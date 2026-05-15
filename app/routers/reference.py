"""Reference search API."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.schemas import ReferenceSearchRequest, ReferenceSearchResponse
from app.users import User
from services.reference_providers import PROVIDERS

router = APIRouter(prefix="/api/v1/reference", tags=["reference"])


@router.post("/search", response_model=ReferenceSearchResponse)
def search_reference(
    request: ReferenceSearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ReferenceSearchResponse:
    """Search a configured third-party source for reference metadata."""

    provider_cls = PROVIDERS.get(request.source)
    if provider_cls is None:
        raise HTTPException(status_code=400, detail="Unsupported source")
    warnings: list[str] = []
    try:
        results = provider_cls().search(request.query, request.page, request.page_size)
    except Exception as exc:
        warnings.append(f"REFERENCE_SEARCH_FAILED: {exc}")
        results = []
    if request.source in {"spotify", "youtube"}:
        warnings.append("Spotify/YouTube are metadata-only; backend audio download/import is not allowed.")
    if request.source in {"jamendo", "freesound"} and not results:
        warnings.append("Provider API key may be missing or no licensed results were found.")
    return ReferenceSearchResponse(source=request.source, results=[asdict(r) for r in results], warnings=warnings)
