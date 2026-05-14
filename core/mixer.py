"""Simple offline mixer for corrected vocals and optional accompaniment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.audio_io import load_audio, peak_normalize, write_wav


@dataclass
class MixResult:
    """Metadata from creating `mix.wav`."""

    output_path: str
    mix_mode: str
    peak: float
    duration: float
    warnings: list[str]


def mix_audio(
    vocal_path: str | Path,
    accompaniment_path: str | Path | None,
    output_path: str | Path,
    vocal_gain_db: float = 0.0,
    accompaniment_gain_db: float = 0.0,
) -> MixResult:
    """Mix corrected vocal with accompaniment, or create a vocal-only mix."""

    vocal = load_audio(vocal_path, normalize=False)
    warnings: list[str] = []
    vocal_y = vocal.y * _db_to_gain(vocal_gain_db)
    if accompaniment_path is None or not Path(accompaniment_path).exists():
        if accompaniment_path is not None:
            warnings.append(f"Accompaniment not found; writing vocal-only mix: {accompaniment_path}")
        mix = vocal_y
        mode = "vocal_only"
    else:
        acc = load_audio(accompaniment_path, target_sr=vocal.sr, normalize=False)
        acc_y = acc.y * _db_to_gain(accompaniment_gain_db)
        n = max(len(vocal_y), len(acc_y))
        mix = _pad(vocal_y, n) + _pad(acc_y, n)
        mode = "vocal_plus_accompaniment"
    mix = peak_normalize(mix, target_peak=0.98)
    write = write_wav(output_path, mix, vocal.sr, normalize=False)
    return MixResult(write.path, mode, write.peak, write.duration, warnings)


def _db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def _pad(y: np.ndarray, length: int) -> np.ndarray:
    if len(y) >= length:
        return y[:length]
    return np.pad(y, (0, length - len(y)))
