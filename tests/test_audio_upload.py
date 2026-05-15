import hashlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from core.audio_io import write_wav


def _hash(password="secret"):
    return "sha256$" + hashlib.sha256(password.encode()).hexdigest()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("XIUYIN_WEB_JOBS_DIR", str(tmp_path / "web_jobs"))
    monkeypatch.setenv("UPLOAD_RAW_DIR", str(tmp_path / "storage" / "uploads" / "raw"))
    monkeypatch.setenv("UPLOAD_NORMALIZED_DIR", str(tmp_path / "storage" / "uploads" / "normalized"))
    monkeypatch.setenv("XIUYIN_JWT_SECRET", "test-secret")
    monkeypatch.setenv("XIUYIN_ADMIN_USERNAME", "alice")
    monkeypatch.setenv("XIUYIN_ADMIN_PASSWORD_HASH", _hash())
    return TestClient(app)


def _token(client):
    return client.post("/auth/token", data={"username": "alice", "password": "secret"}).json()["access_token"]


def _tone(path, sr=22050):
    write_wav(path, 0.1 * np.sin(2 * np.pi * 220 * np.arange(sr) / sr).astype(np.float32), sr)


def test_audio_upload_wav_normalizes(client, tmp_path):
    src = tmp_path / "tone.wav"
    _tone(src)
    token = _token(client)
    response = client.post(
        "/api/v1/audio/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"kind": "reference_audio", "source": "upload"},
        files={"file": ("tone.wav", src.read_bytes(), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["audio_id"].startswith("aud_")
    assert data["sample_rate"] == 48000
    assert "storage/uploads/normalized" in data["normalized_path"] or data["normalized_path"].endswith(".wav")


@pytest.mark.parametrize("filename,content_type", [("tone.mp3", "audio/mpeg"), ("tone.webm", "audio/webm")])
def test_audio_upload_compressed_formats_enter_normalize_flow(client, monkeypatch, tmp_path, filename, content_type):
    token = _token(client)
    normalized_src = tmp_path / "normalized.wav"
    _tone(normalized_src, sr=48000)

    def fake_normalize(input_path, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(normalized_src.read_bytes())
        return {"sample_rate": 48000, "channels": 1, "duration_sec": 1.0}

    monkeypatch.setattr("app.routers.audio.normalize_to_wav", fake_normalize)
    response = client.post(
        "/api/v1/audio/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"kind": "user_vocal", "source": "upload"},
        files={"file": (filename, b"mock-compressed", content_type)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["normalized_path"].endswith(".wav")


def test_audio_upload_too_large_returns_error(client, monkeypatch):
    monkeypatch.setattr("app.routers.audio.MAX_RECORDING_BYTES", 4)
    token = _token(client)
    response = client.post(
        "/api/v1/audio/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"kind": "user_vocal", "source": "recording"},
        files={"file": ("x.wav", b"12345", "audio/wav")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["error_code"] == "AUDIO_TOO_LARGE"


def test_audio_upload_unsupported_format_returns_invalid_audio_format(client):
    token = _token(client)
    response = client.post(
        "/api/v1/audio/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"kind": "user_vocal", "source": "upload"},
        files={"file": ("x.txt", b"not-audio", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "INVALID_AUDIO_FORMAT"
