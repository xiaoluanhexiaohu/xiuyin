"""Audio loading, normalization, and WAV export utilities for the offline MVP."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


@dataclass
class AudioData:
    """In-memory mono audio plus basic metadata."""

    y: np.ndarray
    sr: int
    path: str | None
    duration: float
    channels: int


@dataclass
class AudioWriteResult:
    """Metadata returned after writing an audio file."""

    path: str
    sr: int
    duration: float
    peak: float


def load_audio(
    path: str | Path,
    target_sr: int = 44100,
    mono: bool = True,
    normalize: bool = True,
) -> AudioData:
    """Load an audio file, resample it, optionally convert to mono, and normalize."""

    audio_path = Path(path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    info = sf.info(str(audio_path))
    y, sr = librosa.load(str(audio_path), sr=target_sr, mono=mono)
    y = np.asarray(y, dtype=np.float32)
    if normalize:
        y = peak_normalize(y)
    duration = float(len(y) / sr) if mono else float(y.shape[-1] / sr)
    return AudioData(y=y, sr=sr, path=str(audio_path), duration=duration, channels=info.channels)


def peak_normalize(y: np.ndarray, target_peak: float = 0.98) -> np.ndarray:
    """Peak-normalize audio without amplifying silence or non-finite values."""

    samples = np.nan_to_num(np.asarray(y, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak <= 1e-9:
        return samples
    return (samples / peak * target_peak).astype(np.float32)


def write_wav(path: str | Path, y: np.ndarray, sr: int, normalize: bool = False) -> AudioWriteResult:
    """Write audio as WAV and return basic file metadata."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    samples = peak_normalize(y) if normalize else np.nan_to_num(np.asarray(y, dtype=np.float32))
    sf.write(str(output_path), samples, sr)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    duration = float(len(samples) / sr) if samples.ndim == 1 else float(samples.shape[0] / sr)
    return AudioWriteResult(path=str(output_path), sr=sr, duration=duration, peak=peak)


def audio_info(path: str | Path) -> dict:
    """Return JSON-friendly audio file information."""

    audio_path = Path(path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    info = sf.info(str(audio_path))
    return {
        "path": str(audio_path),
        "samplerate": int(info.samplerate),
        "channels": int(info.channels),
        "duration": float(info.duration),
        "frames": int(info.frames),
        "format": info.format,
        "subtype": info.subtype,
    }
