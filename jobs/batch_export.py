"""Offline batch export CLI for one-click correction MVP."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from core.aligner import align_features
from core.audio_io import audio_info, load_audio
from core.correction_planner import create_correction_plan
from core.feature_extractor import extract_features
from core.mixer import mix_audio
from core.pitch_tracker import analyze_array
from core.renderer import render_corrected_vocal
from core.report import build_report, write_report


def run_manifest(manifest_path: str | Path) -> list[dict[str, Any]]:
    """Run all jobs in a manifest and return per-job status dictionaries."""

    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Manifest must contain a 'jobs' list")
    results = []
    for job in jobs:
        try:
            results.append(run_job(job))
        except Exception as exc:
            results.append({"id": job.get("id", "unknown"), "ok": False, "error": str(exc)})
    return results


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    """Run a single local batch export job."""

    start_total = time.perf_counter()
    job_id = str(job.get("id", "job"))
    reference_path = Path(_required(job, "reference_audio"))
    user_path = Path(_required(job, "user_audio"))
    output_dir = Path(_required(job, "output_dir"))
    accompaniment = job.get("accompaniment_audio")
    params = job.get("params", {}) or {}
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    timings: dict[str, float] = {}

    t = time.perf_counter()
    reference = load_audio(reference_path, normalize=True)
    user = load_audio(user_path, target_sr=reference.sr, normalize=True)
    timings["load_audio"] = time.perf_counter() - t

    t = time.perf_counter()
    reference_pitch = analyze_array(reference.y, reference.sr)
    user_pitch = analyze_array(user.y, user.sr)
    timings["pitch_tracking"] = time.perf_counter() - t

    t = time.perf_counter()
    reference_features = extract_features(reference.y, reference.sr, hop_length=user_pitch.hop_length)
    user_features = extract_features(user.y, user.sr, hop_length=user_pitch.hop_length)
    timings["feature_extraction"] = time.perf_counter() - t

    t = time.perf_counter()
    alignment = align_features(reference_features, user_features)
    timings["alignment"] = time.perf_counter() - t

    t = time.perf_counter()
    plan = create_correction_plan(
        user_pitch,
        reference_pitch,
        alignment,
        correction_strength=float(params.get("correction_strength", 0.75)),
        keep_vibrato_ratio=float(params.get("keep_vibrato_ratio", 0.6)),
        max_shift_cents=float(params.get("max_shift_cents", 300.0)),
    )
    timings["correction_planning"] = time.perf_counter() - t

    t = time.perf_counter()
    corrected_path = output_dir / "corrected_vocal.wav"
    render = render_corrected_vocal(user_path, plan, corrected_path)
    mix = mix_audio(corrected_path, accompaniment, output_dir / "mix.wav")
    timings["render_and_mix"] = time.perf_counter() - t
    timings["total"] = time.perf_counter() - start_total

    metadata = {
        "id": job_id,
        "input_files": {
            "reference_audio": audio_info(reference_path),
            "user_audio": audio_info(user_path),
            "accompaniment_audio": str(accompaniment) if accompaniment else None,
        },
        "output_dir": str(output_dir),
        "params": params,
        "sample_rate": reference.sr,
        "duration_sec": {"reference": reference.duration, "user": user.duration},
    }
    report = build_report(
        metadata,
        {"reference": reference_pitch.method, "user": user_pitch.method},
        alignment,
        plan,
        render,
        mix,
        timings,
        warnings,
    )
    report_path = write_report(report, output_dir / "report.json")
    return {
        "id": job_id,
        "ok": True,
        "output_dir": str(output_dir),
        "corrected_vocal": str(corrected_path),
        "mix": mix.output_path,
        "report": str(report_path),
    }


def _required(job: dict[str, Any], key: str) -> str:
    value = job.get(key)
    if not value:
        raise ValueError(f"Job is missing required field: {key}")
    return str(value)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Run offline auto-tune MVP batch export")
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON")
    args = parser.parse_args(argv)
    try:
        results = run_manifest(args.manifest)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps({"results": results}, indent=2, ensure_ascii=False))
    return 0 if all(item.get("ok") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
