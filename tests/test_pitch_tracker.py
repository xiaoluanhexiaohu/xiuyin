import pytest

pytest.importorskip("numpy")

import json

import numpy as np

from core.pitch_tracker import PitchTrackerConfig, analyze_array


def test_analyze_array_returns_json_safe_track():
    sr = 22050
    y = 0.1 * np.sin(2 * np.pi * 220 * np.arange(sr // 2) / sr).astype(np.float32)
    track = analyze_array(y, sr, PitchTrackerConfig(hop_length=512, fmin=80, fmax=500))
    assert len(track.times) == len(track.f0_hz) == len(track.voiced_flag) == len(track.voiced_prob)
    assert track.method in {"librosa.pyin", "torchcrepe"}
    json.dumps(track.to_dict())


def test_silence_does_not_crash():
    track = analyze_array(np.zeros(4096, dtype=np.float32), 22050, PitchTrackerConfig())
    assert len(track.times) == len(track.f0_hz)
