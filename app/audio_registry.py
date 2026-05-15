"""Per-user audio-id registry for uploaded or imported reference audio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.users import hash_user_sub
from jobs.paths import web_jobs_root


def audio_registry_dir(owner_sub: str) -> Path:
    """Return the owner-scoped audio metadata directory."""

    return web_jobs_root() / hash_user_sub(owner_sub) / "audio_index"


def register_audio(owner_sub: str, audio_id: str, metadata: dict[str, Any]) -> None:
    """Persist owner-scoped metadata for one audio id."""

    root = audio_registry_dir(owner_sub)
    root.mkdir(parents=True, exist_ok=True)
    payload = {**metadata, "audio_id": audio_id, "owner_sub": owner_sub}
    (root / f"{audio_id}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_registered_audio(owner_sub: str, audio_id: str) -> dict[str, Any] | None:
    """Load owner-scoped audio metadata if it exists."""

    path = audio_registry_dir(owner_sub) / f"{audio_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
