"""Approximate syllable segmentation for conservative web correction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from core.aligner import AlignmentResult
from core.correction_planner import CorrectionPlan
from core.feature_extractor import AudioFeatures
from core.pitch_tracker import PitchTrack

Granularity = Literal["conservative", "normal", "aggressive"]


@dataclass
class SyllableSegment:
    """A conservative approximate syllable-like correction region."""

    segment_id: int
    user_start_time: float
    user_end_time: float
    reference_start_time: float
    reference_end_time: float
    user_frame_start: int
    user_frame_end: int
    reference_frame_start: int
    reference_frame_end: int
    median_shift_cents: float
    confidence: float
    skipped: bool
    skipped_reason: str | None


def segment_syllables(
    user_pitch: PitchTrack,
    reference_pitch: PitchTrack,
    user_features: AudioFeatures,
    reference_features: AudioFeatures,
    alignment: AlignmentResult,
    correction_plan: CorrectionPlan,
    granularity: Granularity = "conservative",
) -> list[SyllableSegment]:
    """Create approximate syllable segments from onset, voicing, RMS, F0, and DTW mapping."""

    n = min(len(user_pitch.times), len(user_features.times), len(correction_plan.shift_cents))
    if n == 0:
        return []
    onset = _resize(user_features.onset_strength, n)
    rms = _resize(user_features.rms, n)
    voiced = np.asarray(user_pitch.voiced_flag[:n], dtype=bool)
    probs = _resize(user_pitch.voiced_prob, n)
    settings = {
        "conservative": (1.25, 0.28),
        "normal": (0.9, 0.18),
        "aggressive": (0.55, 0.10),
    }[granularity]
    onset_threshold, min_dur = settings
    frame_step = float(user_pitch.hop_length / user_pitch.sr) if user_pitch.sr else 0.012
    min_frames = max(2, int(round(min_dur / frame_step)))
    boundaries = {0, n}
    onset_z = _zscore(onset)
    rms_z = _zscore(rms)
    for i in range(1, n - 1):
        if onset_z[i] > onset_threshold and onset_z[i] >= onset_z[i - 1] and onset_z[i] >= onset_z[i + 1]:
            boundaries.add(i)
        if voiced[i] != voiced[i - 1]:
            boundaries.add(i)
        if abs(rms_z[i] - rms_z[i - 1]) > onset_threshold * 1.5:
            boundaries.add(i)
    merged = [0]
    for b in sorted(boundaries):
        if b == 0:
            continue
        if b - merged[-1] < min_frames and granularity == "conservative":
            continue
        merged.append(b)
    if merged[-1] != n:
        merged.append(n)
    low = set(correction_plan.low_confidence_frames)
    segments: list[SyllableSegment] = []
    shifts = np.asarray(correction_plan.shift_cents[:n], dtype=float)
    for start, end in zip(merged, merged[1:], strict=False):
        if end <= start:
            continue
        frame_slice = np.arange(start, end)
        valid_voiced = voiced[start:end] & (probs[start:end] >= 0.5)
        low_ratio = float(sum(int(i) in low for i in frame_slice) / max(len(frame_slice), 1))
        skipped = bool((not np.any(valid_voiced)) or low_ratio > 0.4)
        reason = "low_confidence_or_unvoiced" if skipped else None
        valid_shifts = shifts[start:end][valid_voiced]
        median_shift = 0.0 if skipped or valid_shifts.size == 0 else float(np.median(valid_shifts))
        refs = [alignment.user_to_reference_map[i] for i in range(start, min(end, len(alignment.user_to_reference_map)))]
        refs_int = [int(r) for r in refs if r is not None]
        ref_start = min(refs_int) if refs_int else 0
        ref_end = max(refs_int) if refs_int else ref_start
        confidence = float(np.clip(alignment.confidence * (1.0 - low_ratio), 0.0, 1.0))
        segments.append(
            SyllableSegment(
                segment_id=len(segments),
                user_start_time=float(user_pitch.times[start]),
                user_end_time=float(user_pitch.times[min(end - 1, len(user_pitch.times) - 1)]),
                reference_start_time=float(reference_features.times[ref_start]) if ref_start < len(reference_features.times) else 0.0,
                reference_end_time=float(reference_features.times[ref_end]) if ref_end < len(reference_features.times) else 0.0,
                user_frame_start=int(start),
                user_frame_end=int(end),
                reference_frame_start=int(ref_start),
                reference_frame_end=int(ref_end),
                median_shift_cents=median_shift,
                confidence=confidence,
                skipped=skipped,
                skipped_reason=reason,
            )
        )
    return segments


def _resize(values, length: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if len(arr) >= length:
        return np.nan_to_num(arr[:length])
    out = np.zeros(length, dtype=float)
    out[: len(arr)] = np.nan_to_num(arr)
    return out


def _zscore(values: np.ndarray) -> np.ndarray:
    std = float(np.std(values))
    if std <= 1e-8:
        return values * 0.0
    return (values - float(np.mean(values))) / std
