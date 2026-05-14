import pytest

pytest.importorskip("numpy")

import numpy as np
import pytest

from core.aligner import align_features
from core.feature_extractor import AudioFeatures


def _features(matrix):
    n = matrix.shape[1]
    return AudioFeatures(
        times=[i * 0.01 for i in range(n)],
        chroma=matrix[:12],
        onset_strength=np.zeros(n),
        rms=np.ones(n),
        feature_matrix=matrix.astype(np.float32),
        sr=44100,
        hop_length=512,
    )


def test_align_features_maps_user_frames():
    x = np.eye(12, 20)
    result = align_features(_features(x), _features(x.copy()))
    assert len(result.user_to_reference_map) == 20
    assert result.confidence > 0


def test_empty_features_raise_clear_error():
    matrix = np.empty((12, 0), dtype=np.float32)
    with pytest.raises(ValueError, match="non-empty"):
        align_features(_features(matrix), _features(matrix))
