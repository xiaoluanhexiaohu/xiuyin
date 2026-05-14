import hashlib
import json
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from app.main import app
from jobs.paths import create_job_layout, write_job_index
from jobs.status import initial_status, write_status


def _hash(password="secret"):
    return "sha256$" + hashlib.sha256(password.encode()).hexdigest()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("XIUYIN_WEB_JOBS_DIR", str(tmp_path / "web_jobs"))
    monkeypatch.setenv("XIUYIN_JWT_SECRET", "test-secret")
    monkeypatch.setenv("XIUYIN_ADMIN_USERNAME", "alice")
    monkeypatch.setenv("XIUYIN_ADMIN_PASSWORD_HASH", _hash())
    monkeypatch.setattr("app.main.enqueue_web_job", lambda user_hash, job_id: "test-job")
    return TestClient(app)


def _token(client):
    response = client.post("/auth/token", data={"username": "alice", "password": "secret"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _wav_bytes(size=128):
    return b"RIFF" + b"0" * size


def test_login_success_returns_jwt(client):
    response = client.post("/auth/token", data={"username": "alice", "password": "secret"})
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"].count(".") == 2


def test_login_failure_returns_401(client):
    response = client.post("/auth/token", data={"username": "alice", "password": "bad"})
    assert response.status_code == 401


def test_upload_without_token_returns_401(client):
    response = client.post("/upload")
    assert response.status_code == 401


def test_upload_missing_reference_returns_error(client):
    token = _token(client)
    response = client.post(
        "/upload",
        headers=_headers(token),
        files={"user_audio": ("user.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 422


def test_upload_missing_user_returns_error(client):
    token = _token(client)
    response = client.post(
        "/upload",
        headers=_headers(token),
        files={"reference_audio": ("ref.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 422


def test_upload_over_100mb_returns_413(client, monkeypatch):
    monkeypatch.setattr("app.main.MAX_UPLOAD_BYTES", 4)
    token = _token(client)
    response = client.post(
        "/upload",
        headers=_headers(token),
        files={
            "reference_audio": ("ref.wav", b"12345", "audio/wav"),
            "user_audio": ("user.wav", b"123", "audio/wav"),
        },
    )
    assert response.status_code == 413


def test_upload_success_returns_job_id(client):
    token = _token(client)
    response = client.post(
        "/upload",
        headers=_headers(token),
        files={
            "reference_audio": ("ref.wav", _wav_bytes(), "audio/wav"),
            "user_audio": ("user.wav", _wav_bytes(), "audio/wav"),
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["job_id"]
    assert data["status"] == "queued"


def _make_completed_job(tmp_path, owner="alice", expired=False):
    from app.users import hash_user_sub

    job_id = "job123" if not expired else "jobexpired"
    user_hash = hash_user_sub(owner)
    root = create_job_layout(user_hash, job_id)
    status = initial_status(job_id, owner, {})
    completed = datetime.now(UTC) - timedelta(hours=2 if expired else 0)
    expires = completed + timedelta(hours=1)
    status.update(
        status="completed",
        stage="completed",
        progress=1.0,
        message="处理完成",
        completed_at=completed.isoformat(),
        expires_at=expires.isoformat(),
        actual_pitch_shift_applied=False,
        warnings=["仅生成修音计划，未做真实变调"],
    )
    artifacts = root / "artifacts"
    (artifacts / "corrected_vocal.wav").write_bytes(b"vocal")
    (artifacts / "mix.wav").write_bytes(b"mix")
    (artifacts / "report.json").write_text(json.dumps({"render": {"actual_pitch_shift_applied": False}}, ensure_ascii=False), encoding="utf-8")
    with zipfile.ZipFile(artifacts / "bundle.zip", "w") as zf:
        for name in ["corrected_vocal.wav", "mix.wav", "report.json"]:
            zf.write(artifacts / name, arcname=name)
    write_status(root, status)
    write_job_index(job_id, user_hash)
    return job_id, root


def test_status_result_download_owner_access_and_bundle(client, tmp_path):
    token = _token(client)
    job_id, root = _make_completed_job(tmp_path)
    status_response = client.get(f"/status/{job_id}", headers=_headers(token))
    assert status_response.status_code == 200
    result_response = client.get(f"/result/{job_id}", headers=_headers(token))
    assert result_response.status_code == 200
    assert result_response.json()["actual_pitch_shift_applied"] is False
    download_response = client.get(f"/download/{job_id}/bundle.zip", headers=_headers(token))
    assert download_response.status_code == 200
    with zipfile.ZipFile(root / "artifacts" / "bundle.zip") as zf:
        assert sorted(zf.namelist()) == ["corrected_vocal.wav", "mix.wav", "report.json"]


def test_other_user_cannot_access_job(client, monkeypatch, tmp_path):
    _make_completed_job(tmp_path, owner="bob")
    token = _token(client)
    response = client.get("/status/job123", headers=_headers(token))
    assert response.status_code == 403


def test_expired_download_returns_410(client, tmp_path):
    token = _token(client)
    job_id, _ = _make_completed_job(tmp_path, expired=True)
    response = client.get(f"/download/{job_id}/bundle.zip", headers=_headers(token))
    assert response.status_code == 410
