"""Unified reference-audio provider abstractions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ReferenceSearchResult:
    """One third-party search result."""

    source: str
    track_id: str
    title: str
    artist: str | None = None
    duration_sec: float | None = None
    preview_url: str | None = None
    stream_url: str | None = None
    download_url: str | None = None
    license: str | None = None
    can_download: bool = False
    external_url: str | None = None
    authorization_notes: str = ""


@dataclass
class ImportedTrack:
    """Imported/downloadable track metadata."""

    source: str
    track_id: str
    audio_url: str | None
    license: str | None
    authorization_notes: str


class ReferenceProvider(Protocol):
    """Common provider interface."""

    source: str

    def search(self, query: str, page: int = 1, page_size: int = 10) -> list[ReferenceSearchResult]: ...

    def import_track(self, track_id: str) -> ImportedTrack: ...


class ImportNotAllowedError(RuntimeError):
    """Raised when a provider cannot legally import/download audio."""
