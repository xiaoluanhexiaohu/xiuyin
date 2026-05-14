import pytest

pytest.importorskip("numpy")

import numpy as np
import pytest

from core.audio_io import load_audio, peak_normalize, write_wav


def test_write_and_load_wav_roundtrip(tmp_path):
    sr = 22050
    y = np.sin(2 * np.pi * 440 * np.arange(sr // 4) / sr).astype(np.float32) * 0.1
    path = tmp_path / "tone.wav"
    write_wav(path, y, sr)
    audio = load_audio(path, target_sr=sr)
    assert audio.sr == sr
    assert audio.duration > 0
    assert np.max(np.abs(audio.y)) <= 0.981


def test_peak_normalize_silence_stable():
    out = peak_normalize(np.zeros(100, dtype=np.float32))
    assert np.all(out == 0)


def test_missing_audio_has_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Audio file not found"):
        load_audio(tmp_path / "missing.wav")
