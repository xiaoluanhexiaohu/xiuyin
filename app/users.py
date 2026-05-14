"""User lookup and password verification for the web MVP."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    """Authenticated application user."""

    username: str
    sub: str


def get_user(username: str) -> User | None:
    """Return the configured MVP user when the username matches."""

    configured = os.getenv("XIUYIN_ADMIN_USERNAME", "admin")
    if not hmac.compare_digest(username, configured):
        return None
    return User(username=configured, sub=configured)


def verify_password(username: str, password: str) -> bool:
    """Verify a password against the configured hash without hard-coded plaintext."""

    if get_user(username) is None:
        return False
    password_hash = os.getenv("XIUYIN_ADMIN_PASSWORD_HASH", "")
    if not password_hash:
        return False
    return verify_password_hash(password, password_hash)


def verify_password_hash(password: str, password_hash: str) -> bool:
    """Verify supported password hash formats.

    Supported formats:
    - ``pbkdf2_sha256$iterations$salt$hex_digest``
    - ``sha256$hex_digest`` for lightweight local testing only
    """

    parts = password_hash.split("$")
    if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
        iterations = int(parts[1])
        salt = parts[2].encode("utf-8")
        expected = parts[3]
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()
        return hmac.compare_digest(actual, expected)
    if len(parts) == 2 and parts[0] == "sha256":
        actual = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(actual, parts[1])
    return False


def hash_user_sub(sub: str) -> str:
    """Create a stable non-human-readable user directory hash."""

    secret = os.getenv("XIUYIN_JWT_SECRET", "xiuyin-dev-secret")
    return hashlib.sha256(f"{secret}:{sub}".encode("utf-8")).hexdigest()[:24]
