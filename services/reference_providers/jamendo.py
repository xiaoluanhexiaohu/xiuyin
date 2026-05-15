"""Jamendo reference provider."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from services.reference_providers.base import ImportedTrack, ReferenceSearchResult


class JamendoProvider:
    """Search Jamendo and expose downloadable licensed tracks when available."""

    source = "jamendo"
    base_url = "https://api.jamendo.com/v3.0/tracks/"

    def search(self, query: str, page: int = 1, page_size: int = 10) -> list[ReferenceSearchResult]:
        client_id = os.getenv("JAMENDO_CLIENT_ID")
        if not client_id:
            return []
        params = urllib.parse.urlencode({"client_id": client_id, "format": "json", "search": query, "limit": page_size, "offset": max(0, page - 1) * page_size, "include": "licenses"})
        with urllib.request.urlopen(f"{self.base_url}?{params}", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return self.parse_search_response(payload)

    def parse_search_response(self, payload: dict) -> list[ReferenceSearchResult]:
        results = []
        for item in payload.get("results", []):
            license_url = item.get("license_ccurl") or item.get("license")
            audio_url = item.get("audiodownload") or item.get("audio")
            results.append(ReferenceSearchResult(
                source=self.source,
                track_id=str(item.get("id", "")),
                title=str(item.get("name", "")),
                artist=item.get("artist_name"),
                duration_sec=float(item["duration"]) if item.get("duration") not in {None, ""} else None,
                preview_url=item.get("audio"),
                stream_url=item.get("audio"),
                download_url=audio_url,
                license=license_url,
                can_download=bool(audio_url and license_url),
                external_url=item.get("shareurl"),
                authorization_notes="Jamendo tracks may be imported only according to their displayed license.",
            ))
        return results

    def import_track(self, track_id: str) -> ImportedTrack:
        return ImportedTrack(self.source, track_id, None, None, "Resolve the selected Jamendo result and verify its license before downloading.")
