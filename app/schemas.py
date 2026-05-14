"""Pydantic schemas for the MVP FastAPI layer."""

from __future__ import annotations

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
