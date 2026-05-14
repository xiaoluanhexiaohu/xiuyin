"""Audio loading, normalization, upload validation, and WAV export utilities."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

SUPPORTED_UPLOAD_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac"}
COMPRESSED_EXTENSIONS = {".mp3", ".m4a"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_UPLOAD_DURATION_SECONDS = 600.0


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


def is_ffmpeg_available() -> bool:
    """Return whether ffmpeg and ffprobe are available on PATH."""

    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_audio_duration(path: str | Path) -> float:
    """Probe audio duration in seconds using soundfile first, then ffprobe."""

    audio_path = Path(path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if audio_path.suffix.lower() not in COMPRESSED_EXTENSIONS:
        info = sf.info(str(audio_path))
        return float(info.duration)
    if not is_ffmpeg_available():
        raise RuntimeError("服务器未安装 ffmpeg，无法处理 mp3/m4a，请上传 wav 或联系管理员。")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    return float(payload["format"]["duration"])


def validate_audio_limits(
    path: str | Path,
    max_bytes: int = MAX_UPLOAD_BYTES,
    max_duration_seconds: float = MAX_UPLOAD_DURATION_SECONDS,
) -> None:
    """Validate upload extension, size, and duration with Chinese user errors."""

    audio_path = Path(path)
    suffix = audio_path.suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise ValueError("仅支持 wav、mp3、m4a、flac 格式。")
    if audio_path.stat().st_size > max_bytes:
        raise ValueError("单个音频文件不能超过 100MB。")
    duration = probe_audio_duration(audio_path)
    if duration > max_duration_seconds:
        raise ValueError("音频时长不能超过 10 分钟。")


def normalize_uploaded_audio(
    input_path: str | Path,
    output_wav_path: str | Path,
    target_sr: int = 44100,
) -> AudioWriteResult:
    """Normalize an uploaded audio file into a mono working WAV."""

    src = Path(input_path)
    dst = Path(output_wav_path)
    validate_audio_limits(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower()
    if suffix in COMPRESSED_EXTENSIONS:
        if not is_ffmpeg_available():
            raise RuntimeError("服务器未安装 ffmpeg，无法处理 mp3/m4a，请上传 wav 或联系管理员。")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-ac",
                "1",
                "-ar",
                str(target_sr),
                "-sample_fmt",
                "s16",
                str(dst),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        audio = load_audio(dst, target_sr=target_sr, normalize=True)
        return write_wav(dst, audio.y, audio.sr, normalize=False)
    audio = load_audio(src, target_sr=target_sr, mono=True, normalize=True)
    return write_wav(dst, audio.y, audio.sr, normalize=False)
