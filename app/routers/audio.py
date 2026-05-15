"""Unified audio upload and browser-recording API."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.audio_registry import register_audio
from app.auth import get_current_user
from app.schemas import AudioKind, AudioSource, AudioUploadResponse
from app.users import User, hash_user_sub
from core.audio_io import audio_info, load_audio
from core.vad import energy_vad
from services.reference_providers.base import (
    AudioNormalizeError,
    max_audio_size_bytes,
    normalize_to_wav,
    safe_filename,
    upload_normalized_dir,
    upload_raw_dir,
)

router = APIRouter(prefix="/api/v1/audio", tags=["audio"])

MAX_RECORDING_BYTES = 20 * 1024 * 1024
SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".webm", ".mp4"}


@router.post("/upload", response_model=AudioUploadResponse)
def upload_audio(
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(description="Uploaded or browser-recorded audio")],
    kind: Annotated[AudioKind, Form()] = "user_vocal",
    source: Annotated[AudioSource, Form()] = "upload",
) -> AudioUploadResponse:
    """Persist one audio object and normalize it to mono WAV for later jobs."""

    filename = file.filename or "audio.wav"
    suffix = Path(filename).suffix.lower() or ".wav"
    if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_AUDIO_FORMAT"})
    max_bytes = MAX_RECORDING_BYTES if source == "recording" else max_audio_size_bytes()
    audio_id = f"aud_{uuid.uuid4().hex}"
    user_hash = hash_user_sub(current_user.sub)
    raw_path = upload_raw_dir() / user_hash / audio_id / f"{safe_filename(Path(filename).stem)}{suffix}"
    wav_path = upload_normalized_dir() / user_hash / f"{audio_id}.wav"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with raw_path.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raw_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail={"error_code": "AUDIO_TOO_LARGE"})
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error_code": "AUDIO_UPLOAD_FAILED", "message": str(exc)}) from exc

    warnings: list[str] = []
    try:
        normalize_to_wav(raw_path, wav_path)
    except AudioNormalizeError as exc:
        raise HTTPException(status_code=400, detail={"error_code": exc.error_code, "message": exc.message}) from exc
    info = audio_info(wav_path)
    try:
        audio = load_audio(wav_path, target_sr=int(info["samplerate"]), normalize=False)
        if not energy_vad(audio.y, audio.sr):
            warnings.append("VOICE_ACTIVITY_EMPTY")
    except Exception as exc:
        warnings.append(f"VOICE_ACTIVITY_CHECK_FAILED: {exc}")
    register_audio(
        current_user.sub,
        audio_id,
        {
            "kind": kind,
            "source": source,
            "raw_path": str(raw_path),
            "normalized_path": str(wav_path),
            "duration_sec": float(info["duration"]),
            "sample_rate": int(info["samplerate"]),
            "channels": int(info["channels"]),
        },
    )
    return AudioUploadResponse(
        audio_id=audio_id,
        kind=kind,
        source=source,
        duration_sec=float(info["duration"]),
        sample_rate=int(info["samplerate"]),
        channels=int(info["channels"]),
        normalized_path=str(wav_path),
        storage_key=f"{user_hash}/audio/{audio_id}/normalized.wav",
        warnings=warnings,
    )
