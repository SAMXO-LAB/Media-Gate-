"""X (Twitter) adapter — X API v2.

* Metadata and real video variants come from GET /2/tweets/:id with media expansions.
  The X API is pay-per-use: each post read is billed, so analyze results are cached.
* Downloads are offered only when the signed-in user has connected the X account that
  authored the post. Media of other users is shown (metadata only) but not downloadable.
"""
from __future__ import annotations

import base64
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

from app.adapters.base import ConnectionToken, OAuthStart, PlatformAdapter, ResolvedMedia, SourcePlan
from app.core.config import get_settings
from app.core.errors import AppError, MediaUnavailable, PlatformError
from app.models.schemas import DownloadEligibility, DownloadReason, MediaFormat, MediaInfo
from app.net.safe_http import MEDIA_HOSTS, SafeHttpClient
from app.net.url_validation import ParsedMediaUrl, Platform

API = "https://api.x.com/2"
AUTHORIZE = "https://x.com/i/oauth2/authorize"
TOKEN = "https://api.x.com/2/oauth2/token"
SCOPES = "tweet.read users.read offline.access"
_RES = re.compile(r"/(\d{2,4})x(\d{2,4})/")


class XAdapter(PlatformAdapter):
    platform = Platform.x
    display_name = "X"
    connectable = True
    capabilities = {"metadata": True, "formats": True, "download": True, "requires_connection": True,
                    "own_content_only": True}
    summary = ("Metadata and real video variants via the X API. Downloads are available for posts "
               "you authored, after connecting your X account.")
    url_patterns = ("x.com/{user}/status/{id}", "twitter.com/{user}/status/{id}", "x.com/i/web/status/{id}")

    def missing_config(self) -> list[str]:
        s = get_settings()
        missing = []
        if not s.x_bearer_token.get_secret_value():
            missing.append("X_BEARER_TOKEN")
        if not s.x_client_id:
            missing.append("X_CLIENT_ID")
        return missing

    async def resolve(self, parsed: ParsedMediaUrl, *, http: SafeHttpClient,
                      connection: ConnectionToken | None, signed_in: bool) -> ResolvedMedia:
        s = get_settings()
        bearer = connection.access_token if connection else s.x_bearer_token.get_secret_value()
        if not bearer:
            self.ensure_configured()
        resp = await http.get(f"{API}/tweets/{parsed.media_id}", headers={"Authorization": f"Bearer {bearer}"},
                              params={"expansions": "attachments.media_keys,author_id",
                                      "media.fields": "type,duration_ms,preview_image_url,variants,width,height,url",
                                      "tweet.fields": "created_at,author_id,possibly_sensitive",
                                      "user.fields": "username,name"})
        if resp.status_code == 401 and connection:
            raise AppError("Your X connection expired. Please reconnect your account.",
                           code="connection_expired", status_code=401)
        self.raise_for_upstream(resp, not_found_message="That post wasn't found on X.")
        try:
            body = resp.json()
        except ValueError as exc:
            raise PlatformError("X returned an unreadable response.") from exc
        tweet = body.get("data")
        if not tweet:
            detail = (body.get("errors") or [{}])[0]
            if "Authorization" in (detail.get("title") or ""):
                raise MediaUnavailable("This post is from a protected account and isn't accessible.")
            raise MediaUnavailable("That post wasn't found, or it was deleted.")

        inc = body.get("includes", {})
        users = {u["id"]: u for u in inc.get("users", [])}
        author = users.get(tweet.get("author_id"), {})
        media = inc.get("media", [])
        text = (tweet.get("text") or "").strip()
        title = re.sub(r"\s*https://t\.co/\S+$", "", text)[:200] or None

        published = None
        if tweet.get("created_at"):
            try:
                published = datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00"))
            except ValueError:
                pass

        primary = next((m for m in media if m.get("type") in ("video", "animated_gif")), media[0] if media else None)
        info = MediaInfo(
            platform=self.platform, media_id=parsed.media_id, canonical_url=parsed.canonical_url,
            title=title, author=f"@{author['username']}" if author.get("username") else None,
            thumbnail_url=(primary or {}).get("preview_image_url") or (primary or {}).get("url"),
            duration_seconds=((primary or {}).get("duration_ms") or 0) / 1000 or None,
            published_at=published, media_type=(primary or {}).get("type"),
        )

        formats, sources, notices = self._formats(media)
        eligibility = self._eligibility(tweet.get("author_id"), connection, signed_in, bool(sources))
        if not eligibility.allowed:
            # Show what exists, but disable it with the reason.
            for f in formats:
                if f.available:
                    f.available = False
                    f.unavailable_reason = "Only the post's author can download"
            sources = {}
        return ResolvedMedia(info=info, formats=formats, eligibility=eligibility, sources=sources, notices=notices)

    def _formats(self, media: list[dict]) -> tuple[list[MediaFormat], dict[str, SourcePlan], list[str]]:
        limit = get_settings().max_duration_seconds
        formats: list[MediaFormat] = []
        sources: dict[str, SourcePlan] = {}
        notices: list[str] = []
        multi = len(media) > 1
        for idx, m in enumerate(media, start=1):
            prefix = f"m{idx}-" if multi else ""
            label_prefix = f"Item {idx} · " if multi else ""
            mtype = m.get("type")
            if mtype == "photo" and m.get("url"):
                fid = f"{prefix}photo"
                formats.append(MediaFormat(id=fid, label=f"{label_prefix}Original image",
                                           kind="image", container="jpg", width=m.get("width"), height=m.get("height")))
                if MEDIA_HOSTS.allows(urlsplit(m["url"]).hostname or ""):
                    sources[fid] = SourcePlan(m["url"] + "?name=orig" if "?" not in m["url"] else m["url"],
                                              "passthrough", "image/jpeg", "jpg")
                continue
            if mtype not in ("video", "animated_gif"):
                continue
            duration = (m.get("duration_ms") or 0) / 1000 or None
            too_long = bool(duration and duration > limit)
            mp4s = [v for v in m.get("variants", []) if v.get("content_type") == "video/mp4" and v.get("url")]
            if any(v.get("content_type") == "application/x-mpegURL" for v in m.get("variants", [])) and not mp4s:
                notices.append("X only provides a streaming playlist for this video, which isn't supported for download.")
            mp4s.sort(key=lambda v: v.get("bit_rate") or 0, reverse=True)
            for v in mp4s:
                w = h = None
                r = _RES.search(urlsplit(v["url"]).path)
                if r:
                    w, h = int(r.group(1)), int(r.group(2))
                br = v.get("bit_rate")
                parts = [f"{min(w, h)}p" if w and h else None, "MP4", f"{round(br / 1000)} kbps" if br else None]
                if mtype == "animated_gif":
                    parts[0] = "GIF as MP4"
                fid = f"{prefix}v{br or 0}"
                ok_host = MEDIA_HOSTS.allows(urlsplit(v["url"]).hostname or "")
                fmt = MediaFormat(id=fid, label=label_prefix + " · ".join(p for p in parts if p), kind="video",
                                  container="mp4", width=w, height=h, bitrate=br,
                                  available=ok_host and not too_long,
                                  unavailable_reason=("Longer than this server's limit" if too_long else
                                                      None if ok_host else "Unexpected media host"))
                formats.append(fmt)
                if fmt.available:
                    sources[fid] = SourcePlan(v["url"], "remux_mp4", "video/mp4", "mp4", duration)
            if mp4s and mtype == "video" and not too_long:
                best = mp4s[0]
                aid = f"{prefix}audio"
                formats.append(MediaFormat(id=aid, label=f"{label_prefix}Audio only · M4A", kind="audio",
                                           container="m4a", derived=True))
                sources[aid] = SourcePlan(best["url"], "extract_m4a", "audio/mp4", "m4a", duration)
        if formats and not any(f.filesize for f in formats):
            notices.append("X doesn't report file sizes in advance.")
        return formats, sources, notices

    def _eligibility(self, author_id: str | None, connection: ConnectionToken | None, signed_in: bool,
                     has_sources: bool) -> DownloadEligibility:
        if not has_sources:
            return DownloadEligibility(allowed=False, reason=DownloadReason.no_media,
                                       message="This post doesn't contain downloadable media.")
        if not signed_in:
            return DownloadEligibility(allowed=False, reason=DownloadReason.sign_in_required, action="sign_in",
                                       message="Sign in and connect your X account to download media from your own posts.")
        if connection is None:
            return DownloadEligibility(allowed=False, reason=DownloadReason.not_connected, action="connect",
                                       message="Connect your X account. Downloads are available for posts you authored.")
        if author_id and connection.account_id == author_id:
            return DownloadEligibility(allowed=True, reason=DownloadReason.allowed,
                                       message="You authored this post, so you can download its media.")
        return DownloadEligibility(allowed=False, reason=DownloadReason.not_owner,
                                   message=("This post belongs to another account. To respect creators' rights, "
                                            "only the author can download its media here."))

    # ---- OAuth 2.0 with PKCE ----------------------------------------------------
    def start_oauth(self, *, state: str, redirect_uri: str) -> OAuthStart:
        self.ensure_configured()
        verifier = secrets.token_urlsafe(64)[:96]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        q = urlencode({"response_type": "code", "client_id": get_settings().x_client_id,
                       "redirect_uri": redirect_uri, "scope": SCOPES, "state": state,
                       "code_challenge": challenge, "code_challenge_method": "S256"})
        return OAuthStart(authorize_url=f"{AUTHORIZE}?{q}", code_verifier=verifier)

    def _client_auth(self) -> dict[str, str]:
        s = get_settings()
        secret = s.x_client_secret.get_secret_value()
        if secret:  # confidential client
            raw = base64.b64encode(f"{s.x_client_id}:{secret}".encode()).decode()
            return {"Authorization": f"Basic {raw}"}
        return {}

    async def _token_request(self, data: dict, http: SafeHttpClient) -> dict:
        resp = await http.post(TOKEN, data={**data, "client_id": get_settings().x_client_id},
                               headers={"Content-Type": "application/x-www-form-urlencoded", **self._client_auth()})
        if resp.status_code >= 400:
            raise AppError("X didn't accept the authorization. Please try connecting again.",
                           code="oauth_failed", status_code=400)
        return resp.json()

    async def exchange_code(self, *, code: str, redirect_uri: str, code_verifier: str | None,
                            http: SafeHttpClient) -> ConnectionToken:
        if not code_verifier:
            raise AppError("Missing PKCE verifier.", code="oauth_failed")
        tok = await self._token_request({"grant_type": "authorization_code", "code": code,
                                         "redirect_uri": redirect_uri, "code_verifier": code_verifier}, http)
        me = await http.get(f"{API}/users/me", headers={"Authorization": f"Bearer {tok['access_token']}"})
        self.raise_for_upstream(me, not_found_message="X account not found.")
        user = me.json().get("data", {})
        return ConnectionToken(
            access_token=tok["access_token"], refresh_token=tok.get("refresh_token"),
            account_id=str(user.get("id")), account_name=user.get("username"), scopes=tok.get("scope"),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=int(tok.get("expires_in", 7200))))

    async def refresh(self, token: ConnectionToken, *, http: SafeHttpClient) -> ConnectionToken:
        if not token.refresh_token:
            return token
        if token.expires_at and token.expires_at - datetime.now(timezone.utc) > timedelta(minutes=5):
            return token
        tok = await self._token_request({"grant_type": "refresh_token", "refresh_token": token.refresh_token}, http)
        token.access_token = tok["access_token"]
        token.refresh_token = tok.get("refresh_token", token.refresh_token)
        token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(tok.get("expires_in", 7200)))
        return token
