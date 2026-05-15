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
    monkeypatch.setenv("XIUYIN_JWT_SECRET", "test-secret")
    monkeypatch.setenv("XIUYIN_ADMIN_USERNAME", "alice")
    monkeypatch.setenv("XIUYIN_ADMIN_PASSWORD_HASH", _hash())
    return TestClient(app)


def _token(client):
    return client.post("/auth/token", data={"username": "alice", "password": "secret"}).json()["access_token"]


def test_audio_upload_wav_normalizes(client, tmp_path):
    src = tmp_path / "tone.wav"
    write_wav(src, 0.1 * np.sin(2 * np.pi * 220 * np.arange(22050) / 22050).astype(np.float32), 22050)
    token = _token(client)
    response = client.post(
        "/api/v1/audio/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"kind": "user_vocal", "source": "recording"},
        files={"file": ("tone.wav", src.read_bytes(), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["audio_id"]
    assert data["sample_rate"] == 48000
    assert data["normalized_path"].endswith("normalized.wav")


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
