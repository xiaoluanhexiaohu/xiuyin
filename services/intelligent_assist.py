"""Configurable AI-assist orchestration with lightweight fallback backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from core.audio_io import load_audio
from core.pitch_tracker import analyze_array
from core.vad import VoicedSegment, energy_vad


class VADBackend(Protocol):
    """Voice activity backend interface."""

    def detect(self, path: str | Path) -> list[VoicedSegment]: ...


class PitchBackend(Protocol):
    """Pitch backend interface."""

    def analyze(self, path: str | Path) -> dict[str, Any]: ...


@dataclass
class AssistArtifacts:
    """Artifacts returned by intelligent assist analysis."""

    user_voiced_segments: list[dict[str, float]]
    reference_voiced_segments: list[dict[str, float]]
    user_f0: dict[str, Any]
    reference_f0: dict[str, Any]
    note_events: list[dict[str, Any]] = field(default_factory=list)
    separated_vocal_paths: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class SimpleEnergyVADBackend:
    """Dependency-free VAD backend based on frame RMS."""

    def detect(self, path: str | Path) -> list[VoicedSegment]:
        audio = load_audio(path, normalize=True)
        return energy_vad(audio.y, audio.sr)


class ExistingPitchBackend:
    """Use the existing project pitch tracker."""

    def analyze(self, path: str | Path) -> dict[str, Any]:
        audio = load_audio(path, normalize=True)
        return analyze_array(audio.y, audio.sr).to_dict()


def analyze_reference_and_user(reference_path: str | Path, user_path: str | Path, options: dict[str, Any] | None = None) -> AssistArtifacts:
    """Analyze reference and user audio with pluggable backends.

    Heavy backends (Silero, torchcrepe, RMVPE, Demucs, Basic Pitch) are reserved
    for future adapters. The default path uses existing/fallback code so the MVP
    remains installable without large model dependencies.
    """

    opts = options or {}
    warnings: list[str] = []
    vad_name = str(opts.get("vad_backend", "simple_energy"))
    pitch_name = str(opts.get("pitch_backend", "existing"))
    if vad_name not in {"simple_energy", "silero", "webrtcvad"}:
        warnings.append(f"Unknown VAD backend {vad_name}; using simple_energy.")
    if pitch_name not in {"existing", "torchcrepe", "rmvpe"}:
        warnings.append(f"Unknown pitch backend {pitch_name}; using existing.")
    if vad_name != "simple_energy":
        warnings.append(f"VAD backend {vad_name} is not bundled yet; using simple_energy fallback.")
    if pitch_name != "existing":
        warnings.append(f"Pitch backend {pitch_name} is not bundled yet; using existing fallback.")
    if opts.get("separation"):
        warnings.append("Separation backend is reserved for Demucs/none adapters; no separation was run.")
    vad = SimpleEnergyVADBackend()
    pitch = ExistingPitchBackend()
    user_segments = [s.__dict__ for s in vad.detect(user_path)]
    ref_segments = [s.__dict__ for s in vad.detect(reference_path)]
    return AssistArtifacts(
        user_voiced_segments=user_segments,
        reference_voiced_segments=ref_segments,
        user_f0=pitch.analyze(user_path),
        reference_f0=pitch.analyze(reference_path),
        note_events=[],
        separated_vocal_paths={},
        warnings=warnings,
    )
