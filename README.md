# Auto Tune MVP

Offline one-click singing correction MVP in Python. It analyzes a reference vocal and a user vocal, aligns them, creates a conservative pitch correction plan, and exports:

- `corrected_vocal.wav`
- `mix.wav`
- `report.json`

> MVP note: `core.renderer` is intentionally a placeholder. It writes the normalized user vocal as `corrected_vocal.wav` and records the correction plan/report. Real pitch-shift rendering is reserved for Rubber Band, WORLD, or a future neural renderer.

## Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional F0 backend:

```bash
pip install torch torchcrepe
```

System tools for future extensions: `ffmpeg`, optional `demucs`, optional `rubberband`.

## Run CLI

```bash
python -m jobs.batch_export --manifest examples/demo_manifest.json
```

The demo manifest references placeholder audio paths. If files are missing, the CLI returns a clear error. Replace them with real local paths to run an export.

## Run API

```bash
uvicorn app.main:app --reload
```

Endpoints:

- `GET /health`
- `POST /analyze/reference`
- `POST /analyze/user`
- `POST /align`
- `POST /correct`
- `POST /export`

The first API version accepts local file paths, not multipart uploads.

## Test

```bash
pytest
```

## Algorithm Overview

1. Load audio, resample, convert to mono, normalize.
2. Estimate F0 using `torchcrepe` when available, otherwise `librosa.pyin`.
3. Extract chroma, onset strength, and RMS features.
4. Align user to reference using DTW.
5. Generate `target_f0_hz` and `shift_cents` with conservative correction:
   - corrections are computed in cents/log pitch;
   - low confidence and unvoiced frames are skipped;
   - trend is corrected while vibrato residual is partially preserved;
   - large shifts are clipped by `max_shift_cents`.
6. Placeholder render and simple mix.
7. Write JSON report.

## License Risk Notes

Before commercial distribution, re-check all dependency and model licenses. Rubber Band usage may require special attention due to GPL/commercial licensing. Demucs/Spleeter code and model weights must also be reviewed separately.
