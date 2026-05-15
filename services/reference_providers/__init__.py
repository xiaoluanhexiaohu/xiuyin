"""Reference provider registry."""

from services.reference_providers.base import (
    AudioNormalizeError,
    ConfigMissingError,
    ImportedReferenceAudio,
    ImportNotAllowedError,
    ReferenceAudioUnauthorizedError,
    ReferenceDownloadError,
    ReferenceProviderError,
    ReferenceSearchError,
    ReferenceSearchItem,
)
from services.reference_providers.freesound import FreesoundProvider
from services.reference_providers.jamendo import JamendoProvider
from services.reference_providers.spotify import SpotifyProvider
from services.reference_providers.youtube import YouTubeProvider

PROVIDERS = {
    "jamendo": JamendoProvider,
    "freesound": FreesoundProvider,
    "spotify": SpotifyProvider,
    "youtube": YouTubeProvider,
}

__all__ = [
    "PROVIDERS",
    "AudioNormalizeError",
    "ConfigMissingError",
    "ImportedReferenceAudio",
    "ImportNotAllowedError",
    "ReferenceAudioUnauthorizedError",
    "ReferenceDownloadError",
    "ReferenceProviderError",
    "ReferenceSearchError",
    "ReferenceSearchItem",
]
