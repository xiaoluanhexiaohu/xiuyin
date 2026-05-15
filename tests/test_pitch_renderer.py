import numpy as np

from core.audio_io import load_audio, write_wav
from core.correction_planner import CorrectionPlan
from core.pitch_renderer import render_pitch_corrected_vocal


def _plan(frames=40, shift=100.0, low=None):
    times = [i * 0.02 for i in range(frames)]
    low = low or []
    return CorrectionPlan(
        times=times,
        original_f0_hz=[220.0] * frames,
        reference_f0_hz=[233.0] * frames,
        target_f0_hz=[233.0] * frames,
        shift_cents=[shift] * frames,
        correction_strength=0.75,
        keep_vibrato_ratio=0.6,
        max_shift_cents=300.0,
        low_confidence_frames=low,
        warnings=[],
        metadata={},
    )


def test_pitch_renderer_applies_shift_and_preserves_duration(tmp_path):
    sr = 22050
    t = np.linspace(0, 1.0, sr, endpoint=False)
    y = 0.2 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
    src = tmp_path / "src.wav"
    out = tmp_path / "out.wav"
    write_wav(src, y, sr)
    result = render_pitch_corrected_vocal(src, _plan(), out)
    rendered = load_audio(out, target_sr=sr, normalize=False)
    assert result.actual_pitch_shift_applied is True
    assert result.metadata["actual_pitch_shift_applied"] is True
    assert result.metadata["mean_abs_shift_cents"] > 0
    assert abs(rendered.duration - 1.0) < 0.01


def test_pitch_renderer_skips_low_confidence_and_silence_safely(tmp_path):
    sr = 22050
    y = np.zeros(sr, dtype=np.float32)
    n = sr // 2 - sr // 4
    y[sr // 4 : sr // 2] = 0.15 * np.sin(2 * np.pi * 220 * np.arange(n) / sr)
    src = tmp_path / "src.wav"
    out = tmp_path / "out.wav"
    write_wav(src, y, sr)
    plan = _plan(frames=50, shift=120.0, low=list(range(50)))
    result = render_pitch_corrected_vocal(src, plan, out)
    rendered = load_audio(out, target_sr=sr, normalize=False)
    assert result.actual_pitch_shift_applied is False
    assert np.max(np.abs(rendered.y)) <= 1.0
    assert result.metadata["skipped_frames"] >= 50
