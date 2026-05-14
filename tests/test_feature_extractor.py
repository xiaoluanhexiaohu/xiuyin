import pytest

pytest.importorskip("numpy")

import numpy as np

from core.feature_extractor import extract_features


def test_extract_features_shapes():
    sr = 22050
    y = 0.1 * np.sin(2 * np.pi * 440 * np.arange(sr // 2) / sr).astype(np.float32)
    features = extract_features(y, sr, hop_length=512)
    assert features.feature_matrix.ndim == 2
    assert features.feature_matrix.shape[1] == len(features.times)
    assert features.chroma.shape[0] == 12
