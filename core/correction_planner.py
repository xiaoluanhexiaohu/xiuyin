"""Conservative pitch correction planning in log-pitch/cents space."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.ndimage import median_filter

from core.aligner import AlignmentResult
from core.pitch_tracker import PitchTrack


@dataclass
class CorrectionPlan:
    """A JSON-friendly offline pitch correction plan."""

    times: list[float]
    original_f0_hz: list[float | None]
    reference_f0_hz: list[float | None]
    target_f0_hz: list[float | None]
    shift_cents: list[float]
    correction_strength: float
    keep_vibrato_ratio: float
    max_shift_cents: float
    low_confidence_frames: list[int]
    warnings: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""

        return self.__dict__.copy()


def create_correction_plan(
    user_pitch: PitchTrack,
    reference_pitch: PitchTrack,
    alignment: AlignmentResult,
    correction_strength: float = 0.75,
    keep_vibrato_ratio: float = 0.6,
    max_shift_cents: float = 300.0,
    voiced_prob_threshold: float = 0.5,
    trend_filter_size: int = 9,
) -> CorrectionPlan:
    """Create a target F0 contour that corrects trend while preserving expression."""

    strength = float(np.clip(correction_strength, 0.0, 1.0))
    vibrato = float(np.clip(keep_vibrato_ratio, 0.0, 1.0))
    max_shift = abs(float(max_shift_cents))
    user_f0 = _to_float_array(user_pitch.f0_hz)
    ref_f0 = _to_float_array(reference_pitch.f0_hz)
    user_prob = _resize_or_pad(user_pitch.voiced_prob, len(user_f0), 0.0)
    user_voiced = np.asarray(user_pitch.voiced_flag, dtype=bool)
    if len(user_voiced) != len(user_f0):
        user_voiced = np.isfinite(user_f0) & (user_f0 > 0)

    warnings: list[str] = list(alignment.warnings)
    target = np.full(len(user_f0), np.nan, dtype=float)
    shift_cents = np.zeros(len(user_f0), dtype=float)
    ref_for_user = np.full(len(user_f0), np.nan, dtype=float)
    low_conf_frames: list[int] = []
    clipped_count = 0
    skipped_unvoiced = 0
    skipped_low_prob = 0
    skipped_alignment = 0

    log_user = np.where(user_f0 > 0, np.log2(user_f0), np.nan)
    trend = _smooth_log_pitch(log_user, trend_filter_size)
    residual = np.where(np.isfinite(log_user) & np.isfinite(trend), log_user - trend, 0.0)

    for i in range(len(user_f0)):
        if not user_voiced[i] or not np.isfinite(user_f0[i]) or user_f0[i] <= 0:
            skipped_unvoiced += 1
            continue
        if user_prob[i] < voiced_prob_threshold:
            low_conf_frames.append(i)
            skipped_low_prob += 1
            target[i] = user_f0[i]
            continue
        ref_idx = alignment.user_to_reference_map[i] if i < len(alignment.user_to_reference_map) else None
        if ref_idx is None or ref_idx < 0 or ref_idx >= len(ref_f0) or not np.isfinite(ref_f0[ref_idx]):
            low_conf_frames.append(i)
            skipped_alignment += 1
            target[i] = user_f0[i]
            continue
        ref_for_user[i] = ref_f0[ref_idx]
        raw_shift = 1200.0 * np.log2(ref_f0[ref_idx] / user_f0[i]) * strength
        clipped_shift = float(np.clip(raw_shift, -max_shift, max_shift))
        if abs(raw_shift - clipped_shift) > 1e-6:
            clipped_count += 1
        shift_cents[i] = clipped_shift
        target_log = trend[i] + clipped_shift / 1200.0 + residual[i] * vibrato
        if strength == 0.0:
            target[i] = float(user_f0[i])
        elif np.isfinite(target_log):
            target[i] = float(2.0**target_log)
        else:
            target[i] = user_f0[i]

    if clipped_count:
        warnings.append(f"Clipped {clipped_count} frames to max_shift_cents={max_shift}.")
    if skipped_low_prob:
        warnings.append(f"Skipped {skipped_low_prob} low voiced-probability frames.")
    if skipped_alignment:
        warnings.append(f"Skipped {skipped_alignment} frames with missing/invalid alignment.")
    if len(user_f0) == 0:
        warnings.append("User pitch track is empty.")
    if len(ref_f0) == 0:
        warnings.append("Reference pitch track is empty.")

    return CorrectionPlan(
        times=[float(t) for t in user_pitch.times[: len(user_f0)]],
        original_f0_hz=_to_optional_list(user_f0),
        reference_f0_hz=_to_optional_list(ref_for_user),
        target_f0_hz=_to_optional_list(target),
        shift_cents=[float(v) for v in shift_cents],
        correction_strength=strength,
        keep_vibrato_ratio=vibrato,
        max_shift_cents=max_shift,
        low_confidence_frames=sorted(set(int(i) for i in low_conf_frames)),
        warnings=warnings,
        metadata={
            "voiced_prob_threshold": float(voiced_prob_threshold),
            "trend_filter_size": int(trend_filter_size),
            "skipped_unvoiced_frames": int(skipped_unvoiced),
            "skipped_low_probability_frames": int(skipped_low_prob),
            "skipped_alignment_frames": int(skipped_alignment),
            "clipped_frames": int(clipped_count),
        },
    )


def cents_difference(reference_hz: float, user_hz: float) -> float:
    """Return pitch difference in cents from user pitch to reference pitch."""

    if reference_hz <= 0 or user_hz <= 0:
        raise ValueError("Frequencies must be positive to compute cents difference")
    return float(1200.0 * np.log2(reference_hz / user_hz))


def _to_float_array(values: list[float | None]) -> np.ndarray:
    return np.asarray([np.nan if v is None else float(v) for v in values], dtype=float)


def _to_optional_list(values: np.ndarray) -> list[float | None]:
    return [float(v) if np.isfinite(v) and v > 0 else None for v in values]


def _resize_or_pad(values: list[float], length: int, fill: float) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if len(arr) >= length:
        return np.nan_to_num(arr[:length], nan=fill)
    out = np.full(length, fill, dtype=float)
    out[: len(arr)] = np.nan_to_num(arr, nan=fill)
    return out


def _smooth_log_pitch(log_pitch: np.ndarray, filter_size: int) -> np.ndarray:
    """Median-smooth log pitch while filling unvoiced gaps from nearby voiced frames."""

    if len(log_pitch) == 0:
        return log_pitch.copy()
    valid = np.isfinite(log_pitch)
    if not np.any(valid):
        return np.full_like(log_pitch, np.nan)
    idx = np.arange(len(log_pitch))
    filled = np.interp(idx, idx[valid], log_pitch[valid])
    size = max(3, int(filter_size) | 1)
    return median_filter(filled, size=size, mode="nearest")
