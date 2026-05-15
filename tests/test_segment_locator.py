import numpy as np

from core.audio_io import write_wav
from core.segment_locator import locate_reference_segment


def test_segment_locator_finds_reference_start(tmp_path):
    sr = 22050
    t = np.linspace(0, 4.0, sr * 4, endpoint=False)
    ref = np.zeros_like(t, dtype=np.float32)
    ref += 0.05 * np.sin(2 * np.pi * 110 * t)
    ref[sr * 2 : sr * 3] += 0.3 * np.sin(2 * np.pi * 440 * t[:sr])
    user = ref[sr * 2 : sr * 3]
    ref_path = tmp_path / "ref.wav"
    user_path = tmp_path / "user.wav"
    write_wav(ref_path, ref, sr)
    write_wav(user_path, user, sr)
    match = locate_reference_segment(ref_path, user_path, threshold=0.2)
    assert abs(match.reference_start_sec - 2.0) < 0.25
    assert match.confidence > 0.2


def test_segment_locator_low_quality_needs_confirmation(tmp_path):
    sr = 22050
    ref_path = tmp_path / "ref.wav"
    user_path = tmp_path / "user.wav"
    write_wav(ref_path, np.zeros(sr, dtype=np.float32), sr)
    write_wav(user_path, np.zeros(sr // 2, dtype=np.float32), sr)
    match = locate_reference_segment(ref_path, user_path)
    assert match.needs_confirmation is True
    assert match.warnings
