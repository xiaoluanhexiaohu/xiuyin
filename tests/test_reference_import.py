import asyncio
import hashlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from core.audio_io import write_wav
from services.reference_providers.base import ImportedReferenceAudio, ReferenceSearchItem
from services.reference_providers.freesound import FreesoundProvider
from services.reference_providers.jamendo import JamendoProvider


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


def test_jamendo_import_when_download_allowed(monkeypatch, tmp_path):
    src = tmp_path / "source.wav"
    write_wav(src, np.zeros(1024, dtype=np.float32), 22050)
    monkeypatch.setenv("REFERENCE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("REFERENCE_NORMALIZED_DIR", str(tmp_path / "norm"))

    async def fake_track(self, track_id):
        return ReferenceSearchItem(
            source="jamendo",
            track_id=track_id,
            title="Allowed",
            artist="Artist",
            download_url="https://example.test/audio.wav",
            external_url="https://jamendo.test/track",
            license="CC BY",
            can_download=True,
            authorization_notes="可按授权导入",
        )

    async def fake_download(url, destination, headers=None):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(src.read_bytes())

    monkeypatch.setattr(JamendoProvider, "_track", fake_track)
    monkeypatch.setattr("services.reference_providers.jamendo.download_audio", fake_download)
    imported = asyncio.run(JamendoProvider().import_track("1"))
    assert imported.audio_id.startswith("ref_")
    assert imported.normalized_path.endswith(".wav")


def test_freesound_import_without_oauth_uses_preview(monkeypatch, tmp_path):
    src = tmp_path / "preview.wav"
    write_wav(src, np.zeros(1024, dtype=np.float32), 22050)
    monkeypatch.delenv("FREESOUND_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("REFERENCE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("REFERENCE_NORMALIZED_DIR", str(tmp_path / "norm"))
    seen = {}

    async def fake_sound(self, track_id):
        return ReferenceSearchItem(
            source="freesound",
            track_id=track_id,
            title="Preview",
            preview_url="https://example.test/preview.wav",
            license="CC0",
            can_download=True,
            authorization_notes="仅导入 preview，原始文件下载需要 OAuth2。",
        )

    async def fake_download(url, destination, headers=None):
        seen["url"] = url
        seen["headers"] = headers
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(src.read_bytes())

    monkeypatch.setattr(FreesoundProvider, "_sound", fake_sound)
    monkeypatch.setattr("services.reference_providers.freesound.download_audio", fake_download)
    imported = asyncio.run(FreesoundProvider().import_track("42"))
    assert seen["url"].endswith("preview.wav")
    assert seen["headers"] is None
    assert "preview" in imported.authorization_notes


def test_spotify_import_api_returns_not_allowed(client):
    token = _token(client)
    response = client.post(
        "/api/v1/reference/import",
        headers={"Authorization": f"Bearer {token}"},
        json={"source": "spotify", "track_id": "sp1"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "REFERENCE_IMPORT_NOT_ALLOWED"


def test_youtube_import_api_returns_not_allowed(client):
    token = _token(client)
    response = client.post(
        "/api/v1/reference/import",
        headers={"Authorization": f"Bearer {token}"},
        json={"source": "youtube", "track_id": "yt1"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "REFERENCE_IMPORT_NOT_ALLOWED"


def test_reference_import_api_registers_imported_audio(client, monkeypatch, tmp_path):
    token = _token(client)
    normalized = tmp_path / "ref.wav"
    write_wav(normalized, np.zeros(1024, dtype=np.float32), 48000)

    async def fake_import(self, track_id):
        return ImportedReferenceAudio(
            source="jamendo",
            track_id=track_id,
            audio_id="ref_test",
            title="Imported",
            artist="Artist",
            original_url="https://example.test",
            local_path=str(tmp_path / "raw.wav"),
            normalized_path=str(normalized),
            sample_rate=48000,
            duration_sec=0.02,
            license="CC BY",
            authorization_notes="可按授权导入",
        )

    monkeypatch.setattr(JamendoProvider, "import_track", fake_import)
    response = client.post(
        "/api/v1/reference/import",
        headers={"Authorization": f"Bearer {token}"},
        json={"source": "jamendo", "track_id": "1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["audio_id"] == "ref_test"
