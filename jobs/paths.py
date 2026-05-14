"""Filesystem layout helpers for web upload jobs."""

from __future__ import annotations

import json
import os
from pathlib import Path

WEB_JOBS_ROOT = Path(os.getenv("XIUYIN_WEB_JOBS_DIR", "outputs/web_jobs"))


def web_jobs_root() -> Path:
    """Return the web jobs root directory."""

    return Path(os.getenv("XIUYIN_WEB_JOBS_DIR", str(WEB_JOBS_ROOT)))


def job_dir(user_hash: str, job_id: str) -> Path:
    """Return the directory for one user-owned job."""

    return web_jobs_root() / user_hash / job_id


def create_job_layout(user_hash: str, job_id: str) -> Path:
    """Create the standard job directory structure."""

    root = job_dir(user_hash, job_id)
    for name in ["inputs", "staging", "artifacts"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    (web_jobs_root() / "index").mkdir(parents=True, exist_ok=True)
    return root


def index_path(job_id: str) -> Path:
    """Return the path to a job index document."""

    return web_jobs_root() / "index" / f"{job_id}.json"


def write_job_index(job_id: str, user_hash: str) -> None:
    """Write the lookup index for a job id."""

    path = index_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"job_id": job_id, "user_hash": user_hash, "status_path": str(job_dir(user_hash, job_id) / "status.json")}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def find_job_dir(job_id: str) -> Path | None:
    """Find a job directory by job id without exposing the user hash."""

    idx = index_path(job_id)
    if idx.exists():
        data = json.loads(idx.read_text(encoding="utf-8"))
        status_path = Path(data["status_path"])
        return status_path.parent
    matches = list(web_jobs_root().glob(f"*/{job_id}/status.json"))
    return matches[0].parent if matches else None
