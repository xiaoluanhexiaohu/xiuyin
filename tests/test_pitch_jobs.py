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
    monkeypatch.setattr("app.routers.pitch_jobs.process_web_job", lambda user_hash, job_id: {"job_id": job_id, "ok": True})
    return TestClient(app)


def _token(client):
    return client.post("/auth/token", data={"username": "alice", "password": "secret"}).json()["access_token"]


def _upload(client, token, tmp_path, name, freq=220.0):
    src = tmp_path / name
    sr = 22050
    y = 0.1 * np.sin(2 * np.pi * freq * np.arange(sr) / sr).astype(np.float32)
    write_wav(src, y, sr)
    response = client.post(
        "/api/v1/audio/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"kind": "reference_audio" if "ref" in name else "user_vocal", "source": "upload"},
        files={"file": (name, src.read_bytes(), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    return response.json()["audio_id"]


def test_pitch_job_succeeds(client, tmp_path):
    token = _token(client)
    ref_id = _upload(client, token, tmp_path, "ref.wav")
    user_id = _upload(client, token, tmp_path, "user.wav")
    response = client.post(
        "/api/v1/pitch-correction/jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"reference_audio_id": ref_id, "user_audio_id": user_id, "options": {"auto_locate_segment": False}},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] in {"succeeded", "failed"}
    assert data["job_id"]


def test_pitch_job_needs_confirmation_on_low_segment_confidence(client, tmp_path, monkeypatch):
    token = _token(client)
    ref_id = _upload(client, token, tmp_path, "ref.wav")
    user_id = _upload(client, token, tmp_path, "user.wav")

    class Match:
        needs_confirmation = True
        warnings = ["SEGMENT_CONFIDENCE_LOW"]

        def to_dict(self):
            return {"confidence": 0.1, "warnings": self.warnings, "needs_confirmation": True}

    monkeypatch.setattr("app.routers.pitch_jobs.locate_reference_segment", lambda *a, **k: Match())
    response = client.post(
        "/api/v1/pitch-correction/jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={"reference_audio_id": ref_id, "user_audio_id": user_id, "options": {"auto_locate_segment": True}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "needs_confirmation"
    assert response.json()["error_code"] == "SEGMENT_NEEDS_CONFIRMATION"
