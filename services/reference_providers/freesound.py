"""Freesound reference provider."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from services.reference_providers.base import ImportedTrack, ReferenceSearchResult


class FreesoundProvider:
    """Search Freesound metadata for licensed sounds."""

    source = "freesound"
    base_url = "https://freesound.org/apiv2/search/text/"

    def search(self, query: str, page: int = 1, page_size: int = 10) -> list[ReferenceSearchResult]:
        key = os.getenv("FREESOUND_API_KEY")
        if not key:
            return []
        params = urllib.parse.urlencode({"query": query, "page": page, "page_size": page_size, "fields": "id,name,username,duration,previews,license,url"})
        request = urllib.request.Request(f"{self.base_url}?{params}", headers={"Authorization": f"Token {key}"})
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return self.parse_search_response(payload)

    def parse_search_response(self, payload: dict) -> list[ReferenceSearchResult]:
        results = []
        for item in payload.get("results", []):
            previews = item.get("previews") or {}
            results.append(ReferenceSearchResult(
                source=self.source,
                track_id=str(item.get("id", "")),
                title=str(item.get("name", "")),
                artist=item.get("username"),
                duration_sec=float(item["duration"]) if item.get("duration") not in {None, ""} else None,
                preview_url=previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3"),
                stream_url=previews.get("preview-hq-mp3"),
                download_url=None,
                license=item.get("license"),
                can_download=bool(item.get("license")),
                external_url=item.get("url"),
                authorization_notes="Freesound import requires API authorization and compliance with the sound license.",
            ))
        return results

    def import_track(self, track_id: str) -> ImportedTrack:
        return ImportedTrack(self.source, track_id, None, None, "Use the Freesound download endpoint only after checking the selected sound license.")
