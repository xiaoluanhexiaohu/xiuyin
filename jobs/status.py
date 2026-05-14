"""JSON status persistence and access checks for web jobs."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from jobs.paths import find_job_dir

DOWNLOAD_TTL_SECONDS = 3600


def utc_now() -> datetime:
    """Return current UTC time."""

    return datetime.now(UTC)


def iso_now() -> str:
    """Return current UTC time in ISO format."""

    return utc_now().isoformat()


def initial_status(job_id: str, owner_sub: str, options: dict[str, Any]) -> dict[str, Any]:
    """Build an initial queued status document."""

    return {
        "job_id": job_id,
        "owner_sub": owner_sub,
        "status": "queued",
        "stage": "upload",
        "progress": 0.0,
        "message": "排队中",
        "warnings": [],
        "created_at": iso_now(),
        "started_at": None,
        "completed_at": None,
        "expires_at": None,
        "error": None,
        "options": options,
        "actual_pitch_shift_applied": False,
    }


def read_status(job_root: str | Path) -> dict[str, Any]:
    """Read a job status document."""

    return json.loads((Path(job_root) / "status.json").read_text(encoding="utf-8"))


def write_status(job_root: str | Path, status: dict[str, Any]) -> None:
    """Persist a job status document."""

    path = Path(job_root) / "status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def update_status(job_root: str | Path, **updates: Any) -> dict[str, Any]:
    """Update and persist a status document."""

    status = read_status(job_root)
    warnings = updates.pop("warnings", None)
    if warnings:
        status["warnings"] = sorted(set([*status.get("warnings", []), *[str(w) for w in warnings]]))
    status.update({k: v for k, v in updates.items() if v is not None})
    write_status(job_root, status)
    return status


def append_warning(job_root: str | Path, warning: str) -> dict[str, Any]:
    """Append one warning to a status document."""

    return update_status(job_root, warnings=[warning])


def mark_started(job_root: str | Path) -> dict[str, Any]:
    """Mark a job as running."""

    return update_status(job_root, status="running", started_at=iso_now())


def mark_completed(job_root: str | Path, actual_pitch_shift_applied: bool) -> dict[str, Any]:
    """Mark a job as completed and set the one-hour expiry."""

    completed = utc_now()
    expires = completed + timedelta(seconds=DOWNLOAD_TTL_SECONDS)
    return update_status(
        job_root,
        status="completed",
        stage="completed",
        progress=1.0,
        message="处理完成",
        completed_at=completed.isoformat(),
        expires_at=expires.isoformat(),
        actual_pitch_shift_applied=bool(actual_pitch_shift_applied),
    )


def mark_failed(job_root: str | Path, message: str, error: str | None = None) -> dict[str, Any]:
    """Mark a job as failed with a Chinese user-facing message."""

    return update_status(job_root, status="failed", message=message, error=error or message)


def load_job_for_user(job_id: str, owner_sub: str) -> tuple[Path, dict[str, Any]]:
    """Find a job, enforce owner isolation, and refresh expiry."""

    root = find_job_dir(job_id)
    if root is None or not (root / "status.json").exists():
        raise HTTPException(status_code=404, detail="任务不存在。")
    status = read_status(root)
    if status.get("owner_sub") != owner_sub:
        raise HTTPException(status_code=403, detail="无权访问该任务。")
    if is_expired(status):
        status["status"] = "expired"
        status["message"] = "下载链接已过期"
        write_status(root, status)
    return root, status


def is_expired(status: dict[str, Any]) -> bool:
    """Return True when a completed job is past its download expiry."""

    expires_at = status.get("expires_at")
    if status.get("status") not in {"completed", "expired"} or not expires_at:
        return False
    return datetime.fromisoformat(expires_at) <= utc_now()


def cleanup_expired(root: str | Path | None = None) -> int:
    """Delete inputs/staging/artifacts for expired jobs and mark them expired."""

    from jobs.paths import web_jobs_root

    base = Path(root) if root else web_jobs_root()
    count = 0
    for status_path in base.glob("*/*/status.json"):
        job_root = status_path.parent
        status = read_status(job_root)
        if not is_expired(status):
            continue
        for child in ["inputs", "staging", "artifacts"]:
            shutil.rmtree(job_root / child, ignore_errors=True)
        status["status"] = "expired"
        status["message"] = "下载链接已过期"
        write_status(job_root, status)
        count += 1
    return count
