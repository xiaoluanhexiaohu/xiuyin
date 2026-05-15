# API Overview

All `/api/v1/*` endpoints require a Bearer token from `POST /auth/token`.

## Upload or recording

`POST /api/v1/audio/upload` multipart fields:
- `file`: webm/mp4/wav/mp3/m4a/flac
- `kind`: `user_vocal` or `reference_audio`
- `source`: `upload` or `recording`

Returns `audio_id`, duration, sample rate, normalized WAV path/storage key, and warnings.

## Search references

`POST /api/v1/reference/search` JSON:

```json
{"source":"jamendo","query":"acoustic vocal","page":1,"page_size":10}
```

Spotify/YouTube results are metadata-only; backend import/download is forbidden.

## Create correction job

`POST /api/v1/pitch-correction/jobs` JSON:

```json
{
  "reference_audio_id": "...",
  "user_audio_id": "...",
  "options": {
    "auto_locate_segment": true,
    "correction_strength": 0.75,
    "keep_vibrato_ratio": 0.6,
    "max_shift_cents": 300,
    "separation": false,
    "ai_assist": false
  }
}
```

Poll `GET /api/v1/pitch-correction/jobs/{job_id}` and fetch artifact links with `GET /api/v1/pitch-correction/jobs/{job_id}/artifacts`.
