"""JWT/OAuth2 helpers for the upload-style web API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.users import User, get_user

TOKEN_EXPIRE_SECONDS = 3600
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def create_access_token(subject: str, expires_in: int = TOKEN_EXPIRE_SECONDS) -> str:
    """Create a compact HS256 JWT containing ``sub`` and ``exp``."""

    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": subject, "iat": now, "exp": now + int(expires_in)}
    signing_input = f"{_b64_json(header)}.{_b64_json(payload)}"
    signature = hmac.new(_jwt_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an HS256 JWT."""

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录已失效，请重新登录。",
        headers={"WWW-Authenticate": "Bearer"},
    )
    parts = token.split(".")
    if len(parts) != 3:
        raise credentials_error
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = hmac.new(_jwt_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64(expected), parts[2]):
        raise credentials_error
    payload = _json_from_b64(parts[1])
    if int(payload.get("exp", 0)) < int(time.time()):
        raise credentials_error
    if not payload.get("sub"):
        raise credentials_error
    return payload


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    """Return the current authenticated user from a Bearer token."""

    payload = decode_access_token(token)
    user = get_user(str(payload["sub"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已停用。",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _jwt_secret() -> bytes:
    return os.getenv("XIUYIN_JWT_SECRET", "xiuyin-dev-secret").encode("utf-8")


def _b64_json(value: dict[str, Any]) -> str:
    return _b64(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _json_from_b64(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
