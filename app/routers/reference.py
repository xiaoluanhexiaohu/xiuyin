"""Reference music search and compliant import API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.audio_registry import register_audio
from app.auth import get_current_user
from app.schemas import ReferenceImportRequest, ReferenceImportResponse, ReferenceSearchRequest, ReferenceSearchResponse
from app.users import User
from services.reference_providers import PROVIDERS, ReferenceProviderError

router = APIRouter(prefix="/api/v1/reference", tags=["reference"])

IMPORT_NOT_ALLOWED_MESSAGE = "Spotify/YouTube 仅支持搜索展示，不支持后台导入音频。请使用本地上传或选择 Jamendo/Freesound 可授权音频。"


def _provider(source: str):
    provider_cls = PROVIDERS.get(source)
    if provider_cls is None:
        raise HTTPException(status_code=400, detail={"error_code": "REFERENCE_PROVIDER_NOT_SUPPORTED", "message": f"Unsupported source: {source}"})
    return provider_cls()


def _error_status(error_code: str) -> int:
    """Map stable provider error codes to HTTP statuses."""

    return 400 if error_code in {"CONFIG_MISSING", "REFERENCE_IMPORT_NOT_ALLOWED", "REFERENCE_AUDIO_UNAUTHORIZED"} else 502


def _error_payload(exc: ReferenceProviderError) -> dict[str, str]:
    """Return the public error shape consumed by the frontend."""

    message = IMPORT_NOT_ALLOWED_MESSAGE if exc.error_code == "REFERENCE_IMPORT_NOT_ALLOWED" else exc.message
    return {"error_code": exc.error_code, "message": message}


def _http_error(exc: ReferenceProviderError) -> HTTPException:
    return HTTPException(status_code=_error_status(exc.error_code), detail=_error_payload(exc))


@router.options("/search")
def reference_search_options() -> dict[str, str]:
    """Allow unauthenticated CORS preflight checks for the public search endpoint."""

    return {"status": "ok"}


@router.post("/search", response_model=ReferenceSearchResponse)
async def search_reference(request: ReferenceSearchRequest) -> ReferenceSearchResponse | JSONResponse:
    """Search a configured third-party source for normalized reference metadata.

    This endpoint is intentionally public: it returns third-party metadata only
    and does not import, cache, or expose private user audio.
    """

    provider = _provider(request.source)
    try:
        items = await provider.search(request.query, request.page, request.page_size)
    except ReferenceProviderError as exc:
        return JSONResponse(status_code=_error_status(exc.error_code), content=_error_payload(exc))
    return ReferenceSearchResponse(items=items)


@router.post("/import", response_model=ReferenceImportResponse)
async def import_reference(
    request: ReferenceImportRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ReferenceImportResponse:
    """Import an authorized Jamendo/Freesound audio file and register it for pitch jobs."""

    provider = _provider(request.source)
    try:
        imported = await provider.import_track(request.track_id)
    except ReferenceProviderError as exc:
        raise _http_error(exc) from exc
    register_audio(
        current_user.sub,
        imported.audio_id,
        {
            "kind": "reference_audio",
            "source": imported.source,
            "normalized_path": imported.normalized_path,
            "local_path": imported.local_path,
            "title": imported.title,
            "artist": imported.artist,
            "license": imported.license,
            "authorization_notes": imported.authorization_notes,
        },
    )
    return ReferenceImportResponse(**imported.model_dump())
