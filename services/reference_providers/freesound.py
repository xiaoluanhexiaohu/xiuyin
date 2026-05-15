"""Freesound reference provider with preview import fallback."""

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


class FreesoundProvider(ReferenceProvider):
    """Search Freesound and import previews or OAuth-authorized originals."""

    source = "freesound"
    search_url = "https://freesound.org/apiv2/search/text/"
    sound_url = "https://freesound.org/apiv2/sounds/{track_id}/"
    download_url = "https://freesound.org/apiv2/sounds/{track_id}/download/"

    def _api_key(self) -> str:
        key = os.getenv("FREESOUND_API_KEY")
        if not key:
            raise ConfigMissingError("FREESOUND_API_KEY is not configured.")
        return key

    def _oauth_token(self) -> str | None:
        return os.getenv("FREESOUND_OAUTH_TOKEN") or None

    async def search(self, query: str, page: int = 1, page_size: int = 10) -> list[ReferenceSearchItem]:
        """Search Freesound sounds via the official API."""

        params = {
            "query": query,
            "page": page,
            "page_size": page_size,
            "fields": "id,name,username,duration,previews,license,url,images",
        }
        headers = {"Authorization": f"Token {self._api_key()}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.get(self.search_url, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise ReferenceSearchError(str(exc)) from exc
        return self.parse_search_response(payload)

    async def _sound(self, track_id: str) -> ReferenceSearchItem | None:
        headers = {"Authorization": f"Token {self._api_key()}"}
        params = {"fields": "id,name,username,duration,previews,license,url,images"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.get(self.sound_url.format(track_id=track_id), params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise ReferenceSearchError(str(exc)) from exc
        items = self.parse_search_response({"results": [payload]})
        return items[0] if items else None

    def parse_search_response(self, payload: dict) -> list[ReferenceSearchItem]:
        """Convert a Freesound payload into the unified result format."""

        results: list[ReferenceSearchItem] = []
        for item in payload.get("results", []):
            previews = item.get("previews") or {}
            images = item.get("images") or {}
            preview_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3") or previews.get("preview-hq-ogg")
            has_oauth = bool(self._oauth_token())
            results.append(
                ReferenceSearchItem(
                    source=self.source,
                    track_id=str(item.get("id", "")),
                    title=str(item.get("name", "")),
                    artist=item.get("username"),
                    album=None,
                    duration_sec=float(item["duration"]) if item.get("duration") not in {None, ""} else None,
                    preview_url=preview_url,
                    stream_url=preview_url,
                    download_url=self.download_url.format(track_id=item.get("id")) if has_oauth else preview_url,
                    cover_url=images.get("waveform_m") or images.get("spectral_m"),
                    external_url=item.get("url"),
                    license=item.get("license"),
                    can_download=bool(item.get("license") and (preview_url or has_oauth)),
                    authorization_notes="已配置 OAuth2，可按 Freesound 授权下载原始文件。" if has_oauth else "仅导入 preview，原始文件下载需要 OAuth2。",
                )
            )
        return results

    async def import_track(self, track_id: str) -> ImportedReferenceAudio:
        """Import an OAuth-authorized original, or preview audio when OAuth is absent."""

        item = await self._sound(track_id)
        if item is None or not item.can_download:
            raise ImportNotAllowedError("Freesound result has no importable preview/original audio.")
        oauth_token = self._oauth_token()
        if oauth_token:
            source_url = self.download_url.format(track_id=track_id)
            headers = {"Authorization": f"Bearer {oauth_token}"}
        else:
            source_url = item.preview_url
            headers = None
        if not source_url:
            raise ImportNotAllowedError("Freesound result has no preview URL and no OAuth2 original download token.")
        audio_id = new_reference_audio_id()
        suffix = extension_from_url(source_url)
        raw_path = reference_raw_dir() / self.source / f"{audio_id}_{safe_filename(item.title)}{suffix}"
        normalized_path = reference_normalized_dir() / f"{audio_id}.wav"
        await download_audio(source_url, raw_path, headers=headers)
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
            original_url=item.external_url or source_url,
            local_path=str(raw_path),
            normalized_path=str(normalized_path),
            sample_rate=int(info.get("sample_rate", target_sample_rate())),
            duration_sec=float(info.get("duration_sec", item.duration_sec or 0.0)),
            license=item.license,
            authorization_notes=item.authorization_notes,
        )
