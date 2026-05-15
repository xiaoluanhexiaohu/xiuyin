"""Lightweight plan-driven pitch renderer for offline vocal correction.

This module intentionally avoids neural timbre transfer and only applies conservative
DSP pitch shifts to confident voiced regions described by ``CorrectionPlan``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from core.audio_io import load_audio, write_wav
from core.correction_planner import CorrectionPlan


@dataclass
class PitchRenderMetadata:
    """Metadata describing what the renderer actually applied."""

    actual_pitch_shift_applied: bool
    mean_abs_shift_cents: float
    skipped_frames: int
    render_time_ms: float
    warnings: list[str] = field(default_factory=list)
    applied_regions: int = 0


@dataclass
class PitchRenderResult:
    """Result returned by the plan-driven pitch renderer."""

    output_path: str
    renderer: str
    actual_pitch_shift_applied: bool
    metadata_path: str | None
    warnings: list[str]
    metadata: dict[str, object]
    warning: str | None = None

    @property
    def render_backend(self) -> str:
        """Alias used by report builders."""

        return self.renderer


def render_pitch_corrected_vocal(
    input_vocal: str | Path,
    correction_plan: CorrectionPlan,
    output_path: str | Path,
    *,
    metadata_path: str | Path | None = None,
    min_shift_cents: float = 5.0,
    confidence_padding_frames: int = 1,
) -> PitchRenderResult:
    """Render a corrected vocal by shifting only confident voiced plan regions.

    The implementation groups consecutive frames with usable ``shift_cents`` values,
    applies one median shift per region, preserves the original number of samples,
    and crossfades region boundaries to reduce clicks. Unvoiced, silent, and
    low-confidence frames remain untouched.
    """

    started = time.perf_counter()
    audio = load_audio(input_vocal, normalize=True)
    y = np.nan_to_num(np.asarray(audio.y, dtype=np.float32))
    rendered = y.copy()
    warnings = list(correction_plan.warnings)

    shifts = np.asarray(correction_plan.shift_cents, dtype=float)
    frame_count = int(shifts.size)
    low_conf = set(int(i) for i in correction_plan.low_confidence_frames)
    if confidence_padding_frames > 0 and low_conf:
        padded: set[int] = set()
        for idx in low_conf:
            padded.update(range(idx - confidence_padding_frames, idx + confidence_padding_frames + 1))
        low_conf = {i for i in padded if 0 <= i < frame_count}

    original_f0 = _optional_array(correction_plan.original_f0_hz, frame_count)
    target_f0 = _optional_array(correction_plan.target_f0_hz, frame_count)
    times = np.asarray(correction_plan.times[:frame_count], dtype=float)
    if times.size < frame_count:
        step = _infer_frame_step(times)
        start = float(times[-1] + step) if times.size else 0.0
        times = np.concatenate([times, start + step * np.arange(frame_count - times.size)])

    usable = (
        np.isfinite(shifts)
        & (np.abs(shifts) >= float(min_shift_cents))
        & np.isfinite(original_f0)
        & (original_f0 > 0)
        & np.isfinite(target_f0)
        & (target_f0 > 0)
    )
    for idx in low_conf:
        if 0 <= idx < frame_count:
            usable[idx] = False

    regions = _contiguous_regions(usable)
    applied_shifts: list[float] = []
    skipped_frames = int(frame_count - int(np.sum(usable)))
    fade = max(8, int(audio.sr * 0.012))
    frame_step = _infer_frame_step(times)
    for start_frame, end_frame in regions:
        median_shift = float(np.median(shifts[start_frame:end_frame]))
        start_sample = max(0, int(round(times[start_frame] * audio.sr)))
        end_time = float(times[end_frame - 1] + frame_step)
        end_sample = min(len(y), int(round(end_time * audio.sr)))
        if end_sample - start_sample < max(64, fade * 2):
            skipped_frames += end_frame - start_frame
            continue
        chunk = y[start_sample:end_sample]
        shifted = _pitch_shift_preserve_length(chunk, median_shift)
        shifted = _peak_match(chunk, shifted)
        rendered[start_sample:end_sample] = _crossfade_replace(
            rendered[start_sample:end_sample], shifted, min(fade, len(chunk) // 2)
        )
        applied_shifts.extend(abs(float(v)) for v in shifts[start_frame:end_frame] if np.isfinite(v))

    if not applied_shifts:
        warnings.append("No confident voiced pitch-shift regions were applied; audio was copied unchanged.")
    render_time_ms = (time.perf_counter() - started) * 1000.0
    actual = bool(applied_shifts)
    metadata = PitchRenderMetadata(
        actual_pitch_shift_applied=actual,
        mean_abs_shift_cents=float(np.mean(applied_shifts)) if applied_shifts else 0.0,
        skipped_frames=int(skipped_frames),
        render_time_ms=float(render_time_ms),
        warnings=warnings,
        applied_regions=len(regions) if actual else 0,
    )
    write_wav(output_path, rendered, audio.sr, normalize=True)
    meta_dict = metadata.__dict__.copy()
    meta_path: str | None = None
    if metadata_path is None:
        metadata_path = Path(output_path).with_suffix(".render.json")
    if metadata_path:
        path = Path(metadata_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta_dict, ensure_ascii=False, indent=2), encoding="utf-8")
        meta_path = str(path)
    return PitchRenderResult(
        output_path=str(output_path),
        renderer="scipy_resample_plan",
        actual_pitch_shift_applied=actual,
        metadata_path=meta_path,
        warnings=warnings,
        metadata=meta_dict,
        warning=None if actual else "No confident voiced pitch-shift regions were applied.",
    )


def _optional_array(values: list[float | None], length: int) -> np.ndarray:
    arr = np.asarray([np.nan if v is None else float(v) for v in values[:length]], dtype=float)
    if arr.size >= length:
        return arr
    out = np.full(length, np.nan, dtype=float)
    out[: arr.size] = arr
    return out


def _infer_frame_step(times: np.ndarray) -> float:
    if times.size >= 2:
        diffs = np.diff(times)
        diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
        if diffs.size:
            return float(np.median(diffs))
    return 512.0 / 44100.0


def _contiguous_regions(mask: np.ndarray) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    start: int | None = None
    for idx, value in enumerate(mask):
        if bool(value) and start is None:
            start = idx
        elif not bool(value) and start is not None:
            regions.append((start, idx))
            start = None
    if start is not None:
        regions.append((start, len(mask)))
    return regions


def _pitch_shift_preserve_length(chunk: np.ndarray, cents: float) -> np.ndarray:
    if abs(cents) < 1e-6 or chunk.size == 0:
        return chunk.astype(np.float32, copy=True)
    factor = float(2.0 ** (cents / 1200.0))
    up = max(1, int(round(factor * 1000)))
    down = 1000
    shifted_rate = resample_poly(chunk, up, down).astype(np.float32)
    if shifted_rate.size < 2:
        return chunk.astype(np.float32, copy=True)
    x_old = np.linspace(0.0, 1.0, shifted_rate.size, endpoint=True)
    x_new = np.linspace(0.0, 1.0, chunk.size, endpoint=True)
    return np.interp(x_new, x_old, shifted_rate).astype(np.float32)


def _peak_match(original: np.ndarray, shifted: np.ndarray) -> np.ndarray:
    orig_peak = float(np.max(np.abs(original))) if original.size else 0.0
    new_peak = float(np.max(np.abs(shifted))) if shifted.size else 0.0
    if orig_peak <= 1e-8 or new_peak <= 1e-8:
        return shifted.astype(np.float32)
    return (shifted * min(2.0, orig_peak / new_peak)).astype(np.float32)


def _crossfade_replace(original: np.ndarray, shifted: np.ndarray, fade: int) -> np.ndarray:
    out = shifted.astype(np.float32, copy=True)
    fade = min(int(fade), len(out) // 2)
    if fade <= 0:
        return out
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    out[:fade] = original[:fade] * (1.0 - ramp) + shifted[:fade] * ramp
    out[-fade:] = shifted[-fade:] * (1.0 - ramp) + original[-fade:] * ramp
    return out
