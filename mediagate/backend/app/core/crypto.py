"""Encryption of platform tokens at rest, and signed short-lived state values."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import AppError, Gone


def _fernet() -> Fernet:
    key = get_settings().token_encryption_key.get_secret_value()
    if not key:
        raise AppError("Token encryption is not configured.", code="server_misconfigured", status_code=500)
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise AppError("Stored credential could not be decrypted.", code="credential_error", status_code=500) from exc


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign(payload: dict[str, Any], ttl_seconds: int, *, key: bytes | None = None, now: float | None = None) -> str:
    """Compact HMAC-SHA256 token: base64(json).base64(sig). Includes exp and a nonce."""
    k = key or get_settings().state_signing_key.get_secret_value().encode()
    if not k:
        raise AppError("Signing key is not configured.", code="server_misconfigured", status_code=500)
    body = dict(payload, exp=int((now or time.time()) + ttl_seconds), n=secrets.token_urlsafe(8))
    raw = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64(hmac.new(k, raw.encode(), hashlib.sha256).digest())
    return f"{raw}.{sig}"


def verify(token: str, *, key: bytes | None = None, now: float | None = None) -> dict[str, Any]:
    k = key or get_settings().state_signing_key.get_secret_value().encode()
    try:
        raw, sig = token.split(".", 1)
        expected = _b64(hmac.new(k, raw.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            raise ValueError("bad signature")
        body = json.loads(_unb64(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError("Invalid or tampered token.", code="invalid_token", status_code=400) from exc
    if int(body.get("exp", 0)) < int(now or time.time()):
        raise Gone("This link has expired.")
    return body
