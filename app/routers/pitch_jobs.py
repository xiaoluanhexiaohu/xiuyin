"""Task-style API for one-click pitch-correction jobs."""

from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.audio_registry import load_registered_audio
from app.auth import get_current_user
from app.schemas import PitchCorrectionJobCreateRequest, PitchCorrectionJobResponse
from app.users import User, hash_user_sub
from core.segment_locator import locate_reference_segment
from jobs.paths import create_job_layout, web_jobs_root, write_job_index
from jobs.status import initial_status, load_job_for_user, mark_failed, read_status, update_status, write_status
from jobs.web_export import process_web_job

router = APIRouter(prefix="/api/v1/pitch-correction/jobs", tags=["pitch-correction"])


def _audio_path_for(owner_sub: str, audio_id: str) -> Path:
    """Resolve an owner-scoped upload/import audio id to a normalized WAV path."""

    metadata = load_registered_audio(owner_sub, audio_id)
    if metadata and metadata.get("normalized_path"):
        registered_path = Path(str(metadata["normalized_path"]))
        if registered_path.exists():
            return registered_path
    legacy_path = web_jobs_root() / hash_user_sub(owner_sub) / "audio" / audio_id / "normalized.wav"
    if legacy_path.exists():
        return legacy_path
    raise HTTPException(status_code=404, detail={"error_code": "AUDIO_NOT_FOUND", "audio_id": audio_id})


@router.post("", response_model=PitchCorrectionJobResponse)
def create_pitch_job(
    request: PitchCorrectionJobCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> PitchCorrectionJobResponse:
    """Create and run a local offline pitch-correction job.

    This MVP implementation persists ``queued`` then ``running`` states and runs
    inline; the same status document can be moved to RQ later without changing
    the public API shape.
    """

    job_id = uuid.uuid4().hex
    user_hash = hash_user_sub(current_user.sub)
    root = create_job_layout(user_hash, job_id)
    options = request.options.model_dump()
    status = initial_status(job_id, current_user.sub, options)
    status.update(
        api_version="v1",
        inputs={"reference_audio_id": request.reference_audio_id, "user_audio_id": request.user_audio_id},
        metrics={},
        artifacts={},
        step_timings={},
    )
    write_status(root, status)
    write_job_index(job_id, user_hash)
    started = time.perf_counter()
    try:
        ref_path = _audio_path_for(current_user.sub, request.reference_audio_id)
        user_path = _audio_path_for(current_user.sub, request.user_audio_id)
        if options.get("auto_locate_segment", True):
            seg_start = time.perf_counter()
            match = locate_reference_segment(ref_path, user_path)
            update_status(root, segment_match=match.to_dict(), step_timings={"segment_locator_sec": time.perf_counter() - seg_start})
            if match.needs_confirmation:
                status_doc = update_status(
                    root,
                    status="needs_confirmation",
                    stage="align",
                    progress=0.2,
                    message="自动定位片段置信度较低，需要用户确认。",
                    warnings=match.warnings,
                    error_code="SEGMENT_NEEDS_CONFIRMATION",
                )
                return _response(job_id, status_doc)
        inputs = root / "inputs"
        shutil.copyfile(ref_path, inputs / "reference_audio.original.wav")
        shutil.copyfile(user_path, inputs / "user_audio.original.wav")
        result = process_web_job(user_hash, job_id)
        status_doc = read_status(root)
        if not result.get("ok"):
            status_doc = mark_failed(root, "处理失败", str(result.get("error", "UNKNOWN_ERROR")))
            status_doc["error_code"] = "PITCH_JOB_FAILED"
            write_status(root, status_doc)
        else:
            status_doc = read_status(root)
            status_doc["status"] = "succeeded"
            status_doc["message"] = "处理完成"
            status_doc["step_timings"] = {**status_doc.get("step_timings", {}), "total_sec": time.perf_counter() - started}
            status_doc["artifacts"] = {
                "corrected_vocal": f"/download/{job_id}/corrected_vocal.wav",
                "mix": f"/download/{job_id}/mix.wav",
                "report": f"/download/{job_id}/report.json",
                "bundle": f"/download/{job_id}/bundle.zip",
            }
            write_status(root, status_doc)
        return _response(job_id, status_doc)
    except HTTPException:
        raise
    except Exception as exc:
        status_doc = mark_failed(root, "处理失败", str(exc))
        status_doc["error_code"] = "PITCH_JOB_FAILED"
        write_status(root, status_doc)
        return _response(job_id, status_doc)


@router.get("/{job_id}", response_model=PitchCorrectionJobResponse)
def get_pitch_job(job_id: str, current_user: Annotated[User, Depends(get_current_user)]) -> PitchCorrectionJobResponse:
    """Return one pitch-correction job status for its owner."""

    _, status_doc = load_job_for_user(job_id, current_user.sub)
    return _response(job_id, status_doc)


@router.get("/{job_id}/artifacts")
def get_pitch_job_artifacts(job_id: str, current_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    """Return artifact links for a completed/succeeded job."""

    _, status_doc = load_job_for_user(job_id, current_user.sub)
    if status_doc.get("status") not in {"completed", "succeeded"}:
        raise HTTPException(status_code=409, detail={"error_code": "JOB_NOT_READY"})
    return status_doc.get("artifacts") or {
        "corrected_vocal": f"/download/{job_id}/corrected_vocal.wav",
        "mix": f"/download/{job_id}/mix.wav",
        "report": f"/download/{job_id}/report.json",
        "bundle": f"/download/{job_id}/bundle.zip",
    }


def _response(job_id: str, status_doc: dict[str, Any]) -> PitchCorrectionJobResponse:
    raw_status = status_doc.get("status", "queued")
    public_status = "succeeded" if raw_status == "completed" else raw_status
    return PitchCorrectionJobResponse(
        job_id=job_id,
        status=public_status,
        inputs=status_doc.get("inputs", {}),
        segment_match=status_doc.get("segment_match"),
        options=status_doc.get("options", {}),
        artifacts=status_doc.get("artifacts", {}),
        metrics=status_doc.get("metrics", {}),
        warnings=status_doc.get("warnings", []),
        step_timings=status_doc.get("step_timings", {}),
        error_code=status_doc.get("error_code"),
        message=status_doc.get("message", ""),
    )
