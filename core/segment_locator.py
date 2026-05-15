"""Locate a short user vocal fragment inside a longer reference recording."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import librosa
import numpy as np

from core.audio_io import load_audio
from core.vad import energy_vad


@dataclass
class SegmentMatchResult:
    """Best matching reference segment for a user fragment."""

    reference_start_sec: float
    reference_end_sec: float
    confidence: float
    alignment_path: list[tuple[int, int]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    needs_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-safe dict."""

        return {
            "reference_start_sec": self.reference_start_sec,
            "reference_end_sec": self.reference_end_sec,
            "confidence": self.confidence,
            "alignment_path": self.alignment_path,
            "warnings": self.warnings,
            "needs_confirmation": self.needs_confirmation,
        }


def locate_reference_segment(
    reference_audio: str | Path,
    user_audio: str | Path,
    *,
    threshold: float = 0.45,
    target_sr: int = 22050,
    hop_length: int = 512,
) -> SegmentMatchResult:
    """Find where ``user_audio`` likely occurs within ``reference_audio``.

    First version: energy-trim the user signal, use chroma/RMS fingerprints for
    coarse sliding-window recall, and use a small DTW score around the best window
    for confidence refinement. It does not require source separation.
    """

    warnings: list[str] = []
    ref = load_audio(reference_audio, target_sr=target_sr, normalize=True)
    user = load_audio(user_audio, target_sr=target_sr, normalize=True)
    active = energy_vad(user.y, user.sr)
    if not active:
        return SegmentMatchResult(0.0, min(ref.duration, user.duration), 0.0, [], ["VOICE_ACTIVITY_EMPTY"], True)
    start = max(0, int(active[0].start_sec * user.sr))
    end = min(len(user.y), int(active[-1].end_sec * user.sr))
    user_y = user.y[start:end]
    if len(user_y) < user.sr * 0.2:
        return SegmentMatchResult(0.0, min(ref.duration, user.duration), 0.1, [], ["User fragment is too short for reliable segment location."], True)

    ref_feat = _fingerprint(ref.y, ref.sr, hop_length)
    user_feat = _fingerprint(user_y, user.sr, hop_length)
    if user_feat.shape[1] < 2 or ref_feat.shape[1] < user_feat.shape[1]:
        return SegmentMatchResult(0.0, min(ref.duration, user.duration), 0.0, [], ["Reference audio is shorter than the active user fragment."], True)

    user_vec = _flatten_norm(user_feat)
    win = user_feat.shape[1]
    best_score = -1.0
    best_idx = 0
    for idx in range(0, ref_feat.shape[1] - win + 1):
        score = float(np.dot(_flatten_norm(ref_feat[:, idx : idx + win]), user_vec))
        if score > best_score:
            best_score = score
            best_idx = idx

    # Fine score: DTW in the neighborhood of the best coarse window.
    pad = max(2, win // 8)
    left = max(0, best_idx - pad)
    right = min(ref_feat.shape[1], best_idx + win + pad)
    try:
        dist, path = librosa.sequence.dtw(X=user_feat, Y=ref_feat[:, left:right], metric="cosine")
        fine = 1.0 / (1.0 + float(dist[-1, -1]) / max(1, len(path)))
        alignment = [(int(a), int(b + left)) for a, b in path[:: max(1, len(path) // 50)]]
    except Exception as exc:
        warnings.append(f"DTW refinement failed, using coarse score only: {exc}")
        fine = max(0.0, best_score)
        alignment = []
    confidence = float(np.clip((max(0.0, best_score) + fine) / 2.0, 0.0, 1.0))
    start_sec = float(librosa.frames_to_time(best_idx, sr=ref.sr, hop_length=hop_length))
    end_sec = min(ref.duration, start_sec + len(user_y) / user.sr)
    if confidence < threshold:
        warnings.append("SEGMENT_CONFIDENCE_LOW")
    return SegmentMatchResult(start_sec, end_sec, confidence, alignment, warnings, confidence < threshold)


def _fingerprint(y: np.ndarray, sr: int, hop_length: int) -> np.ndarray:
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop_length)
    rms = librosa.feature.rms(y=y, hop_length=hop_length)
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)[np.newaxis, :]
    min_frames = min(chroma.shape[1], rms.shape[1], onset.shape[1])
    feat = np.vstack([chroma[:, :min_frames], rms[:, :min_frames] * 5.0, onset[:, :min_frames] / (np.max(onset) + 1e-6)])
    return np.nan_to_num(feat.astype(np.float32))


def _flatten_norm(x: np.ndarray) -> np.ndarray:
    vec = np.nan_to_num(x.reshape(-1).astype(np.float32))
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 1e-8 else vec
