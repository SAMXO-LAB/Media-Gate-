"""Supabase Auth JWT verification.

Supports both legacy HS256 project secrets (SUPABASE_JWT_SECRET) and the asymmetric
signing keys newer Supabase projects use (verified against the project's JWKS endpoint).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.errors import Forbidden, NotAuthenticated


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str | None
    is_admin: bool = False


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=5)


async def decode_token(token: str, settings: Settings) -> dict:
    opts = {"require": ["exp", "sub", "aud"]}
    try:
        secret = settings.supabase_jwt_secret.get_secret_value()
        if secret:
            return jwt.decode(token, secret, algorithms=["HS256"], audience=settings.supabase_jwt_audience,
                              options=opts, leeway=10)
        if not settings.supabase_url:
            raise NotAuthenticated("Authentication is not configured on the server.")
        client = _jwks_client(settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json")
        key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
        return jwt.decode(token, key.key, algorithms=["ES256", "RS256"], audience=settings.supabase_jwt_audience,
                          options=opts, leeway=10)
    except jwt.ExpiredSignatureError as exc:
        raise NotAuthenticated("Your session expired. Please sign in again.", code="token_expired") from exc
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        raise NotAuthenticated("Invalid session token.") from exc


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        tok = header[7:].strip()
        return tok or None
    return None


async def optional_user(request: Request, settings: Settings = Depends(get_settings)) -> CurrentUser | None:
    token = _bearer(request)
    if not token:
        return None
    claims = await decode_token(token, settings)
    try:
        uid = UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise NotAuthenticated("Invalid session token.") from exc
    from app.services.db import fetch_is_admin  # local import avoids a cycle
    is_admin = await fetch_is_admin(uid)
    user = CurrentUser(id=uid, email=claims.get("email"), is_admin=is_admin)
    request.state.user_id = str(uid)
    return user


async def require_user(user: CurrentUser | None = Depends(optional_user)) -> CurrentUser:
    if user is None:
        raise NotAuthenticated("Please sign in to continue.")
    return user


async def require_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    if not user.is_admin:
        raise Forbidden("Administrator access required.")
    return user
