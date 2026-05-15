"""Spotify metadata-only provider."""

from __future__ import annotations

import base64
import os

import httpx

from services.reference_providers.base import ConfigMissingError, ImportedReferenceAudio, ImportNotAllowedError, ReferenceProvider, ReferenceSearchError, ReferenceSearchItem


SPOTIFY_METADATA_ONLY_NOTE = "Spotify 仅用于元数据搜索展示，不支持后台导入原曲音频"


class SpotifyProvider(ReferenceProvider):
    """Search Spotify track metadata without downloading, caching, or importing audio."""

    source = "spotify"
    token_url = "https://accounts.spotify.com/api/token"
    search_url = "https://api.spotify.com/v1/search"

    def _credentials(self) -> tuple[str, str]:
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ConfigMissingError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are required.")
        return client_id, client_secret

    async def _access_token(self) -> str:
        client_id, client_secret = self._credentials()
        raw = f"{client_id}:{client_secret}".encode("utf-8")
        headers = {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}
        data = {"grant_type": "client_credentials"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.post(self.token_url, data=data, headers=headers)
                response.raise_for_status()
                return str(response.json()["access_token"])
        except Exception as exc:
            raise ReferenceSearchError(str(exc)) from exc

    async def search(self, query: str, page: int = 1, page_size: int = 10) -> list[ReferenceSearchItem]:
        """Search Spotify tracks for display-only metadata."""

        token = await self._access_token()
        params = {"q": query, "type": "track", "limit": page_size, "offset": max(0, page - 1) * page_size}
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.get(self.search_url, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise ReferenceSearchError(str(exc)) from exc
        return self.parse_search_response(payload)

    def parse_search_response(self, payload: dict) -> list[ReferenceSearchItem]:
        """Convert Spotify search JSON into display-only unified results."""

        results: list[ReferenceSearchItem] = []
        for item in (payload.get("tracks") or {}).get("items", []):
            album = item.get("album") or {}
            images = album.get("images") or []
            external = item.get("external_urls") or {}
            artists = item.get("artists") or []
            results.append(
                ReferenceSearchItem(
                    source=self.source,
                    track_id=str(item.get("id", "")),
                    title=str(item.get("name", "")),
                    artist=", ".join(str(artist.get("name", "")) for artist in artists if artist.get("name")) or None,
                    album=album.get("name"),
                    duration_sec=float(item.get("duration_ms", 0)) / 1000.0 if item.get("duration_ms") is not None else None,
                    preview_url=item.get("preview_url"),
                    stream_url=None,
                    download_url=None,
                    cover_url=images[0].get("url") if images else None,
                    external_url=external.get("spotify"),
                    license=None,
                    can_download=False,
                    authorization_notes=SPOTIFY_METADATA_ONLY_NOTE,
                )
            )
        return results

    async def import_track(self, track_id: str) -> ImportedReferenceAudio:
        """Reject Spotify import because this project never downloads Spotify audio."""

        raise ImportNotAllowedError(SPOTIFY_METADATA_ONLY_NOTE)
