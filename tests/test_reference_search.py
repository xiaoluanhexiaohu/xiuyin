import pytest

from services.reference_providers.freesound import FreesoundProvider
from services.reference_providers.jamendo import JamendoProvider
from services.reference_providers.spotify import SpotifyProvider
from services.reference_providers.youtube import YouTubeProvider


def test_jamendo_parse_search_result():
    payload = {
        "results": [
            {
                "id": "1",
                "name": "Song",
                "artist_name": "Artist",
                "album_name": "Album",
                "duration": "12",
                "audio": "https://audio",
                "audiodownload": "https://download",
                "license_ccurl": "https://license",
                "shareurl": "https://share",
                "album_image": "https://cover",
            }
        ]
    }
    result = JamendoProvider().parse_search_response(payload)[0]
    assert result.source == "jamendo"
    assert result.album == "Album"
    assert result.cover_url == "https://cover"
    assert result.can_download is True
    assert result.license == "https://license"


def test_freesound_parse_search_result_without_oauth(monkeypatch):
    monkeypatch.delenv("FREESOUND_OAUTH_TOKEN", raising=False)
    payload = {
        "results": [
            {
                "id": 42,
                "name": "Kick",
                "username": "maker",
                "duration": 1.5,
                "previews": {"preview-hq-mp3": "https://preview"},
                "license": "CC0",
                "url": "https://freesound/42",
            }
        ]
    }
    result = FreesoundProvider().parse_search_response(payload)[0]
    assert result.source == "freesound"
    assert result.track_id == "42"
    assert result.preview_url == "https://preview"
    assert result.can_download is True
    assert "preview" in result.authorization_notes


def test_spotify_parse_search_metadata_only():
    payload = {
        "tracks": {
            "items": [
                {
                    "id": "sp1",
                    "name": "Song",
                    "duration_ms": 123000,
                    "preview_url": "https://preview",
                    "artists": [{"name": "Singer"}],
                    "album": {"name": "Album", "images": [{"url": "https://cover"}]},
                    "external_urls": {"spotify": "https://open.spotify.com/track/sp1"},
                }
            ]
        }
    }
    result = SpotifyProvider().parse_search_response(payload)[0]
    assert result.can_download is False
    assert result.download_url is None
    assert result.album == "Album"
    assert "不支持后台导入" in result.authorization_notes


def test_youtube_parse_search_metadata_only():
    payload = {
        "items": [
            {
                "id": {"videoId": "yt1"},
                "snippet": {
                    "title": "Video",
                    "channelTitle": "Channel",
                    "thumbnails": {"high": {"url": "https://thumb"}},
                },
            }
        ]
    }
    result = YouTubeProvider().parse_search_response(payload)[0]
    assert result.track_id == "yt1"
    assert result.can_download is False
    assert result.download_url is None
    assert result.external_url == "https://www.youtube.com/watch?v=yt1"


@pytest.mark.parametrize("provider", [SpotifyProvider(), YouTubeProvider()])
def test_metadata_only_providers_do_not_import(provider):
    import asyncio

    with pytest.raises(Exception) as exc_info:
        asyncio.run(provider.import_track("abc"))
    assert getattr(exc_info.value, "error_code", None) == "REFERENCE_IMPORT_NOT_ALLOWED"


def test_reference_search_is_public_and_returns_config_missing(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.delenv("JAMENDO_CLIENT_ID", raising=False)
    client = TestClient(app)
    response = client.post(
        "/api/v1/reference/search",
        json={"source": "jamendo", "query": "hello", "page": 1, "page_size": 10},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error_code"] == "CONFIG_MISSING"
    assert "JAMENDO_CLIENT_ID" in data["message"]


def test_reference_search_options_is_public():
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).options("/api/v1/reference/search")
    assert response.status_code == 200


def test_reference_import_still_requires_login():
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).post(
        "/api/v1/reference/import",
        json={"source": "jamendo", "track_id": "1"},
    )
    assert response.status_code == 401
