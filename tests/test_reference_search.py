import pytest

from services.reference_providers.base import ImportNotAllowedError
from services.reference_providers.jamendo import JamendoProvider
from services.reference_providers.spotify import SpotifyProvider
from services.reference_providers.youtube import YouTubeProvider


def test_jamendo_parse_search_result():
    payload = {"results": [{"id": "1", "name": "Song", "artist_name": "Artist", "duration": "12", "audio": "https://audio", "audiodownload": "https://download", "license_ccurl": "https://license", "shareurl": "https://share"}]}
    result = JamendoProvider().parse_search_response(payload)[0]
    assert result.source == "jamendo"
    assert result.can_download is True
    assert result.license == "https://license"


@pytest.mark.parametrize("provider", [SpotifyProvider(), YouTubeProvider()])
def test_metadata_only_providers_do_not_import(provider):
    with pytest.raises(ImportNotAllowedError):
        provider.import_track("abc")
