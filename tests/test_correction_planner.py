import pytest

pytest.importorskip("numpy")

import json

import numpy as np

from core.aligner import AlignmentResult
from core.correction_planner import cents_difference, create_correction_plan
from core.pitch_tracker import PitchTrack


def _pitch(values, prob=0.9):
    return PitchTrack(
        times=[i * 0.01 for i in range(len(values))],
        f0_hz=values,
        voiced_flag=[v is not None for v in values],
        voiced_prob=[prob] * len(values),
        method="test",
        sr=44100,
        hop_length=512,
    )


def _alignment(n):
    return AlignmentResult([(i, i) for i in range(n)], list(range(n)), 0.9, [], 0.0, [])


def test_cents_difference_signs():
    assert cents_difference(220.0, 110.0) > 0
    assert cents_difference(110.0, 220.0) < 0


def test_correction_strength_zero_keeps_user_pitch():
    user = _pitch([220.0] * 12)
    ref = _pitch([440.0] * 12)
    plan = create_correction_plan(user, ref, _alignment(12), correction_strength=0.0)
    assert np.nanmean([v for v in plan.target_f0_hz if v is not None]) == 220.0


def test_max_shift_clips_large_shift():
    user = _pitch([110.0] * 12)
    ref = _pitch([880.0] * 12)
    plan = create_correction_plan(user, ref, _alignment(12), correction_strength=1.0, max_shift_cents=300)
    assert max(plan.shift_cents) == 300
    assert any("Clipped" in w for w in plan.warnings)


def test_low_probability_and_unvoiced_are_not_forced():
    user = _pitch([220.0, None, 220.0], prob=0.4)
    ref = _pitch([440.0, 440.0, 440.0])
    plan = create_correction_plan(user, ref, _alignment(3), voiced_prob_threshold=0.5)
    assert plan.target_f0_hz[0] == 220.0
    assert plan.target_f0_hz[1] is None
    assert plan.low_confidence_frames == [0, 2]


def test_plan_is_json_serializable_and_preserves_some_vibrato():
    values = [220 + 5 * np.sin(i / 2) for i in range(30)]
    user = _pitch([float(v) for v in values])
    ref = _pitch([240.0] * 30)
    plan = create_correction_plan(user, ref, _alignment(30), keep_vibrato_ratio=0.5)
    json.dumps(plan.to_dict())
    assert len(set(round(v or 0, 2) for v in plan.target_f0_hz)) > 1
