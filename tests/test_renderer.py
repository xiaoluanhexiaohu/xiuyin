import pytest

pytest.importorskip("numpy")

import numpy as np

from core.audio_io import write_wav
from core.correction_planner import CorrectionPlan
from core.renderer import PLACEHOLDER_WARNING, render_corrected_vocal


def test_rubberband_unavailable_uses_placeholder(tmp_path, monkeypatch):
    monkeypatch.setattr("core.renderer.is_rubberband_available", lambda: False)
    path = tmp_path / "user.wav"
    write_wav(path, np.zeros(1024, dtype=np.float32), 22050)
    plan = CorrectionPlan([0.0], [220.0], [220.0], [220.0], [0.0], 0.75, 0.6, 300, [], [], {})
    result = render_corrected_vocal(path, plan, tmp_path / "corrected.wav", [])
    assert result.actual_pitch_shift_applied is False
    assert result.renderer == "placeholder"
    assert PLACEHOLDER_WARNING in result.warnings
