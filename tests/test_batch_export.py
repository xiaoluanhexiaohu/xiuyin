import pytest

pytest.importorskip("numpy")

import json

import numpy as np
import pytest

from core.audio_io import write_wav
from jobs.batch_export import run_manifest


def test_manifest_missing_file_has_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Manifest file not found"):
        run_manifest(tmp_path / "missing.json")


def test_missing_audio_returns_job_error(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"jobs": [{"id": "x", "reference_audio": "no.wav", "user_audio": "no2.wav", "output_dir": str(tmp_path / "out")}]}))
    results = run_manifest(manifest)
    assert results[0]["ok"] is False
    assert "Audio file not found" in results[0]["error"]


def test_batch_export_generates_outputs(tmp_path):
    sr = 22050
    t = np.arange(sr // 2) / sr
    ref = tmp_path / "ref.wav"
    user = tmp_path / "user.wav"
    write_wav(ref, 0.1 * np.sin(2 * np.pi * 220 * t).astype(np.float32), sr)
    write_wav(user, 0.1 * np.sin(2 * np.pi * 210 * t).astype(np.float32), sr)
    out = tmp_path / "out"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"jobs": [{"id": "x", "reference_audio": str(ref), "user_audio": str(user), "output_dir": str(out)}]}))
    results = run_manifest(manifest)
    assert results[0]["ok"] is True, results
    assert (out / "corrected_vocal.wav").exists()
    assert (out / "mix.wav").exists()
    assert (out / "report.json").exists()
