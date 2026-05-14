"""Placeholder vocal renderer for the MVP correction plan."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.audio_io import load_audio, write_wav
from core.correction_planner import CorrectionPlan


@dataclass
class RenderResult:
    """Result of rendering corrected vocals."""

    output_path: str
    renderer: str
    actual_pitch_shift_applied: bool
    metadata_path: str | None
    warnings: list[str]


def render_corrected_vocal(
    input_vocal: str | Path,
    correction_plan: CorrectionPlan,
    output_path: str | Path,
) -> RenderResult:
    """Write a placeholder corrected vocal while preserving future renderer API shape."""

    audio = load_audio(input_vocal, normalize=True)
    write_wav(output_path, audio.y, audio.sr, normalize=False)
    warnings = [
        "Placeholder renderer: no actual pitch shifting was applied. Use correction plan metadata for future rendering."
    ]
    warnings.extend(correction_plan.warnings)
    return RenderResult(str(output_path), "placeholder", False, None, warnings)
