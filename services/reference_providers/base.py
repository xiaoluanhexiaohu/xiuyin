"""Unified reference-audio provider abstractions and helpers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel


class ReferenceProviderError(RuntimeError):
    """Base error carrying a stable API-facing error code."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class ConfigMissingError(ReferenceProviderError):
    """Raised when a required provider credential is not configured."""

    def __init__(self, message: str = "Provider configuration is missing.") -> None:
        super().__init__("CONFIG_MISSING", message)


class ReferenceSearchError(ReferenceProviderError):
    """Raised when provider search fails."""

    def __init__(self, message: str = "Reference search failed.") -> None:
        super().__init__("REFERENCE_SEARCH_FAILED", message)


class ImportNotAllowedError(ReferenceProviderError):
    """Raised when a provider cannot legally import/download audio."""

    def __init__(self, message: str = "Reference import is not allowed.") -> None:
        super().__init__("REFERENCE_IMPORT_NOT_ALLOWED", message)


class ReferenceDownloadError(ReferenceProviderError):
    """Raised when an allowed reference download fails."""

    def __init__(self, message: str = "Reference download failed.") -> None:
        super().__init__("REFERENCE_DOWNLOAD_FAILED", message)


class AudioNormalizeError(ReferenceProviderError):
    """Raised when downloaded/uploaded audio cannot be normalized."""

    def __init__(self, message: str = "Audio normalization failed.") -> None:
        super().__init__("AUDIO_NORMALIZE_FAILED", message)


class ReferenceAudioUnauthorizedError(ReferenceProviderError):
    """Raised when provider metadata does not authorize import."""

    def __init__(self, message: str = "Reference audio is not authorized for import.") -> None:
        super().__init__("REFERENCE_AUDIO_UNAUTHORIZED", message)


class ReferenceSearchItem(BaseModel):
    """One normalized third-party reference search result."""

    source: str
    track_id: str
    title: str
    artist: str | None = None
    album: str | None = None
    duration_sec: float | None = None
    preview_url: str | None = None
    stream_url: str | None = None
    download_url: str | None = None
    cover_url: str | None = None
    external_url: str | None = None
    license: str | None = None
    can_download: bool = False
    authorization_notes: str = ""


class ImportedReferenceAudio(BaseModel):
    """Normalized local reference audio imported from an authorized provider."""

    source: str
    track_id: str
    audio_id: str
    title: str
    artist: str | None = None
    original_url: str | None = None
    local_path: str
    normalized_path: str
    sample_rate: int
    duration_sec: float
    license: str | None = None
    authorization_notes: str = ""


class ReferenceProvider(ABC):
    """Common async interface for reference metadata providers."""

    source: str
    timeout_sec: float = 15.0

    @abstractmethod
    async def search(self, query: str, page: int = 1, page_size: int = 10) -> list[ReferenceSearchItem]:
        """Search provider metadata and return normalized results."""

    @abstractmethod
    async def import_track(self, track_id: str) -> ImportedReferenceAudio:
        """Import a legally downloadable track into local normalized storage."""


def env_int(name: str, default: int) -> int:
    """Read a positive integer from environment with a safe fallback."""

    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    value = int(raw)
    return value if value > 0 else default


def reference_raw_dir() -> Path:
    """Return the configured directory for raw provider downloads."""

    return Path(os.getenv("REFERENCE_RAW_DIR", "storage/reference/raw"))


def reference_normalized_dir() -> Path:
    """Return the configured directory for normalized provider WAV files."""

    return Path(os.getenv("REFERENCE_NORMALIZED_DIR", "storage/reference/normalized"))


def upload_raw_dir() -> Path:
    """Return the configured directory for raw uploads."""

    return Path(os.getenv("UPLOAD_RAW_DIR", "storage/uploads/raw"))


def upload_normalized_dir() -> Path:
    """Return the configured directory for normalized upload WAV files."""

    return Path(os.getenv("UPLOAD_NORMALIZED_DIR", "storage/uploads/normalized"))


def target_sample_rate() -> int:
    """Return configured target sample rate for normalized audio."""

    return env_int("TARGET_SAMPLE_RATE", 48000)


def target_channels() -> int:
    """Return configured target channel count for normalized audio."""

    return env_int("TARGET_CHANNELS", 1)


def max_audio_size_bytes() -> int:
    """Return configured maximum audio file size in bytes."""

    return env_int("MAX_AUDIO_SIZE_MB", 50) * 1024 * 1024


def new_reference_audio_id() -> str:
    """Generate a stable reference-audio identifier."""

    return f"ref_{uuid.uuid4().hex}"


def safe_filename(value: str, fallback: str = "audio") -> str:
    """Sanitize an external filename fragment to avoid path traversal."""

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return cleaned[:120] or fallback


def extension_from_url(url: str, fallback: str = ".mp3") -> str:
    """Best-effort extension extraction from a URL path."""

    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix and len(suffix) <= 10 else fallback


async def download_audio(url: str, destination: Path, headers: dict[str, str] | None = None) -> None:
    """Download an authorized audio URL with size limits and timeout."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0), follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                with destination.open("wb") as out:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        total += len(chunk)
                        if total > max_audio_size_bytes():
                            destination.unlink(missing_ok=True)
                            raise ReferenceDownloadError("AUDIO_TOO_LARGE")
                        out.write(chunk)
    except ReferenceProviderError:
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise ReferenceDownloadError(str(exc)) from exc


def normalize_to_wav(input_path: Path, output_path: Path) -> dict[str, float | int]:
    """Normalize an audio file to configured WAV format using ffmpeg when needed."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg") is None and input_path.suffix.lower() in {".wav", ".flac"}:
        from core.audio_io import audio_info, normalize_uploaded_audio

        try:
            normalize_uploaded_audio(input_path, output_path, target_sr=target_sample_rate())
            info = audio_info(output_path)
        except Exception as exc:
            raise AudioNormalizeError(str(exc)) from exc
        return {
            "sample_rate": int(info["samplerate"]),
            "channels": int(info["channels"]),
            "duration_sec": float(info["duration"]),
        }
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        str(target_channels()),
        "-ar",
        str(target_sample_rate()),
        "-sample_fmt",
        "s16",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise AudioNormalizeError(result.stderr.strip() or "ffmpeg failed")
    from core.audio_io import audio_info

    try:
        info = audio_info(output_path)
    except Exception as exc:
        raise AudioNormalizeError(str(exc)) from exc
    return {
        "sample_rate": int(info["samplerate"]),
        "channels": int(info["channels"]),
        "duration_sec": float(info["duration"]),
    }
