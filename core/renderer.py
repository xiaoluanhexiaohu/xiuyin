"""Compatibility renderer that delegates to the real plan-driven pitch renderer."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import util
from pathlib import Path

from core.correction_planner import CorrectionPlan
from core.pitch_renderer import PitchRenderResult, render_pitch_corrected_vocal
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
    metadata: dict[str, object] | None = None

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
    """Render corrected vocals using the real pitch plan instead of copying audio.

    ``segments`` is accepted for backward compatibility with older callers. The
    renderer now consumes frame-level ``CorrectionPlan`` data directly so it can
    skip low-confidence/unvoiced frames even when syllable segmentation is absent.
    """

    result: PitchRenderResult = render_pitch_corrected_vocal(
        input_vocal,
        correction_plan,
        output_path,
        metadata_path=Path(output_path).with_suffix(".render.json"),
    )
    return RenderResult(
        output_path=result.output_path,
        renderer=result.renderer,
        actual_pitch_shift_applied=result.actual_pitch_shift_applied,
        metadata_path=result.metadata_path,
        warnings=result.warnings,
        warning=result.warning,
        metadata=result.metadata,
    )
