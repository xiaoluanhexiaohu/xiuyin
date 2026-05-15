"""Simple VAD helpers used by upload validation and segment location."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VoicedSegment:
    """A voiced/active audio segment in seconds."""

    start_sec: float
    end_sec: float
    confidence: float


def energy_vad(y: np.ndarray, sr: int, frame_length: int = 2048, hop_length: int = 512, threshold_db: float = -45.0) -> list[VoicedSegment]:
    """Detect active regions with an RMS threshold and merge adjacent frames."""

    samples = np.nan_to_num(np.asarray(y, dtype=np.float32))
    if samples.size == 0:
        return []
    frames = []
    for start in range(0, max(1, len(samples) - frame_length + 1), hop_length):
        chunk = samples[start : start + frame_length]
        rms = float(np.sqrt(np.mean(chunk * chunk))) if chunk.size else 0.0
        db = 20.0 * np.log10(max(rms, 1e-8))
        frames.append((start, start + len(chunk), db >= threshold_db, rms))
    segments: list[VoicedSegment] = []
    active_start: int | None = None
    confidences: list[float] = []
    for start, end, active, rms in frames:
        if active and active_start is None:
            active_start = start
            confidences = []
        if active:
            confidences.append(min(1.0, rms * 20.0))
        elif active_start is not None:
            segments.append(VoicedSegment(active_start / sr, start / sr, float(np.mean(confidences) if confidences else 0.0)))
            active_start = None
    if active_start is not None:
        segments.append(VoicedSegment(active_start / sr, min(len(samples), frames[-1][1]) / sr, float(np.mean(confidences) if confidences else 0.0)))
    return [s for s in segments if s.end_sec - s.start_sec > 0.05]
