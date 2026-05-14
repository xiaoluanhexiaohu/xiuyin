import pytest

pytest.importorskip("numpy")

from services.source_separation import DEMUCS_UNAVAILABLE_WARNING, separate_reference_audio


def test_demucs_unavailable_does_not_fail(tmp_path, monkeypatch):
    monkeypatch.setattr("services.source_separation.is_demucs_available", lambda: False)
    source = tmp_path / "reference.wav"
    source.write_bytes(b"fake")
    result = separate_reference_audio(source, tmp_path / "out")
    assert result.vocals_path == str(source)
    assert DEMUCS_UNAVAILABLE_WARNING in result.warnings
