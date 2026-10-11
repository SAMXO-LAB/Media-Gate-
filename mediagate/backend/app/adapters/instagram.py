"""Instagram adapter — Instagram API with Instagram Login.

What Meta permits (Oct 2026):
* The API only returns media owned by the *connected* Instagram professional account
  (Business or Creator). Personal accounts are not supported.
* `media_url` is the authorized file URL. Meta omits it for media that contains or is flagged
  for copyrighted material; we treat that as "not downloadable".
* There is no authorized API that returns files (or, since Nov 2025, even thumbnails) for
  other people's posts, so for those we show only the link and explain why.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

from app.adapters.base import (ConnectionToken, OAuthStart, PlatformAdapter, ResolvedMedia, SourcePlan)
from app.core.config import get_settings
from app.core.errors import AppError, PlatformError
from app.models.schemas import DownloadEligibility, DownloadReason, MediaFormat, MediaInfo
from app.net.safe_http import MEDIA_HOSTS, SafeHttpClient
from app.net.url_validation import ParsedMediaUrl, Platform

AUTHORIZE = "https://www.instagram.com/oauth/authorize"
TOKEN = "https://api.instagram.com/oauth/access_token"
GRAPH = "https://graph.instagram.com"
SCOPES = "instagram_business_basic"
MAX_PAGES = 10          # 10 × 50 = most recent 500 posts
FIELDS = ("id,caption,media_type,media_product_type,media_url,thumbnail_url,permalink,timestamp,username,"
          "children{id,media_type,media_url,thumbnail_url}")


def _shortcode(permalink: str | None) -> str | None:
    if not permalink:
        return None
    parts = [p for p in urlsplit(permalink).path.split("/") if p]
    for i, p in enumerate(parts):
        if p in ("p", "reel", "reels", "tv") and i + 1 < len(parts):
            return parts[i + 1]
    return None


class InstagramAdapter(PlatformAdapter):
    platform = Platform.instagram
    display_name = "Instagram"
    connectable = True
    capabilities = {"metadata": True, "formats": True, "download": True, "requires_connection": True,
                    "own_content_only": True}
    summary = ("Connect an Instagram Business or Creator account to download your own posts and reels. "
               "Meta provides no authorized access to other accounts' media.")
    url_patterns = ("instagram.com/p/{code}", "instagram.com/reel/{code}", "instagram.com/tv/{code}",
                    "instagram.com/{user}/p/{code}")

    @property
    def _ver(self) -> str:
        return get_settings().instagram_graph_version

    def missing_config(self) -> list[str]:
        s = get_settings()
        missing = []
        if not s.instagram_app_id:
            missing.append("INSTAGRAM_APP_ID")
        if not s.instagram_app_secret.get_secret_value():
            missing.append("INSTAGRAM_APP_SECRET")
        return missing

    # ---- resolve ------------------------------------------------------------
    async def resolve(self, parsed: ParsedMediaUrl, *, http: SafeHttpClient,
                      connection: ConnectionToken | None, signed_in: bool) -> ResolvedMedia:
        base = MediaInfo(platform=self.platform, media_id=parsed.media_id, canonical_url=parsed.canonical_url)
        notices = ["Instagram only shares media with the account that owns it, so previews and downloads "
                   "work for posts from your connected professional account."]

        if not self.configured:
            return ResolvedMedia(info=base, formats=[], notices=notices, eligibility=DownloadEligibility(
                allowed=False, reason=DownloadReason.platform_not_configured,
                message="Instagram support isn't configured on this server yet."))
        if not signed_in:
            return ResolvedMedia(info=base, formats=[], notices=notices, eligibility=DownloadEligibility(
                allowed=False, reason=DownloadReason.sign_in_required, action="sign_in",
                message="Sign in and connect your Instagram professional account to download your own posts."))
        if connection is None:
            return ResolvedMedia(info=base, formats=[], notices=notices, eligibility=DownloadEligibility(
                allowed=False, reason=DownloadReason.not_connected, action="connect",
                message="Connect the Instagram Business or Creator account that published this post."))

        item = await self._find_own_media(parsed.media_id, http=http, token=connection.access_token)
        if item is None:
            who = f"@{connection.account_name}" if connection.account_name else "your connected account"
            return ResolvedMedia(info=base, formats=[], notices=notices, eligibility=DownloadEligibility(
                allowed=False, reason=DownloadReason.not_owner,
                message=(f"This post isn't one of {who}'s recent posts. Instagram only allows downloading "
                         "media you own.")))

        return self._build(parsed, item, notices)

    async def _find_own_media(self, shortcode: str, *, http: SafeHttpClient, token: str) -> dict | None:
        url = f"{GRAPH}/{self._ver}/me/media"
        params: dict | None = {"fields": FIELDS, "limit": 50}
        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(MAX_PAGES):
            resp = await http.get(url, params=params, headers=headers)
            if resp.status_code in (400, 401, 403) and _is_token_error(resp):
                raise AppError("Your Instagram connection expired. Please reconnect your account.",
                               code="connection_expired", status_code=401)
            self.raise_for_upstream(resp, not_found_message="Instagram media not found.")
            try:
                body = resp.json()
            except ValueError as exc:
                raise PlatformError("Instagram returned an unreadable response.") from exc
            for item in body.get("data", []):
                if _shortcode(item.get("permalink")) == shortcode:
                    return item
            nxt = body.get("paging", {}).get("next")
            if not nxt:
                return None
            # `next` is a full URL from Meta; it is re-vetted against the API allowlist by SafeHttpClient.
            url, params = nxt, None
        return None

    def _build(self, parsed: ParsedMediaUrl, item: dict, notices: list[str]) -> ResolvedMedia:
        mtype = item.get("media_type")
        product = (item.get("media_product_type") or "").lower()
        caption = (item.get("caption") or "").strip()
        title = (caption.splitlines()[0][:140] if caption else None) or f"Instagram {product or 'post'}"
        published = None
        if item.get("timestamp"):
            try:
                published = datetime.strptime(item["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                pass
        info = MediaInfo(platform=self.platform, media_id=parsed.media_id, canonical_url=parsed.canonical_url,
                         title=title, author=item.get("username"),
                         thumbnail_url=item.get("thumbnail_url") or (item.get("media_url") if mtype == "IMAGE" else None),
                         published_at=published,
                         media_type="reel" if product == "reels" else (mtype or "").lower() or None)

        entries: list[tuple[str, dict]] = []
        if mtype == "CAROUSEL_ALBUM":
            for n, child in enumerate(item.get("children", {}).get("data", []), start=1):
                entries.append((f"item{n}", child))
            if not info.thumbnail_url and entries:
                first = entries[0][1]
                info.thumbnail_url = first.get("thumbnail_url") or first.get("media_url")
        else:
            entries.append(("orig", item))

        formats: list[MediaFormat] = []
        sources: dict[str, SourcePlan] = {}
        withheld = False
        for prefix, entry in entries:
            et = entry.get("media_type")
            murl = entry.get("media_url")
            label_prefix = "" if prefix == "orig" else f"Item {prefix[4:]} · "
            if not murl:
                withheld = True
                formats.append(MediaFormat(id=f"{prefix}", label=f"{label_prefix}Original", kind="video" if et == "VIDEO" else "image",
                                           available=False, unavailable_reason="Withheld by Instagram (copyright)"))
                continue
            if not MEDIA_HOSTS.allows(urlsplit(murl).hostname or ""):
                formats.append(MediaFormat(id=prefix, label=f"{label_prefix}Original", kind="image",
                                           available=False, unavailable_reason="Unexpected media host"))
                continue
            if et == "VIDEO":
                formats.append(MediaFormat(id=prefix, label=f"{label_prefix}Original video · MP4", kind="video",
                                           container="mp4"))
                sources[prefix] = SourcePlan(murl, "remux_mp4", "video/mp4", "mp4")
                aid = f"{prefix}-audio"
                formats.append(MediaFormat(id=aid, label=f"{label_prefix}Audio only · M4A", kind="audio",
                                           container="m4a", derived=True))
                sources[aid] = SourcePlan(murl, "extract_m4a", "audio/mp4", "m4a")
            else:
                formats.append(MediaFormat(id=prefix, label=f"{label_prefix}Original image · JPG", kind="image",
                                           container="jpg"))
                sources[prefix] = SourcePlan(murl, "passthrough", "image/jpeg", "jpg")

        if sources:
            elig = DownloadEligibility(allowed=True, reason=DownloadReason.allowed,
                                       message="This is your post, so you can download the original file.")
            notices.append("Instagram doesn't report resolution or file size; you'll get the original file it provides.")
        elif withheld:
            elig = DownloadEligibility(allowed=False, reason=DownloadReason.copyright_withheld,
                                       message="Instagram withheld this file because it contains copyrighted material.")
        else:
            elig = DownloadEligibility(allowed=False, reason=DownloadReason.no_media,
                                       message="This post has no downloadable media.")
        return ResolvedMedia(info=info, formats=formats, eligibility=elig, sources=sources, notices=notices)

    # ---- OAuth --------------------------------------------------------------
    def start_oauth(self, *, state: str, redirect_uri: str) -> OAuthStart:
        self.ensure_configured()
        q = urlencode({"client_id": get_settings().instagram_app_id, "redirect_uri": redirect_uri,
                       "response_type": "code", "scope": SCOPES, "state": state})
        return OAuthStart(authorize_url=f"{AUTHORIZE}?{q}")

    async def exchange_code(self, *, code: str, redirect_uri: str, code_verifier: str | None,
                            http: SafeHttpClient) -> ConnectionToken:
        s = get_settings()
        resp = await http.post(TOKEN, data={
            "client_id": s.instagram_app_id, "client_secret": s.instagram_app_secret.get_secret_value(),
            "grant_type": "authorization_code", "redirect_uri": redirect_uri, "code": code})
        if resp.status_code >= 400:
            raise AppError("Instagram didn't accept the authorization. Please try connecting again.",
                           code="oauth_failed", status_code=400)
        body = resp.json()
        if isinstance(body.get("data"), list) and body["data"]:
            body = body["data"][0]
        short = body["access_token"]

        ll = await http.get(f"{GRAPH}/access_token", params={
            "grant_type": "ig_exchange_token", "client_secret": s.instagram_app_secret.get_secret_value(),
            "access_token": short})
        self.raise_for_upstream(ll, not_found_message="Instagram token exchange failed.")
        llb = ll.json()
        token = llb["access_token"]
        expires = datetime.now(timezone.utc) + timedelta(seconds=int(llb.get("expires_in", 5_184_000)))

        me = await http.get(f"{GRAPH}/{self._ver}/me", params={"fields": "user_id,username"},
                            headers={"Authorization": f"Bearer {token}"})
        self.raise_for_upstream(me, not_found_message="Instagram account not found.")
        meb = me.json()
        return ConnectionToken(access_token=token, account_id=str(meb.get("user_id") or meb.get("id")),
                               account_name=meb.get("username"), expires_at=expires, scopes=SCOPES)

    async def refresh(self, token: ConnectionToken, *, http: SafeHttpClient) -> ConnectionToken:
        # Long-lived tokens last 60 days and can be refreshed once they are at least 24h old.
        if token.expires_at and token.expires_at - datetime.now(timezone.utc) > timedelta(days=7):
            return token
        resp = await http.get(f"{GRAPH}/refresh_access_token",
                              params={"grant_type": "ig_refresh_token", "access_token": token.access_token})
        if resp.status_code >= 400:
            return token  # caller surfaces "connection expired" on next API failure
        b = resp.json()
        token.access_token = b["access_token"]
        token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(b.get("expires_in", 5_184_000)))
        return token


def _is_token_error(resp) -> bool:
    try:
        err = resp.json().get("error", {})
        return err.get("type") == "OAuthException" or err.get("code") in (190, 102)
    except (ValueError, AttributeError):
        return False
