# Xiuyin Incremental Upgrade Plan

This upgrade keeps the existing upload + batch flow and adds API-first building blocks for recording uploads, licensed reference search, segment location, plan-driven rendering, and future AI assist.

## Implemented in this phase
- Frame-level pitch renderer that consumes `CorrectionPlan` shifts and skips low-confidence/unvoiced frames.
- Unified `/api/v1/audio/upload` endpoint for uploaded files and browser recordings.
- Reference provider abstraction for Jamendo, Freesound, Spotify, and YouTube.
- Segment locator using energy VAD + chroma/RMS/onset sliding-window matching + DTW refinement.
- AI assist orchestration interface with fallback VAD/pitch backends.
- `/api/v1/pitch-correction/jobs` task API.

## Deferred
- Full neural APC training/inference.
- Production separation (Demucs), RMVPE, Silero, Basic Pitch adapters.
- Direct import/download implementation for licensed providers after license UX is finalized.
