"""Segment-aware vocal renderer with Rubber Band and placeholder fallback."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import import_module, util
from pathlib import Path

import numpy as np

from core.audio_io import load_audio, write_wav
from core.correction_planner import CorrectionPlan
from core.segmenter import SyllableSegment

PLACEHOLDER_WARNING = "仅生成修音计划，未做真实变调"


@dataclass
class RenderResult:
    """Result of rendering corrected vocals."""

    output_path: str
    renderer: str
    actual_pitch_shift_applied: bool
    metadata_path: str | None
    warnings: list[str]
    warning: str | None = None

    @property
    def render_backend(self) -> str:
        """Alias used by the web report schema."""

        return self.renderer


def is_rubberband_available() -> bool:
    """Return whether pyrubberband and the rubberband binary are both available."""

    return util.find_spec("pyrubberband") is not None and shutil.which("rubberband") is not None


def render_corrected_vocal(
    input_vocal: str | Path,
    correction_plan: CorrectionPlan,
    output_path: str | Path,
    segments: list[SyllableSegment] | None = None,
) -> RenderResult:
    """Render corrected vocals, using Rubber Band when available."""

    if segments and is_rubberband_available():
        result = _render_with_rubberband(input_vocal, output_path, segments)
        result.warnings.extend(correction_plan.warnings)
        return result
    audio = load_audio(input_vocal, normalize=True)
    write_wav(output_path, audio.y, audio.sr, normalize=False)
    warnings = [PLACEHOLDER_WARNING, *correction_plan.warnings]
    return RenderResult(str(output_path), "placeholder", False, None, warnings, PLACEHOLDER_WARNING)


def _render_with_rubberband(
    input_vocal: str | Path,
    output_path: str | Path,
    segments: list[SyllableSegment],
) -> RenderResult:
    audio = load_audio(input_vocal, normalize=True)
    pyrubberband = import_module("pyrubberband")
    y = np.asarray(audio.y, dtype=np.float32).copy()
    rendered = y.copy()
    warnings: list[str] = []
    crossfade = max(1, int(audio.sr * 0.015))
    applied = 0
    for segment in segments:
        start = max(0, int(round(segment.user_start_time * audio.sr)))
        end = min(len(y), int(round(segment.user_end_time * audio.sr)))
        if end <= start or segment.skipped or segment.confidence < 0.35 or abs(segment.median_shift_cents) < 5:
            continue
        chunk = y[start:end]
        if len(chunk) < crossfade * 2:
            continue
        try:
            shifted = pyrubberband.pitch_shift(chunk, audio.sr, segment.median_shift_cents / 100.0)
        except Exception as exc:
            warnings.append(f"Rubber Band 处理片段失败，已保留原音频：{exc}")
            continue
        shifted = np.asarray(shifted, dtype=np.float32)
        if len(shifted) != len(chunk):
            shifted = np.interp(np.linspace(0, len(shifted) - 1, len(chunk)), np.arange(len(shifted)), shifted).astype(np.float32)
        rendered[start:end] = _crossfade_replace(rendered[start:end], shifted, crossfade)
        applied += 1
    if applied == 0:
        write_wav(output_path, y, audio.sr, normalize=False)
        warnings.append(PLACEHOLDER_WARNING)
        return RenderResult(str(output_path), "placeholder", False, None, warnings, PLACEHOLDER_WARNING)
    write_wav(output_path, rendered, audio.sr, normalize=True)
    return RenderResult(str(output_path), "rubberband", True, None, warnings, None)


def _crossfade_replace(original: np.ndarray, shifted: np.ndarray, fade: int) -> np.ndarray:
    out = shifted.copy()
    fade = min(fade, len(out) // 2)
    if fade <= 0:
        return out
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    out[:fade] = original[:fade] * (1.0 - ramp) + shifted[:fade] * ramp
    out[-fade:] = shifted[-fade:] * (1.0 - ramp) + original[-fade:] * ramp
    return out
