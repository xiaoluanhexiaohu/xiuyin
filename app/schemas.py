"""Pydantic schemas for the MVP FastAPI layer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CorrectionParams(BaseModel):
    """User-adjustable correction parameters."""

    correction_strength: float = Field(default=0.75, ge=0.0, le=1.0)
    keep_vibrato_ratio: float = Field(default=0.6, ge=0.0, le=1.0)
    max_shift_cents: float = Field(default=300.0, gt=0.0)


class AnalyzeRequest(BaseModel):
    """Request to analyze one local audio path."""

    audio_path: str


class AlignRequest(BaseModel):
    """Request to align two local audio paths."""

    reference_audio: str
    user_audio: str


class CorrectRequest(AlignRequest):
    """Request to create a correction plan from two local audio paths."""

    params: CorrectionParams = Field(default_factory=CorrectionParams)


class ExportJobRequest(CorrectRequest):
    """Request to export corrected vocal, mix, and report."""

    accompaniment_audio: str | None = None
    output_dir: str
    id: str = "api_job"


JobStatus = Literal["queued", "running", "completed", "failed", "expired"]
JobStage = Literal[
    "upload",
    "normalize",
    "separate",
    "analyze",
    "align",
    "segment",
    "render",
    "mix",
    "package",
    "completed",
]
SyllableGranularity = Literal["conservative", "normal", "aggressive"]


class TokenResponse(BaseModel):
    """OAuth2 bearer token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class UploadResponse(BaseModel):
    """Response returned after a web job is queued."""

    job_id: str
    status: JobStatus
    status_url: str
    result_url: str


class JobStatusResponse(BaseModel):
    """Public job status response."""

    job_id: str
    status: JobStatus
    stage: str
    progress: float
    message: str
    warnings: list[str] = Field(default_factory=list)


class ArtifactUrls(BaseModel):
    """Download URLs for generated artifacts."""

    corrected_vocal: str
    mix: str
    report: str


class ResultResponse(BaseModel):
    """Completed result metadata returned before download."""

    job_id: str
    status: JobStatus
    completed_at: str
    expires_at: str
    bundle_url: str
    artifacts: ArtifactUrls
    actual_pitch_shift_applied: bool
    warnings: list[str] = Field(default_factory=list)
