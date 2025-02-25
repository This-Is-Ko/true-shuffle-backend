import time
from datetime import date
from celery import shared_task
import random
from flask import current_app

from database import database
from services.spotify_client import create_spotify_client
from utils import util, tracker_utils

SHUFFLED_PLAYLIST_PREFIX = "[Shuffled] "
LIKED_TRACKS_PLAYLIST_ID = "likedTracks"
TRACK_SHUFFLES_ATTRIBUTE_NAME = "track_shuffles"


@shared_task(bind=True, ignore_result=False, expires=60)
def shuffle_playlist(self, spotify_auth_dict: dict, playlist_id, playlist_name):
    spotify_client = create_spotify_client(current_app, spotify_auth_dict)

    # Store start time to calculate duration
    start_time = time.time()

    # Grab all tracks from playlist
    all_tracks = util.get_tracks_from_playlist(self, spotify_client, playlist_id)
    if all_tracks is None or len(all_tracks) == 0:
        return {"error": "No tracks found for playlist " + playlist_id}

    # Check if user exists
    user = database.find_user(spotify_client.me()["id"])
    if user is None:
        return {"error": "No user found"}

    util.update_task_progress(
        self,
        state='PROGRESS',
        meta={'progress': {'state': "Shuffling " + str(len(all_tracks)) + " tracks..."}}
    )
    random.shuffle(all_tracks)

    # Check if shuffled playlist exists and remove
    user_playlists = spotify_client.current_user_playlists()
    for playlist in user_playlists["items"]:
        if playlist["name"] == (SHUFFLED_PLAYLIST_PREFIX + playlist_name):
            spotify_client.current_user_unfollow_playlist(playlist["id"])
            break

    response = util.create_new_playlist_with_tracks(
        self,
        spotify_client,
        SHUFFLED_PLAYLIST_PREFIX + playlist_name,
        False,
        "Shuffled by True Shuffle",
        all_tracks
    )

    if response is not None and response["status"] == "success":
        # Calculate duration of process
        duration_seconds = int(time.time() - start_time)

        # Increment user counters for playlists and tracks
        tracker_utils.update_user_trackers(user, playlist_id, playlist_name, len(all_tracks), duration_seconds)

        # Increment overall counters for playlists and tracks
        tracker_utils.update_overall_trackers(len(all_tracks))

    return response


@shared_task(bind=True, ignore_result=False, expires=60)
def create_playlist_from_liked_tracks(self, spotify_auth_dict: dict, new_playlist_name):
    spotify_client = create_spotify_client(current_app, spotify_auth_dict)

    all_tracks = util.get_tracks_from_playlist(self, spotify_client, LIKED_TRACKS_PLAYLIST_ID)
    if all_tracks is None or len(all_tracks) == 0:
        return {"error": "No tracks found for user's liked songs"}

    today = date.today()

    return util.create_new_playlist_with_tracks(
        self,
        spotify_client,
        new_playlist_name,
        True,
        "True Shuffle | My Liked Tracks from " + today.strftime("%d/%m/%Y"),
        all_tracks
    )
