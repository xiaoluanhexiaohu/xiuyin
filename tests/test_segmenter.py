import pytest

pytest.importorskip("numpy")

import numpy as np

from core.aligner import AlignmentResult
from core.correction_planner import create_correction_plan
from core.feature_extractor import AudioFeatures
from core.pitch_tracker import PitchTrack
from core.segmenter import segment_syllables


def _pitch(values, prob=0.9):
    return PitchTrack([i * 0.01 for i in range(len(values))], values, [v is not None for v in values], [prob] * len(values), "test", 44100, 512)


def _features(n):
    onset = np.zeros(n, dtype=np.float32)
    onset[5::10] = 1.0
    return AudioFeatures([i * 0.01 for i in range(n)], np.zeros((12, n), dtype=np.float32), onset, np.ones(n, dtype=np.float32), np.zeros((14, n), dtype=np.float32), 44100, 512)


def test_segmenter_generates_conservative_segments():
    user = _pitch([220.0] * 30)
    ref = _pitch([230.0] * 30)
    alignment = AlignmentResult([(i, i) for i in range(30)], list(range(30)), 0.9, [], 0.0, [])
    plan = create_correction_plan(user, ref, alignment)
    segments = segment_syllables(user, ref, _features(30), _features(30), alignment, plan, "conservative")
    assert segments
    assert all(segment.confidence >= 0 for segment in segments)


def test_low_confidence_segments_are_skipped():
    user = _pitch([220.0] * 10, prob=0.2)
    ref = _pitch([230.0] * 10)
    alignment = AlignmentResult([(i, i) for i in range(10)], list(range(10)), 0.9, [], 0.0, [])
    plan = create_correction_plan(user, ref, alignment)
    segments = segment_syllables(user, ref, _features(10), _features(10), alignment, plan, "normal")
    assert any(segment.skipped for segment in segments)
