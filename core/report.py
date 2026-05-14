"""Report generation for offline correction exports."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.correction_planner import CorrectionPlan

ALGORITHM_VERSION = "offline-mvp-0.1"


def build_report(
    job_metadata: dict[str, Any],
    pitch_methods: dict[str, str],
    alignment_result: Any,
    correction_plan: CorrectionPlan,
    render_result: Any,
    mix_result: Any,
    timings: dict[str, float],
    warnings: list[str],
) -> dict[str, Any]:
    """Build a JSON-friendly processing report."""

    shifts = np.asarray(correction_plan.shift_cents, dtype=float)
    nonzero = shifts[np.abs(shifts) > 1e-9]
    stats = {
        "mean_abs_shift_cents": float(np.mean(np.abs(nonzero))) if nonzero.size else 0.0,
        "max_abs_shift_cents": float(np.max(np.abs(nonzero))) if nonzero.size else 0.0,
        "corrected_frame_count": int(nonzero.size),
        "low_confidence_frame_count": int(len(correction_plan.low_confidence_frames)),
    }
    low_segments = [_asdict(s) for s in getattr(alignment_result, "low_confidence_segments", [])]
    all_warnings = []
    for source in [warnings, getattr(alignment_result, "warnings", []), correction_plan.warnings, getattr(render_result, "warnings", []), getattr(mix_result, "warnings", [])]:
        all_warnings.extend(str(w) for w in source)
    return {
        "job": job_metadata,
        "algorithm_version": ALGORITHM_VERSION,
        "pitch_methods": pitch_methods,
        "alignment": {
            "confidence": float(getattr(alignment_result, "confidence", 0.0)),
            "distance": float(getattr(alignment_result, "distance", 0.0)),
            "low_confidence_segments": low_segments,
        },
        "pitch_deviation": stats,
        "correction": {
            "correction_strength": correction_plan.correction_strength,
            "keep_vibrato_ratio": correction_plan.keep_vibrato_ratio,
            "max_shift_cents": correction_plan.max_shift_cents,
            "metadata": correction_plan.metadata,
            "preview": {
                "times": correction_plan.times[:20],
                "original_f0_hz": correction_plan.original_f0_hz[:20],
                "reference_f0_hz": correction_plan.reference_f0_hz[:20],
                "target_f0_hz": correction_plan.target_f0_hz[:20],
                "shift_cents": correction_plan.shift_cents[:20],
            },
        },
        "render": _asdict(render_result),
        "mix": _asdict(mix_result),
        "timings_sec": {k: float(v) for k, v in timings.items()},
        "warnings": sorted(set(all_warnings)),
    }


def build_web_report(
    *,
    job_id: str,
    user: str,
    reference_audio_name: str,
    user_audio_name: str,
    reference_was_separated: bool,
    alignment_result: Any,
    correction_plan: CorrectionPlan,
    segments: list[Any],
    syllable_granularity: str,
    render_result: Any,
    mix_result: Any,
    warnings: list[str],
    created_at: str,
    completed_at: str,
    expires_at: str,
) -> dict[str, Any]:
    """Build the Chinese upload-web MVP report structure."""

    low_segments = [_asdict(s) for s in getattr(alignment_result, "low_confidence_segments", [])]
    render_warning = getattr(render_result, "warning", None)
    all_warnings = []
    for source in [
        warnings,
        getattr(alignment_result, "warnings", []),
        correction_plan.warnings,
        getattr(render_result, "warnings", []),
        getattr(mix_result, "warnings", []),
    ]:
        all_warnings.extend(str(w) for w in source if w)
    return {
        "job_id": job_id,
        "user": user,
        "input": {
            "reference_audio": reference_audio_name,
            "user_audio": user_audio_name,
            "reference_was_separated": bool(reference_was_separated),
            "partial_match": bool(getattr(alignment_result, "partial_match", False)),
        },
        "limits": {"max_file_size_mb": 100, "max_duration_seconds": 600},
        "alignment": {
            "partial_match": bool(getattr(alignment_result, "partial_match", False)),
            "matched_reference_start_time": float(getattr(alignment_result, "matched_reference_start_time", 0.0)),
            "matched_reference_end_time": float(getattr(alignment_result, "matched_reference_end_time", 0.0)),
            "alignment_confidence": float(getattr(alignment_result, "confidence", 0.0)),
            "low_confidence_segments": low_segments,
        },
        "correction": {
            "mode": "syllable_approx",
            "syllable_granularity": syllable_granularity,
            "correction_strength": correction_plan.correction_strength,
            "keep_vibrato_ratio": correction_plan.keep_vibrato_ratio,
            "max_shift_cents": correction_plan.max_shift_cents,
            "segment_count": len(segments),
            "skipped_segment_count": sum(1 for s in segments if getattr(s, "skipped", False)),
        },
        "render": {
            "actual_pitch_shift_applied": bool(getattr(render_result, "actual_pitch_shift_applied", False)),
            "render_backend": getattr(render_result, "renderer", "placeholder"),
            "warning": render_warning,
        },
        "mix": {"mix_mode": getattr(mix_result, "mix_mode", "vocal_only")},
        "outputs": {
            "corrected_vocal": "corrected_vocal.wav",
            "mix": "mix.wav",
            "report": "report.json",
            "bundle": "bundle.zip",
        },
        "warnings": sorted(set(all_warnings)),
        "created_at": created_at,
        "completed_at": completed_at,
        "expires_at": expires_at,
    }


def write_report(report: dict[str, Any], output_path: str | Path) -> Path:
    """Write a report dictionary to JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _asdict(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value
