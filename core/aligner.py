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
    partial_match: bool = False
    matched_reference_start_time: float = 0.0
    matched_reference_end_time: float = 0.0


def align_features(reference_features: AudioFeatures, user_features: AudioFeatures) -> AlignmentResult:
    """Align user features to reference features using librosa DTW."""

    ref = np.asarray(reference_features.feature_matrix, dtype=np.float32)
    usr = np.asarray(user_features.feature_matrix, dtype=np.float32)
    if ref.ndim != 2 or usr.ndim != 2 or ref.shape[1] == 0 or usr.shape[1] == 0:
        raise ValueError("DTW requires non-empty 2D feature matrices")
    if ref.shape[0] != usr.shape[0]:
        raise ValueError("Reference and user feature matrices must have the same feature dimension")

    ref = _avoid_zero_cosine_rows(ref)
    usr = _avoid_zero_cosine_rows(usr)
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


def detect_best_reference_window(
    reference_features: AudioFeatures,
    user_features: AudioFeatures,
    min_confidence: float = 0.35,
) -> tuple[int, int, float, list[str]]:
    """Detect the best reference frame window for a shorter user recording."""

    ref = np.asarray(reference_features.feature_matrix, dtype=np.float32)
    usr = np.asarray(user_features.feature_matrix, dtype=np.float32)
    warnings: list[str] = []
    if ref.shape[1] <= usr.shape[1] or usr.shape[1] == 0:
        return 0, ref.shape[1], 1.0, warnings
    user_summary = np.mean(usr, axis=1)
    user_norm = float(np.linalg.norm(user_summary)) or 1.0
    win = usr.shape[1]
    step = max(1, win // 8)
    best_start = 0
    best_score = -1.0
    for start in range(0, ref.shape[1] - win + 1, step):
        ref_summary = np.mean(ref[:, start : start + win], axis=1)
        denom = (float(np.linalg.norm(ref_summary)) or 1.0) * user_norm
        score = float(np.dot(ref_summary, user_summary) / denom)
        if score > best_score:
            best_start = start
            best_score = score
    confidence = float(np.clip((best_score + 1.0) / 2.0, 0.0, 1.0))
    if confidence < min_confidence:
        warnings.append("未能可靠匹配原唱片段，本次仅生成基础修音计划。")
        return 0, ref.shape[1], confidence, warnings
    return best_start, min(best_start + win, ref.shape[1]), confidence, warnings


def align_partial_features(reference_features: AudioFeatures, user_features: AudioFeatures) -> AlignmentResult:
    """Align user features, using a local reference window when the user audio is shorter."""

    ref_frames = reference_features.feature_matrix.shape[1]
    user_frames = user_features.feature_matrix.shape[1]
    if ref_frames > user_frames * 1.25 and user_frames > 0:
        start, end, window_confidence, warnings = detect_best_reference_window(reference_features, user_features)
        sliced = AudioFeatures(
            times=reference_features.times[start:end],
            chroma=reference_features.chroma[:, start:end],
            onset_strength=reference_features.onset_strength[start:end],
            rms=reference_features.rms[start:end],
            feature_matrix=reference_features.feature_matrix[:, start:end],
            sr=reference_features.sr,
            hop_length=reference_features.hop_length,
        )
        result = align_features(sliced, user_features)
        result.user_to_reference_map = [None if v is None else int(v + start) for v in result.user_to_reference_map]
        result.alignment_path = [(int(r + start), int(u)) for r, u in result.alignment_path]
        result.partial_match = True
        result.matched_reference_start_time = reference_features.times[start] if start < len(reference_features.times) else 0.0
        result.matched_reference_end_time = reference_features.times[end - 1] if end - 1 < len(reference_features.times) else result.matched_reference_start_time
        result.confidence = float(min(result.confidence, max(window_confidence, 0.0)))
        result.warnings.extend(warnings)
        if result.confidence < 0.35 and "未能可靠匹配原唱片段，本次仅生成基础修音计划。" not in result.warnings:
            result.warnings.append("未能可靠匹配原唱片段，本次仅生成基础修音计划。")
        return result
    result = align_features(reference_features, user_features)
    result.partial_match = False
    result.matched_reference_start_time = 0.0
    result.matched_reference_end_time = reference_features.times[-1] if reference_features.times else 0.0
    return result


def _avoid_zero_cosine_rows(matrix: np.ndarray) -> np.ndarray:
    """Avoid NaN cosine distances for all-zero feature frames."""

    out = np.nan_to_num(np.asarray(matrix, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0).copy()
    # librosa/scipy compute cosine distance on time-frame rows after swapping
    # axes, so columns here must not be all-zero.
    zero_cols = np.linalg.norm(out, axis=0) <= 1e-12
    if np.any(zero_cols):
        out[0, zero_cols] = 1e-6
    return out
