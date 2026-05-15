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


JobStatus = Literal["queued", "running", "completed", "succeeded", "needs_confirmation", "failed", "expired"]
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

AudioKind = Literal["user_vocal", "reference_audio"]
AudioSource = Literal["upload", "recording"]
ReferenceSource = Literal["jamendo", "freesound", "spotify", "youtube"]
PitchJobStatus = Literal["queued", "running", "needs_confirmation", "succeeded", "failed"]


class AudioUploadResponse(BaseModel):
    """Unified audio upload/recording response."""

    audio_id: str
    kind: AudioKind
    source: AudioSource
    duration_sec: float
    sample_rate: int
    channels: int
    normalized_path: str
    storage_key: str
    warnings: list[str] = Field(default_factory=list)


class ReferenceSearchRequest(BaseModel):
    """Third-party reference search request."""

    query: str = Field(min_length=1)
    source: ReferenceSource
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=50)


class ReferenceSearchItem(BaseModel):
    """One third-party reference result."""

    source: str
    track_id: str
    title: str
    artist: str | None = None
    duration_sec: float | None = None
    preview_url: str | None = None
    stream_url: str | None = None
    download_url: str | None = None
    license: str | None = None
    can_download: bool = False
    external_url: str | None = None
    authorization_notes: str = ""


class ReferenceSearchResponse(BaseModel):
    """Search response."""

    source: ReferenceSource
    results: list[ReferenceSearchItem]
    warnings: list[str] = Field(default_factory=list)


class PitchCorrectionOptions(BaseModel):
    """Options for API v1 pitch-correction jobs."""

    auto_locate_segment: bool = True
    correction_strength: float = Field(default=0.75, ge=0.0, le=1.0)
    keep_vibrato_ratio: float = Field(default=0.6, ge=0.0, le=1.0)
    max_shift_cents: float = Field(default=300.0, gt=0.0)
    separation: bool = False
    ai_assist: bool = False


class PitchCorrectionJobCreateRequest(BaseModel):
    """Create a pitch-correction job from uploaded audio ids."""

    reference_audio_id: str
    user_audio_id: str
    options: PitchCorrectionOptions = Field(default_factory=PitchCorrectionOptions)


class PitchCorrectionJobResponse(BaseModel):
    """API v1 pitch job status response."""

    job_id: str
    status: PitchJobStatus
    inputs: dict = Field(default_factory=dict)
    segment_match: dict | None = None
    options: dict = Field(default_factory=dict)
    artifacts: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    step_timings: dict = Field(default_factory=dict)
    error_code: str | None = None
    message: str = ""
