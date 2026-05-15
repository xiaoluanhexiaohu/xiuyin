"""FastAPI application for the Chinese upload-style one-click correction MVP."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import TOKEN_EXPIRE_SECONDS, create_access_token, get_current_user
from app.schemas import JobStatusResponse, ResultResponse, TokenResponse, UploadResponse
from app.users import User, hash_user_sub, verify_password
from app.routers.audio import router as audio_router
from app.routers.pitch_jobs import router as pitch_jobs_router
from app.routers.reference import router as reference_router
from jobs.paths import create_job_layout, write_job_index
from jobs.queue import enqueue_web_job
from jobs.status import initial_status, is_expired, load_job_for_user, mark_failed, write_status

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
SUPPORTED_UPLOAD_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac"}

app = FastAPI(title="修音 Web 系统", version="0.2.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.include_router(audio_router)
app.include_router(reference_router)
app.include_router(pitch_jobs_router)

ALLOWED_ARTIFACTS = {
    "bundle.zip": "application/zip",
    "corrected_vocal.wav": "audio/wav",
    "mix.wav": "audio/wav",
    "report.json": "application/json",
}


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""

    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Return the minimal Chinese upload page."""

    return templates.TemplateResponse("simple_upload.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Return the Chinese login page."""

    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/auth/token", response_model=TokenResponse)
def token(form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> TokenResponse:
    """OAuth2 password-flow login endpoint."""

    if not verify_password(form.username, form.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误。",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(form.username, TOKEN_EXPIRE_SECONDS),
        token_type="bearer",
        expires_in=TOKEN_EXPIRE_SECONDS,
    )


@app.post("/upload", response_model=UploadResponse)
def upload(
    current_user: Annotated[User, Depends(get_current_user)],
    reference_audio: Annotated[UploadFile, File(description="原唱音频")],
    user_audio: Annotated[UploadFile, File(description="我的录音")],
    correction_strength: Annotated[float, Form()] = 0.75,
    keep_vibrato_ratio: Annotated[float, Form()] = 0.6,
    max_shift_cents: Annotated[float, Form()] = 300.0,
    auto_separate_reference: Annotated[bool, Form()] = True,
    syllable_granularity: Annotated[str, Form()] = "conservative",
    output_format: Annotated[str, Form()] = "wav",
) -> UploadResponse:
    """Save uploaded audio files, create a job, enqueue processing, and return immediately."""

    _validate_upload_name(reference_audio.filename)
    _validate_upload_name(user_audio.filename)
    if syllable_granularity not in {"conservative", "normal", "aggressive"}:
        raise HTTPException(status_code=400, detail="音节分段粒度只能是 conservative、normal 或 aggressive。")
    if output_format != "wav":
        raise HTTPException(status_code=400, detail="当前 MVP 仅支持 wav 输出。")
    job_id = uuid.uuid4().hex
    user_hash = hash_user_sub(current_user.sub)
    root = create_job_layout(user_hash, job_id)
    options = {
        "correction_strength": float(correction_strength),
        "keep_vibrato_ratio": float(keep_vibrato_ratio),
        "max_shift_cents": float(max_shift_cents),
        "auto_separate_reference": bool(auto_separate_reference),
        "syllable_granularity": syllable_granularity,
        "output_format": output_format,
    }
    write_status(root, initial_status(job_id, current_user.sub, options))
    write_job_index(job_id, user_hash)
    ref_suffix = Path(reference_audio.filename or "").suffix.lower()
    user_suffix = Path(user_audio.filename or "").suffix.lower()
    try:
        _save_upload(reference_audio, root / "inputs" / f"reference_audio.original{ref_suffix}")
        _save_upload(user_audio, root / "inputs" / f"user_audio.original{user_suffix}")
        enqueue_web_job(user_hash, job_id)
    except HTTPException:
        raise
    except Exception as exc:
        mark_failed(root, "排队失败", str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return UploadResponse(
        job_id=job_id,
        status="queued",
        status_url=f"/status/{job_id}",
        result_url=f"/result/{job_id}",
    )


@app.get("/status/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str, current_user: Annotated[User, Depends(get_current_user)]) -> JobStatusResponse:
    """Return Chinese job progress for the owner."""

    _, status_doc = load_job_for_user(job_id, current_user.sub)
    return JobStatusResponse(
        job_id=job_id,
        status=status_doc["status"],
        stage=status_doc.get("stage", "upload"),
        progress=float(status_doc.get("progress", 0.0)),
        message=status_doc.get("message", ""),
        warnings=status_doc.get("warnings", []),
    )


@app.get("/result/{job_id}", response_model=ResultResponse)
def result(job_id: str, current_user: Annotated[User, Depends(get_current_user)]) -> ResultResponse:
    """Return completed artifact URLs for the owner."""

    root, status_doc = load_job_for_user(job_id, current_user.sub)
    if status_doc.get("status") == "expired" or is_expired(status_doc):
        raise HTTPException(status_code=410, detail="下载链接已过期，请重新提交任务。")
    if status_doc.get("status") != "completed":
        raise HTTPException(status_code=409, detail=status_doc.get("message", "任务尚未完成。"))
    if not (root / "artifacts" / "bundle.zip").exists():
        raise HTTPException(status_code=404, detail="结果文件不存在。")
    return ResultResponse(
        job_id=job_id,
        status="completed",
        completed_at=str(status_doc.get("completed_at")),
        expires_at=str(status_doc.get("expires_at")),
        bundle_url=f"/download/{job_id}/bundle.zip",
        artifacts={
            "corrected_vocal": f"/download/{job_id}/corrected_vocal.wav",
            "mix": f"/download/{job_id}/mix.wav",
            "report": f"/download/{job_id}/report.json",
        },
        actual_pitch_shift_applied=bool(status_doc.get("actual_pitch_shift_applied", False)),
        warnings=status_doc.get("warnings", []),
    )


@app.get("/download/{job_id}/{artifact}")
def download(job_id: str, artifact: str, current_user: Annotated[User, Depends(get_current_user)]):
    """Download a whitelisted artifact for a completed, non-expired owned job."""

    if artifact not in ALLOWED_ARTIFACTS:
        raise HTTPException(status_code=404, detail="文件不存在。")
    root, status_doc = load_job_for_user(job_id, current_user.sub)
    if status_doc.get("status") == "expired" or is_expired(status_doc):
        raise HTTPException(status_code=410, detail="下载链接已过期，请重新提交任务。")
    if status_doc.get("status") != "completed":
        raise HTTPException(status_code=409, detail="任务尚未完成。")
    path = root / "artifacts" / artifact
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在。")
    return FileResponse(path, media_type=ALLOWED_ARTIFACTS[artifact], filename=artifact)


def _validate_upload_name(filename: str | None) -> None:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 wav、mp3、m4a、flac 格式。")


def _save_upload(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with destination.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                out.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="单个音频文件不能超过 100MB。")
            out.write(chunk)
    upload.file.seek(0)
