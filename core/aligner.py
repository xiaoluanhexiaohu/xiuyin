"""DTW alignment between reference and user feature sequences."""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from core.feature_extractor import AudioFeatures


@dataclass
class TimeSegment:
    """A low-confidence time span with a reason."""

    start: float
    end: float
    reason: str
    confidence: float | None = None


@dataclass
class AlignmentResult:
    """DTW alignment output mapping user frames to reference frames."""

    alignment_path: list[tuple[int, int]]
    user_to_reference_map: list[int | None]
    confidence: float
    low_confidence_segments: list[TimeSegment]
    distance: float
    warnings: list[str]


def align_features(reference_features: AudioFeatures, user_features: AudioFeatures) -> AlignmentResult:
    """Align user features to reference features using librosa DTW."""

    ref = np.asarray(reference_features.feature_matrix, dtype=np.float32)
    usr = np.asarray(user_features.feature_matrix, dtype=np.float32)
    if ref.ndim != 2 or usr.ndim != 2 or ref.shape[1] == 0 or usr.shape[1] == 0:
        raise ValueError("DTW requires non-empty 2D feature matrices")
    if ref.shape[0] != usr.shape[0]:
        raise ValueError("Reference and user feature matrices must have the same feature dimension")

    cost, wp = librosa.sequence.dtw(X=ref, Y=usr, metric="cosine")
    path = [(int(r), int(u)) for r, u in wp[::-1]]
    mapping: list[int | None] = [None] * usr.shape[1]
    per_user_refs: dict[int, list[int]] = {}
    for ref_idx, user_idx in path:
        if 0 <= user_idx < len(mapping):
            per_user_refs.setdefault(user_idx, []).append(ref_idx)
    for user_idx, refs in per_user_refs.items():
        mapping[user_idx] = int(round(float(np.median(refs))))

    final_distance = float(cost[-1, -1])
    norm_distance = final_distance / max(len(path), 1)
    confidence = float(np.clip(1.0 / (1.0 + norm_distance), 0.0, 1.0))
    low_segments = _low_confidence_segments(mapping, user_features.times, confidence)
    warnings = []
    if confidence < 0.4:
        warnings.append("Low global DTW confidence; inspect alignment before rendering.")
    if any(v is None for v in mapping):
        warnings.append("Some user frames could not be mapped to reference frames.")
    return AlignmentResult(path, mapping, confidence, low_segments, final_distance, warnings)


def _low_confidence_segments(
    mapping: list[int | None], times: list[float], global_confidence: float
) -> list[TimeSegment]:
    """Detect unmapped or locally unstable mapping spans."""

    bad = np.zeros(len(mapping), dtype=bool)
    last_ref = None
    for i, ref_idx in enumerate(mapping):
        if ref_idx is None:
            bad[i] = True
        elif last_ref is not None and abs(ref_idx - last_ref) > 8:
            bad[i] = True
        if ref_idx is not None:
            last_ref = ref_idx
    if global_confidence < 0.35 and len(bad):
        bad[:] = True
    return _frames_to_segments(bad, times, "unstable_or_unmapped_alignment", global_confidence)


def _frames_to_segments(mask: np.ndarray, times: list[float], reason: str, confidence: float) -> list[TimeSegment]:
    """Convert a boolean frame mask into time segments."""

    segments: list[TimeSegment] = []
    start = None
    for i, is_bad in enumerate(mask.tolist() + [False]):
        if is_bad and start is None:
            start = i
        elif not is_bad and start is not None:
            end_idx = max(i - 1, start)
            start_time = times[start] if start < len(times) else 0.0
            end_time = times[end_idx] if end_idx < len(times) else start_time
            segments.append(TimeSegment(float(start_time), float(end_time), reason, float(confidence)))
            start = None
    return segments
