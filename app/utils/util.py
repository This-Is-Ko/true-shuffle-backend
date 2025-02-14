from datetime import datetime
from typing import List
from flask import current_app
import spotipy

LIKED_TRACKS_PLAYLIST_ID = "likedTracks"


def update_task_progress(task, state, meta):
    if (task is None):
        current_app.logger.error("Task is missing - Unable to update task state")
    else:
        task.update_state(state=state, meta=meta)


def get_tracks_from_playlist(task, spotify: spotipy.Spotify, playlist_id: str) -> List[str]:
    """
    Get tracks from playlist based on playlist_id
    Use separate spotify call for retrieving Liked Tracks
    """
    offset = 0
    all_tracks = []
    while True:
        if playlist_id == LIKED_TRACKS_PLAYLIST_ID:
            tracks_response = spotify.current_user_saved_tracks(limit=50, offset=offset)
        else:
            tracks_response = spotify.playlist_items(playlist_id, limit=50, offset=offset)
        if tracks_response is not None and "items" in tracks_response:
            if len(tracks_response["items"]) == 0:
                break
            for track in tracks_response["items"]:
                if track["track"] is not None and track["track"]["uri"] is not None:
                    all_tracks.append(track["track"]["uri"])
                else:
                    current_app.logger.info("Track missing uri: " + str(track))
            offset += len(tracks_response["items"])
        update_task_progress(task=task, state='PROGRESS', meta={'progress': {
                             'state': "Retrieved " + str(len(all_tracks)) + " tracks so far..."}})
    return all_tracks


def get_all_tracks_with_data_from_playlist(task, spotify: spotipy.Spotify, playlist_id: str):
    """
    Get tracks from playlist based on playlist_id
    Use separate spotify call for retrieving Liked Tracks
    """
    offset = 0
    all_tracks = []
    while True:
        if playlist_id == LIKED_TRACKS_PLAYLIST_ID:
            tracks_response = spotify.current_user_saved_tracks(limit=50, offset=offset)
        else:
            tracks_response = spotify.playlist_items(playlist_id, limit=50, offset=offset)
        if "items" in tracks_response:
            if len(tracks_response["items"]) == 0:
                break
            for track in tracks_response["items"]:
                all_tracks.append(track)
        offset += len(tracks_response["items"])
        update_task_progress(task, state='PROGRESS', meta={'progress': {
                             'state': "Retrieved " + str(len(all_tracks)) + " tracks so far..."}})
        if offset >= tracks_response["total"]:
            break
    return all_tracks


def get_liked_tracks_count(spotify: spotipy.Spotify):
    """
    Get number of songs in user library
    If error, return False
    """
    liked_tracks_response = spotify.current_user_saved_tracks()
    # get_liked_tracks_log = "Liked tracks response: {response}"
    # current_app.logger.debug(
    #     get_liked_tracks_log.format(response=liked_tracks_response))
    if "total" in liked_tracks_response:
        return liked_tracks_response["total"]
    return None


def get_all_track_audio_features(task, spotify: spotipy.Spotify, tracks: list):
    """
    Get audio features for all tracks
    If error, return False
    """
    update_task_progress(task, state='PROGRESS', meta={'progress': {'state': "Getting audio features for each track"}})
    tracks_left = len(tracks)
    index = 0
    all_track_features = []
    while tracks_left > 0:
        # Max 100 tracks at once
        if tracks_left < 100:
            tracks_to_analyse = tracks[index: index + tracks_left]
            tracks_left -= tracks_left
            index += tracks_left
        else:
            tracks_to_analyse = tracks[index: index + 100]
            tracks_left -= 100
            index += 100
        response = spotify.audio_features(tracks_to_analyse)
        all_track_features += response
        update_task_progress(
            task, state='PROGRESS', meta={
                'progress': {
                    'state': "Retrieved audio features for " + str(index) + " tracks so far..."}})
    return all_track_features


def calcFromMillis(milliseconds):
    seconds = (milliseconds / 1000) % 60
    seconds = int(seconds)
    minutes = (milliseconds / (1000 * 60)) % 60
    minutes = int(minutes)
    hours = (milliseconds / (1000 * 60 * 60)) % 24
    hours = int(hours)
    days = (milliseconds / (1000 * 60 * 60 * 24)) % 365
    days = int(days)
    return seconds, minutes, hours, days


def create_new_playlist_with_tracks(
        task,
        spotify: spotipy.Spotify,
        new_playlist_name: str,
        public_status: bool,
        playlist_description: str,
        tracks_to_add: List[str]):
    try:
        if tracks_to_add is None:
            raise Exception("No tracks to add")

        # Remove any invalid uris which have a whitespace
        tracks_to_add = validate_tracks(tracks_to_add)
        if len(tracks_to_add) == 0:
            raise Exception("No tracks to add")

        # Create new playlist
        user_id = spotify.me()["id"]
        new_playlist = spotify.user_playlist_create(
            user=user_id,
            name=new_playlist_name,
            public=public_status,
            description=playlist_description)
        new_playlist_id = new_playlist["id"]
        if new_playlist_id is None:
            raise Exception("Created playlist id is missing")
        current_app.logger.info(
            "User: {user_id} -- Initialised playlist: {playlist_id}".format(
                user_id=user_id,
                playlist_id=new_playlist_id
            )
        )

        # Add 100 tracks per call
        if len(tracks_to_add) <= 100:
            calls_required = 1
        else:
            calls_required = len(tracks_to_add) // 100 + 1
        left_over = len(tracks_to_add) % 100
        for i in range(calls_required):
            if i == calls_required - 1:
                add_items_response = spotify.playlist_add_items(
                    new_playlist_id, tracks_to_add[i * 100: i * 100 + left_over])
                update_task_progress(task, state='PROGRESS', meta={'progress': {
                                     'state': "Adding  " + str(i * 100 + left_over) + "/" + str(len(tracks_to_add))
                                     + " tracks..."}})
            else:
                add_items_response = spotify.playlist_add_items(new_playlist_id, tracks_to_add[i * 100: i * 100 + 100])
                update_task_progress(task, state='PROGRESS', meta={'progress': {
                                     'state': "Added " + str(i * 100 + 100) + "/" + str(len(tracks_to_add))
                                     + " tracks"}})
            if "snapshot_id" not in add_items_response:
                current_app.logger.error("Error while adding tracks. Response: " + add_items_response)
                return {
                    "error": "Unable to add tracks to playlist " + new_playlist_id
                }

        create_playlist_with_tracks_success_log = "User: {user_id}"
        + "-- Created playlist: {playlist_id}"
        + "-- Length: {length:d}"
        current_app.logger.info(
            create_playlist_with_tracks_success_log.format(
                user_id=user_id,
                playlist_id=new_playlist_id,
                length=len(tracks_to_add)))

        return {
            "status": "success",
            "playlist_uri": new_playlist["external_urls"]["spotify"],
            "num_of_tracks": len(tracks_to_add),
            "creation_time": datetime.now()
        }
    except Exception as e:
        current_app.logger.error("Error while creating new playlist / adding tracks: " + str(e))
        return {
            "error": "Unable to create new playlist / add tracks to playlist"
        }


def validate_tracks(track_list: List[str]) -> List[str]:
    valid_tracks = []
    invalid_tracks = []
    for track in track_list:
        if track.startswith("spotify:track:") and " " not in track[14:]:
            valid_tracks.append(track)
        else:
            invalid_tracks.append(track)
    if invalid_tracks:
        current_app.logger.warning("Tracks without the correct uri format were removed")
        current_app.logger.warning(invalid_tracks)
    return valid_tracks
