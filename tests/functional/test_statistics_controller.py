from tests import client, env_patch


def test_get_statistics_success(mocker, client, env_patch):
    """
    Successful GET Statistics call
    """
    mocker.patch("builtins.open", mocker.mock_open(read_data="99"))
    response = client.get('/api/statistics/overall')
    response_json = response.get_json()
    print(response_json)
    assert response.status_code == 200
    assert response_json["playlist_counter"] == "99"
    assert response_json["track_counter"] == "99"
