import pytest

pytest.importorskip("numpy")

import numpy as np

from core.audio_io import write_wav
from core.correction_planner import CorrectionPlan
from core.renderer import render_corrected_vocal


def test_renderer_delegates_to_real_pitch_renderer(tmp_path):
    path = tmp_path / "user.wav"
    sr = 22050
    t = np.linspace(0, 1.0, sr, endpoint=False)
    write_wav(path, 0.2 * np.sin(2 * np.pi * 220 * t).astype(np.float32), sr)
    frames = 40
    plan = CorrectionPlan(
        [i * 0.02 for i in range(frames)],
        [220.0] * frames,
        [233.0] * frames,
        [233.0] * frames,
        [100.0] * frames,
        0.75,
        0.6,
        300,
        [],
        [],
        {},
    )
    result = render_corrected_vocal(path, plan, tmp_path / "corrected.wav", [])
    assert result.actual_pitch_shift_applied is True
    assert result.renderer == "scipy_resample_plan"
    assert result.metadata_path
