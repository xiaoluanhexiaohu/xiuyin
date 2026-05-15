"""YouTube metadata-only provider."""

from __future__ import annotations

import os

import httpx

from services.reference_providers.base import ConfigMissingError, ImportedReferenceAudio, ImportNotAllowedError, ReferenceProvider, ReferenceSearchError, ReferenceSearchItem


YOUTUBE_METADATA_ONLY_NOTE = "YouTube 仅用于搜索展示，不支持后台抓取或导入音频"


class YouTubeProvider(ReferenceProvider):
    """Search YouTube video metadata without downloading, scraping, or importing audio."""

    source = "youtube"
    search_url = "https://www.googleapis.com/youtube/v3/search"

    def _api_key(self) -> str:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            raise ConfigMissingError("YouTube API 未配置，请在 .env 中配置 YOUTUBE_API_KEY")
        return api_key

    async def search(self, query: str, page: int = 1, page_size: int = 10) -> list[ReferenceSearchItem]:
        """Search YouTube Data API videos for display-only metadata."""

        params = {
            "key": self._api_key(),
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": page_size,
            "safeSearch": "none",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.get(self.search_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise ReferenceSearchError(str(exc)) from exc
        return self.parse_search_response(payload)

    def parse_search_response(self, payload: dict) -> list[ReferenceSearchItem]:
        """Convert YouTube search JSON into display-only unified results."""

        results: list[ReferenceSearchItem] = []
        for item in payload.get("items", []):
            video_id = (item.get("id") or {}).get("videoId")
            snippet = item.get("snippet") or {}
            thumbnails = snippet.get("thumbnails") or {}
            thumb = thumbnails.get("high") or thumbnails.get("medium") or thumbnails.get("default") or {}
            results.append(
                ReferenceSearchItem(
                    source=self.source,
                    track_id=str(video_id or ""),
                    title=str(snippet.get("title", "")),
                    artist=snippet.get("channelTitle"),
                    album=None,
                    duration_sec=None,
                    preview_url=None,
                    stream_url=None,
                    download_url=None,
                    cover_url=thumb.get("url"),
                    external_url=f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
                    license=None,
                    can_download=False,
                    authorization_notes=YOUTUBE_METADATA_ONLY_NOTE,
                )
            )
        return results

    async def import_track(self, track_id: str) -> ImportedReferenceAudio:
        """Reject YouTube import because this project never scrapes or downloads YouTube audio."""

        raise ImportNotAllowedError(YOUTUBE_METADATA_ONLY_NOTE)
