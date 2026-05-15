"""YouTube metadata-only provider."""

from __future__ import annotations

from services.reference_providers.base import ImportNotAllowedError, ImportedTrack, ReferenceSearchResult


class YouTubeProvider:
    """Return YouTube search metadata; importing audio is forbidden."""

    source = "youtube"

    def search(self, query: str, page: int = 1, page_size: int = 10) -> list[ReferenceSearchResult]:
        return []

    def import_track(self, track_id: str) -> ImportedTrack:
        raise ImportNotAllowedError("YouTube is metadata-only in this project; backend audio download/import is not allowed.")
