"""Unified F0 tracking with optional torchcrepe and librosa.pyin fallback."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module, util
from pathlib import Path
from typing import Any

import librosa
import numpy as np

from core.audio_io import load_audio


@dataclass
class PitchTrackerConfig:
    """Configuration for pitch tracking."""

    hop_length: int = 512
    fmin: float = 65.0
    fmax: float = 1047.0
    model: str = "full"
    batch_size: int = 2048


@dataclass
class PitchTrack:
    """JSON-friendly pitch tracking result."""

    times: list[float]
    f0_hz: list[float | None]
    voiced_flag: list[bool]
    voiced_prob: list[float]
    method: str
    sr: int
    hop_length: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""

        return self.__dict__.copy()


def analyze_file(path: str | Path, config: PitchTrackerConfig | None = None) -> PitchTrack:
    """Load a file and analyze its F0 contour."""

    audio = load_audio(path, normalize=True)
    return analyze_array(audio.y, audio.sr, config=config)


def analyze_array(y: np.ndarray, sr: int, config: PitchTrackerConfig | None = None) -> PitchTrack:
    """Analyze F0 from an audio array, preferring torchcrepe when installed."""

    cfg = config or PitchTrackerConfig()
    samples = np.nan_to_num(np.asarray(y, dtype=np.float32))
    if util.find_spec("torchcrepe") is not None and util.find_spec("torch") is not None:
        return _analyze_torchcrepe(samples, sr, cfg)
    return _analyze_librosa(samples, sr, cfg)


def _analyze_torchcrepe(y: np.ndarray, sr: int, cfg: PitchTrackerConfig) -> PitchTrack:
    """Run torchcrepe dynamically after availability has been checked."""

    torch = import_module("torch")
    torchcrepe = import_module("torchcrepe")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    audio = torch.tensor(y, dtype=torch.float32, device=device).unsqueeze(0)
    f0, periodicity = torchcrepe.predict(
        audio,
        sr,
        cfg.hop_length,
        cfg.fmin,
        cfg.fmax,
        cfg.model,
        cfg.batch_size,
        device,
        return_periodicity=True,
    )
    f0_np = f0.squeeze(0).detach().cpu().numpy().astype(float)
    prob_np = periodicity.squeeze(0).detach().cpu().numpy().astype(float)
    voiced = np.isfinite(f0_np) & (f0_np > 0) & (prob_np >= 0.5)
    return _build_track(f0_np, voiced, prob_np, sr, cfg.hop_length, "torchcrepe")


def _analyze_librosa(y: np.ndarray, sr: int, cfg: PitchTrackerConfig) -> PitchTrack:
    """Run librosa.pyin fallback pitch tracking."""

    if y.size == 0:
        return PitchTrack([], [], [], [], "librosa.pyin", sr, cfg.hop_length)
    f0, voiced_flag, voiced_prob = librosa.pyin(
        y,
        fmin=cfg.fmin,
        fmax=cfg.fmax,
        sr=sr,
        hop_length=cfg.hop_length,
    )
    return _build_track(f0, voiced_flag, voiced_prob, sr, cfg.hop_length, "librosa.pyin")


def _build_track(
    f0: np.ndarray,
    voiced_flag: np.ndarray,
    voiced_prob: np.ndarray,
    sr: int,
    hop_length: int,
    method: str,
) -> PitchTrack:
    """Normalize backend arrays into JSON-safe lists."""

    f0_arr = np.asarray(f0, dtype=float)
    prob_arr = np.nan_to_num(np.asarray(voiced_prob, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    flag_arr = np.asarray(voiced_flag, dtype=bool) & np.isfinite(f0_arr) & (f0_arr > 0)
    f0_list = [float(v) if bool(flag_arr[i]) and np.isfinite(v) else None for i, v in enumerate(f0_arr)]
    times = librosa.frames_to_time(np.arange(len(f0_arr)), sr=sr, hop_length=hop_length)
    return PitchTrack(
        times=[float(t) for t in times],
        f0_hz=f0_list,
        voiced_flag=[bool(v) for v in flag_arr],
        voiced_prob=[float(np.clip(v, 0.0, 1.0)) for v in prob_arr],
        method=method,
        sr=int(sr),
        hop_length=int(hop_length),
    )
