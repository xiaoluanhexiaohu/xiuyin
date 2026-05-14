"""Feature extraction for timing and melodic alignment."""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np


@dataclass
class AudioFeatures:
    """Frame-aligned features used by DTW."""

    times: list[float]
    chroma: np.ndarray
    onset_strength: np.ndarray
    rms: np.ndarray
    feature_matrix: np.ndarray
    sr: int
    hop_length: int


def extract_features(y: np.ndarray, sr: int, hop_length: int = 512, include_mel: bool = False) -> AudioFeatures:
    """Extract chroma, onset strength, RMS, and a normalized DTW feature matrix."""

    samples = np.nan_to_num(np.asarray(y, dtype=np.float32))
    chroma = librosa.feature.chroma_cqt(y=samples, sr=sr, hop_length=hop_length)
    onset = librosa.onset.onset_strength(y=samples, sr=sr, hop_length=hop_length)
    rms = librosa.feature.rms(y=samples, hop_length=hop_length)[0]
    n_frames = min(chroma.shape[1], onset.shape[0], rms.shape[0])
    chroma = chroma[:, :n_frames]
    onset = onset[:n_frames]
    rms = rms[:n_frames]
    rows = [_zscore(chroma), _zscore(onset)[None, :], _zscore(rms)[None, :]]
    if include_mel:
        mel = librosa.feature.melspectrogram(y=samples, sr=sr, hop_length=hop_length, n_mels=16)
        rows.append(_zscore(librosa.power_to_db(mel[:, :n_frames], ref=np.max)))
    feature_matrix = np.vstack(rows).astype(np.float32)
    times = librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=hop_length)
    return AudioFeatures(
        times=[float(t) for t in times],
        chroma=chroma.astype(np.float32),
        onset_strength=onset.astype(np.float32),
        rms=rms.astype(np.float32),
        feature_matrix=feature_matrix,
        sr=int(sr),
        hop_length=int(hop_length),
    )


def _zscore(x: np.ndarray) -> np.ndarray:
    """Normalize an array while remaining stable for silence."""

    arr = np.nan_to_num(np.asarray(x, dtype=np.float32))
    std = float(np.std(arr))
    if std <= 1e-8:
        return arr * 0.0
    return (arr - float(np.mean(arr))) / std
