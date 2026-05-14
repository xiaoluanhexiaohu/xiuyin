"""Optional source-separation adapter with a Demucs-first interface."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import util
from pathlib import Path


@dataclass
class SeparationResult:
    """Result from optional vocal/accompaniment separation."""

    vocals_path: str | None
    accompaniment_path: str | None
    backend: str
    available: bool
    warnings: list[str]


def separate_vocals(input_audio: str | Path, output_dir: str | Path, backend: str = "demucs") -> SeparationResult:
    """Reserve a source-separation interface; Demucs execution is not required for MVP."""

    if backend != "demucs":
        return SeparationResult(None, None, backend, False, [f"Unsupported source separation backend: {backend}"])
    if util.find_spec("demucs") is None:
        return SeparationResult(None, None, backend, False, ["Demucs is not installed; source separation skipped."])
    return SeparationResult(
        None,
        None,
        backend,
        True,
        ["Demucs is available, but automatic execution is reserved for a later MVP iteration."],
    )
