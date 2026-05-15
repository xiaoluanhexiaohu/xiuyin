"""Jamendo reference provider with licensed search and authorized import."""

from __future__ import annotations

import os

import httpx

from services.reference_providers.base import (
    AudioNormalizeError,
    ConfigMissingError,
    ImportedReferenceAudio,
    ImportNotAllowedError,
    ReferenceProvider,
    ReferenceSearchError,
    ReferenceSearchItem,
    download_audio,
    extension_from_url,
    new_reference_audio_id,
    normalize_to_wav,
    reference_normalized_dir,
    reference_raw_dir,
    safe_filename,
    target_sample_rate,
)


class JamendoProvider(ReferenceProvider):
    """Search Jamendo and import tracks that expose a licensed download URL."""

    source = "jamendo"
    base_url = "https://api.jamendo.com/v3.0/tracks/"

    def _client_id(self) -> str:
        client_id = os.getenv("JAMENDO_CLIENT_ID")
        if not client_id:
            raise ConfigMissingError("Jamendo API 未配置，请在 .env 中配置 JAMENDO_CLIENT_ID")
        return client_id

    async def search(self, query: str, page: int = 1, page_size: int = 10) -> list[ReferenceSearchItem]:
        """Search Jamendo tracks via the official API."""

        params = {
            "client_id": self._client_id(),
            "format": "json",
            "search": query,
            "limit": page_size,
            "offset": max(0, page - 1) * page_size,
            "include": "licenses",
            "audioformat": "mp32",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise ReferenceSearchError(str(exc)) from exc
        return self.parse_search_response(payload)

    async def _track(self, track_id: str) -> ReferenceSearchItem | None:
        params = {
            "client_id": self._client_id(),
            "format": "json",
            "id": track_id,
            "limit": 1,
            "include": "licenses",
            "audioformat": "mp32",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise ReferenceSearchError(str(exc)) from exc
        items = self.parse_search_response(payload)
        return items[0] if items else None

    def parse_search_response(self, payload: dict) -> list[ReferenceSearchItem]:
        """Convert a Jamendo payload into the unified result format."""

        results: list[ReferenceSearchItem] = []
        for item in payload.get("results", []):
            license_url = item.get("license_ccurl") or item.get("license")
            download_url = item.get("audiodownload")
            preview_url = item.get("audio")
            results.append(
                ReferenceSearchItem(
                    source=self.source,
                    track_id=str(item.get("id", "")),
                    title=str(item.get("name", "")),
                    artist=item.get("artist_name"),
                    album=item.get("album_name"),
                    duration_sec=float(item["duration"]) if item.get("duration") not in {None, ""} else None,
                    preview_url=preview_url,
                    stream_url=preview_url,
                    download_url=download_url,
                    cover_url=item.get("album_image") or item.get("image"),
                    external_url=item.get("shareurl"),
                    license=license_url,
                    can_download=bool(download_url and license_url),
                    authorization_notes="可按 Jamendo 返回的授权条款导入；请在使用前确认 license。" if download_url and license_url else "未返回可下载地址或授权信息，不能后台导入。",
                )
            )
        return results

    async def import_track(self, track_id: str) -> ImportedReferenceAudio:
        """Download and normalize a Jamendo track only when a download URL is present."""

        item = await self._track(track_id)
        if item is None or not item.can_download or not item.download_url:
            raise ImportNotAllowedError("Jamendo result is missing an authorized download URL.")
        audio_id = new_reference_audio_id()
        suffix = extension_from_url(item.download_url)
        raw_path = reference_raw_dir() / self.source / f"{audio_id}_{safe_filename(item.title)}{suffix}"
        normalized_path = reference_normalized_dir() / f"{audio_id}.wav"
        await download_audio(item.download_url, raw_path)
        try:
            info = normalize_to_wav(raw_path, normalized_path)
        except AudioNormalizeError:
            raise
        return ImportedReferenceAudio(
            source=self.source,
            track_id=track_id,
            audio_id=audio_id,
            title=item.title,
            artist=item.artist,
            original_url=item.external_url or item.download_url,
            local_path=str(raw_path),
            normalized_path=str(normalized_path),
            sample_rate=int(info.get("sample_rate", target_sample_rate())),
            duration_sec=float(info.get("duration_sec", item.duration_sec or 0.0)),
            license=item.license,
            authorization_notes=item.authorization_notes,
        )
