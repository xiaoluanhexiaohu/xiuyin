"""Worker-side processing for uploaded web correction jobs."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

from core.aligner import align_partial_features
from core.audio_io import load_audio, normalize_uploaded_audio
from core.correction_planner import create_correction_plan
from core.feature_extractor import extract_features
from core.mixer import mix_audio
from core.pitch_tracker import analyze_array
from core.renderer import render_corrected_vocal
from core.report import build_web_report, write_report
from core.segmenter import segment_syllables
from jobs.paths import job_dir
from jobs.status import mark_completed, mark_failed, mark_started, read_status, update_status
from services.source_separation import separate_reference_audio


def process_web_job(user_hash: str, job_id: str) -> dict[str, Any]:
    """Process one uploaded job and generate the required artifacts."""

    root = job_dir(user_hash, job_id)
    warnings: list[str] = []
    try:
        status = mark_started(root)
        options = status.get("options", {})
        inputs = root / "inputs"
        staging = root / "staging"
        artifacts = root / "artifacts"
        ref_original = _first_existing(inputs, "reference_audio.original")
        user_original = _first_existing(inputs, "user_audio.original")

        update_status(root, stage="normalize", progress=0.1, message="正在转换音频格式")
        ref_wav = staging / "reference.wav"
        user_wav = staging / "user.wav"
        normalize_uploaded_audio(ref_original, ref_wav)
        normalize_uploaded_audio(user_original, user_wav)

        update_status(root, stage="separate", progress=0.2, message="正在分析原唱")
        separation = separate_reference_audio(
            ref_wav,
            staging,
            auto_separate_reference=bool(options.get("auto_separate_reference", True)),
        )
        warnings.extend(separation.warnings)
        reference_for_analysis = Path(separation.vocals_path) if separation.vocals_path else ref_wav
        accompaniment = Path(separation.accompaniment_path) if separation.accompaniment_path else None

        update_status(root, stage="analyze", progress=0.4, message="正在分析你的录音", warnings=warnings)
        reference = load_audio(reference_for_analysis, normalize=True)
        user = load_audio(user_wav, target_sr=reference.sr, normalize=True)
        reference_pitch = analyze_array(reference.y, reference.sr)
        user_pitch = analyze_array(user.y, user.sr)
        reference_features = extract_features(reference.y, reference.sr, hop_length=user_pitch.hop_length)
        user_features = extract_features(user.y, user.sr, hop_length=user_pitch.hop_length)

        update_status(root, stage="align", progress=0.55, message="正在匹配原唱片段")
        alignment = align_partial_features(reference_features, user_features)
        warnings.extend(alignment.warnings)

        update_status(root, stage="segment", progress=0.68, message="正在按音节生成修音计划", warnings=warnings)
        plan = create_correction_plan(
            user_pitch,
            reference_pitch,
            alignment,
            correction_strength=float(options.get("correction_strength", 0.75)),
            keep_vibrato_ratio=float(options.get("keep_vibrato_ratio", 0.6)),
            max_shift_cents=float(options.get("max_shift_cents", 300.0)),
        )
        granularity = str(options.get("syllable_granularity", "conservative"))
        if granularity == "aggressive":
            warnings.append("细致分段可能产生不自然效果。")
        try:
            segments = segment_syllables(
                user_pitch,
                reference_pitch,
                user_features,
                reference_features,
                alignment,
                plan,
                granularity if granularity in {"conservative", "normal", "aggressive"} else "conservative",
            )
            if not segments:
                warnings.append("音节分段失败，已回退到连续修音计划。")
        except Exception as exc:
            segments = []
            warnings.append(f"音节分段失败，已回退到连续修音计划：{exc}")

        update_status(root, stage="render", progress=0.78, message="正在渲染修音后音频", warnings=warnings)
        corrected_path = artifacts / "corrected_vocal.wav"
        render = render_corrected_vocal(user_wav, plan, corrected_path, segments)
        warnings.extend(render.warnings)

        update_status(root, stage="mix", progress=0.86, message="正在混音", warnings=warnings)
        mix = mix_audio(corrected_path, accompaniment, artifacts / "mix.wav")
        warnings.extend(mix.warnings)

        update_status(root, stage="package", progress=0.95, message="正在打包下载文件", warnings=warnings)
        current_status = read_status(root)
        completed_preview = current_status.get("completed_at") or ""
        expires_preview = current_status.get("expires_at") or ""
        report = build_web_report(
            job_id=job_id,
            user=str(current_status["owner_sub"]),
            reference_audio_name=Path(ref_original).name,
            user_audio_name=Path(user_original).name,
            reference_was_separated=separation.separated,
            alignment_result=alignment,
            correction_plan=plan,
            segments=segments,
            syllable_granularity=granularity,
            render_result=render,
            mix_result=mix,
            warnings=warnings,
            created_at=str(current_status.get("created_at", "")),
            completed_at=completed_preview,
            expires_at=expires_preview,
        )
        report_path = write_report(report, artifacts / "report.json")
        _write_bundle(artifacts)
        final_status = mark_completed(root, render.actual_pitch_shift_applied)
        report["completed_at"] = final_status["completed_at"]
        report["expires_at"] = final_status["expires_at"]
        write_report(report, report_path)
        _write_bundle(artifacts)
        _remove_private_inputs(root)
        update_status(root, warnings=warnings)
        return {"job_id": job_id, "ok": True}
    except Exception as exc:
        mark_failed(root, "处理失败", str(exc))
        return {"job_id": job_id, "ok": False, "error": str(exc)}


def _first_existing(directory: Path, prefix: str) -> Path:
    matches = sorted(directory.glob(f"{prefix}*"))
    if not matches:
        raise FileNotFoundError(f"缺少上传文件：{prefix}")
    return matches[0]


def _write_bundle(artifacts: Path) -> Path:
    bundle = artifacts / "bundle.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in ["corrected_vocal.wav", "mix.wav", "report.json"]:
            zf.write(artifacts / name, arcname=name)
    return bundle


def _remove_private_inputs(root: Path) -> None:
    shutil.rmtree(root / "inputs", ignore_errors=True)
    shutil.rmtree(root / "staging", ignore_errors=True)
