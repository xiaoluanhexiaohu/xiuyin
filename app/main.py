"""FastAPI application for local-path offline audio correction MVP."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException

from app.schemas import AlignRequest, AnalyzeRequest, CorrectRequest, ExportJobRequest
from core.aligner import align_features
from core.audio_io import load_audio
from core.correction_planner import create_correction_plan
from core.feature_extractor import extract_features
from core.pitch_tracker import analyze_array
from jobs.batch_export import run_job

app = FastAPI(title="Auto Tune MVP", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""

    return {"status": "ok"}


@app.post("/analyze/reference")
def analyze_reference(request: AnalyzeRequest) -> dict:
    """Analyze a reference audio path."""

    return _analyze(request.audio_path)


@app.post("/analyze/user")
def analyze_user(request: AnalyzeRequest) -> dict:
    """Analyze a user audio path."""

    return _analyze(request.audio_path)


@app.post("/align")
def align(request: AlignRequest) -> dict:
    """Align local reference and user audio paths."""

    try:
        alignment = _alignment_for_paths(request.reference_audio, request.user_audio)
        return {
            "confidence": alignment.confidence,
            "distance": alignment.distance,
            "low_confidence_segments": [asdict(s) for s in alignment.low_confidence_segments],
            "warnings": alignment.warnings,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/correct")
def correct(request: CorrectRequest) -> dict:
    """Create and return a correction-plan summary for two local audio paths."""

    try:
        ref_audio = load_audio(request.reference_audio, normalize=True)
        user_audio = load_audio(request.user_audio, target_sr=ref_audio.sr, normalize=True)
        ref_pitch = analyze_array(ref_audio.y, ref_audio.sr)
        user_pitch = analyze_array(user_audio.y, user_audio.sr)
        alignment = _alignment_for_arrays(ref_audio.y, user_audio.y, ref_audio.sr, user_pitch.hop_length)
        plan = create_correction_plan(
            user_pitch,
            ref_pitch,
            alignment,
            request.params.correction_strength,
            request.params.keep_vibrato_ratio,
            request.params.max_shift_cents,
        )
        return {
            "correction_strength": plan.correction_strength,
            "keep_vibrato_ratio": plan.keep_vibrato_ratio,
            "max_shift_cents": plan.max_shift_cents,
            "low_confidence_frame_count": len(plan.low_confidence_frames),
            "warnings": plan.warnings,
            "preview": {
                "times": plan.times[:20],
                "target_f0_hz": plan.target_f0_hz[:20],
                "shift_cents": plan.shift_cents[:20],
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/export")
def export(request: ExportJobRequest) -> dict:
    """Run a full offline export job using local paths."""

    try:
        return run_job(
            {
                "id": request.id,
                "reference_audio": request.reference_audio,
                "user_audio": request.user_audio,
                "accompaniment_audio": request.accompaniment_audio,
                "output_dir": request.output_dir,
                "params": request.params.model_dump() if hasattr(request.params, "model_dump") else request.params.dict(),
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _analyze(path: str) -> dict:
    try:
        audio = load_audio(path, normalize=True)
        pitch = analyze_array(audio.y, audio.sr)
        voiced = sum(1 for flag in pitch.voiced_flag if flag)
        return {
            "path": path,
            "sample_rate": audio.sr,
            "duration": audio.duration,
            "pitch_method": pitch.method,
            "frame_count": len(pitch.times),
            "voiced_frame_count": voiced,
            "preview": pitch.to_dict() | {"times": pitch.times[:20], "f0_hz": pitch.f0_hz[:20]},
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _alignment_for_paths(reference_audio: str, user_audio: str):
    ref_audio = load_audio(reference_audio, normalize=True)
    usr_audio = load_audio(user_audio, target_sr=ref_audio.sr, normalize=True)
    return _alignment_for_arrays(ref_audio.y, usr_audio.y, ref_audio.sr, 512)


def _alignment_for_arrays(ref_y, user_y, sr: int, hop_length: int):
    ref_features = extract_features(ref_y, sr, hop_length=hop_length)
    user_features = extract_features(user_y, sr, hop_length=hop_length)
    return align_features(ref_features, user_features)
