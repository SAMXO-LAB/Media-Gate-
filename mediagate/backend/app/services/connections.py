"""Platform account connections (OAuth) — tokens encrypted at rest, never sent to clients."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.adapters.base import ConnectionToken
from app.adapters.registry import get_adapter
from app.core import crypto
from app.core.config import get_settings
from app.core.errors import AppError, Gone
from app.net.safe_http import API_HOSTS, SafeHttpClient
from app.net.url_validation import Platform
from app.services.db import pool

STATE_TTL = timedelta(minutes=10)


def redirect_uri(platform: Platform) -> str:
    return f"{get_settings().public_api_url.rstrip('/')}/api/connections/{platform.value}/callback"


def _hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


async def start(user_id: UUID, platform: Platform) -> str:
    adapter = get_adapter(platform)
    state = secrets.token_urlsafe(32)
    started = adapter.start_oauth(state=state, redirect_uri=redirect_uri(platform))
    await pool().execute(
        "insert into public.oauth_states (state_hash, user_id, platform, code_verifier_enc, expires_at) "
        "values ($1, $2, $3, $4, $5)",
        _hash(state), user_id, platform.value,
        crypto.encrypt(started.code_verifier) if started.code_verifier else None,
        datetime.now(timezone.utc) + STATE_TTL)
    return started.authorize_url


async def finish(platform: Platform, *, state: str, code: str) -> UUID:
    """Complete OAuth. The state row binds the callback to the user who started it (CSRF guard)."""
    row = await pool().fetchrow(
        "delete from public.oauth_states where state_hash = $1 and platform = $2 "
        "returning user_id, code_verifier_enc, expires_at", _hash(state), platform.value)
    if row is None:
        raise AppError("This connection request is invalid or was already used.", code="invalid_state")
    if row["expires_at"] < datetime.now(timezone.utc):
        raise Gone("This connection request expired. Please try again.")
    verifier = crypto.decrypt(row["code_verifier_enc"]) if row["code_verifier_enc"] else None
    adapter = get_adapter(platform)
    async with SafeHttpClient(API_HOSTS, timeout=get_settings().http_timeout_seconds) as http:
        token = await adapter.exchange_code(code=code, redirect_uri=redirect_uri(platform),
                                            code_verifier=verifier, http=http)
    await save(row["user_id"], platform, token)
    return row["user_id"]


async def save(user_id: UUID, platform: Platform, token: ConnectionToken) -> None:
    await pool().execute(
        """insert into public.platform_connections
             (user_id, platform, account_id, account_name, access_token_enc, refresh_token_enc, expires_at, scopes)
           values ($1, $2, $3, $4, $5, $6, $7, $8)
           on conflict (user_id, platform) do update set
             account_id = excluded.account_id, account_name = excluded.account_name,
             access_token_enc = excluded.access_token_enc, refresh_token_enc = excluded.refresh_token_enc,
             expires_at = excluded.expires_at, scopes = excluded.scopes, updated_at = now()""",
        user_id, platform.value, token.account_id, token.account_name, crypto.encrypt(token.access_token),
        crypto.encrypt(token.refresh_token) if token.refresh_token else None, token.expires_at, token.scopes)


async def get_token(user_id: UUID, platform: Platform) -> ConnectionToken | None:
    row = await pool().fetchrow(
        "select account_id, account_name, access_token_enc, refresh_token_enc, expires_at, scopes "
        "from public.platform_connections where user_id = $1 and platform = $2", user_id, platform.value)
    if row is None:
        return None
    token = ConnectionToken(
        access_token=crypto.decrypt(row["access_token_enc"]), account_id=row["account_id"],
        account_name=row["account_name"],
        refresh_token=crypto.decrypt(row["refresh_token_enc"]) if row["refresh_token_enc"] else None,
        expires_at=row["expires_at"], scopes=row["scopes"])
    adapter = get_adapter(platform)
    before = (token.access_token, token.expires_at)
    async with SafeHttpClient(API_HOSTS, timeout=get_settings().http_timeout_seconds) as http:
        try:
            token = await adapter.refresh(token, http=http)
        except AppError:
            return token
    if (token.access_token, token.expires_at) != before:
        await save(user_id, platform, token)
    return token


async def list_for_user(user_id: UUID) -> dict[str, dict]:
    rows = await pool().fetch(
        "select platform, account_name, created_at from public.platform_connections where user_id = $1", user_id)
    return {r["platform"]: dict(r) for r in rows}


async def delete(user_id: UUID, platform: Platform) -> None:
    await pool().execute("delete from public.platform_connections where user_id = $1 and platform = $2",
                         user_id, platform.value)
