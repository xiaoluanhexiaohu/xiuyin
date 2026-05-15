"""Unified audio upload and browser-recording API."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.auth import get_current_user
from app.schemas import AudioKind, AudioSource, AudioUploadResponse
from app.users import User, hash_user_sub
from core.audio_io import MAX_UPLOAD_BYTES, audio_info, normalize_uploaded_audio
from core.vad import energy_vad
from jobs.paths import web_jobs_root

router = APIRouter(prefix="/api/v1/audio", tags=["audio"])

MAX_RECORDING_BYTES = 20 * 1024 * 1024


@router.post("/upload", response_model=AudioUploadResponse)
def upload_audio(
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(description="Uploaded or browser-recorded audio")],
    kind: Annotated[AudioKind, Form()] = "user_vocal",
    source: Annotated[AudioSource, Form()] = "upload",
) -> AudioUploadResponse:
    """Persist one audio object and normalize it to mono WAV."""

    filename = file.filename or "audio.wav"
    suffix = Path(filename).suffix.lower() or ".wav"
    if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".webm", ".mp4"}:
        raise HTTPException(status_code=400, detail={"error_code": "UNSUPPORTED_AUDIO_FORMAT"})
    max_bytes = MAX_RECORDING_BYTES if source == "recording" else MAX_UPLOAD_BYTES
    audio_id = uuid.uuid4().hex
    user_hash = hash_user_sub(current_user.sub)
    root = web_jobs_root() / user_hash / "audio" / audio_id
    raw_path = root / f"original{suffix}"
    wav_path = root / "normalized.wav"
    root.mkdir(parents=True, exist_ok=True)
    total = 0
    with raw_path.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raw_path.unlink(missing_ok=True)
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail={"error_code": "AUDIO_TOO_LARGE"})
            out.write(chunk)
    warnings: list[str] = []
    try:
        normalized = normalize_uploaded_audio(raw_path, wav_path, target_sr=48000)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_AUDIO", "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error_code": "AUDIO_NORMALIZE_FAILED", "message": str(exc)}) from exc
    info = audio_info(wav_path)
    try:
        from core.audio_io import load_audio

        audio = load_audio(wav_path, target_sr=int(info["samplerate"]), normalize=False)
        if not energy_vad(audio.y, audio.sr):
            warnings.append("VOICE_ACTIVITY_EMPTY")
    except Exception as exc:
        warnings.append(f"VOICE_ACTIVITY_CHECK_FAILED: {exc}")
    return AudioUploadResponse(
        audio_id=audio_id,
        kind=kind,
        source=source,
        duration_sec=float(normalized.duration),
        sample_rate=int(info["samplerate"]),
        channels=int(info["channels"]),
        normalized_path=str(wav_path),
        storage_key=f"{user_hash}/audio/{audio_id}/normalized.wav",
        warnings=warnings,
    )
