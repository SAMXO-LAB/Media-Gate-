# MediaGate API

Base URL: `PUBLIC_API_URL`. Interactive OpenAPI docs at `/docs` when `APP_ENV != production`.

**Auth** — `Authorization: Bearer <Supabase access token>`. Optional on `/api/analyze`, required elsewhere.

**Errors** — every non-2xx response:

```json
{ "error": { "code": "media_unavailable", "message": "That post wasn't found on X.", "details": null, "request_id": "9f2c…" } }
```

| Status | Typical codes |
|---|---|
| 400 | `invalid_url`, `unsupported_platform`, `unsupported_format`, `format_unavailable`, `blocked_destination`, `invalid_token` |
| 401 | `not_authenticated`, `token_expired`, `connection_expired` |
| 403 | `forbidden`, `account_blocked`, `download_<reason>` (e.g. `download_not_owner`, `download_platform_prohibits`) |
| 404 | `not_found`, `media_unavailable` (ownership failures also return 404, never 403, to avoid leaking IDs) |
| 409 | `too_many_active_jobs` |
| 410 | `expired` |
| 413 | `limit_exceeded`, `payload_too_large` |
| 422 | `validation_error` (field locations only; submitted values are never echoed) |
| 429 | `rate_limited`, `platform_rate_limited`, `platform_quota` (+ `Retry-After` header) |
| 502 | `platform_error`, `platform_permission_denied`, `storage_error` |
| 503 | `platform_not_configured`, `platform_billing`, `platform_disabled` |

---

### `POST /api/analyze`
Validate a link, fetch metadata and the platform's real formats, and report download eligibility.
Rate limit: `analyze` bucket (per user, else per IP).

```json
// request
{ "url": "https://x.com/someone/status/1800000000000000000" }
// 200
{
  "media":   { "platform": "x", "media_id": "1800…", "canonical_url": "https://x.com/i/web/status/1800…",
               "title": "…", "author": "@someone", "thumbnail_url": "https://pbs.twimg.com/…",
               "duration_seconds": 12.0, "published_at": "2025-06-01T10:00:00Z", "media_type": "video" },
  "formats": [ { "id": "v2176000", "label": "720p · MP4 · 2176 kbps", "kind": "video", "container": "mp4",
                 "width": 1280, "height": 720, "bitrate": 2176000, "filesize": null,
                 "derived": false, "available": true, "unavailable_reason": null } ],
  "download": { "allowed": true, "reason": "allowed", "message": "…", "action": null, "action_url": null },
  "notices": ["X doesn't report file sizes in advance."]
}
```
`download.reason` ∈ `allowed | platform_prohibits | not_connected | not_owner | copyright_withheld | sign_in_required | platform_not_configured | no_media`.
`download.action` tells the UI what to offer: `sign_in`, `connect`, `open_external` (+ `action_url`).

### `GET /api/platforms`
Per-platform `enabled`, `configured`, `missing` env var names, static `capabilities`, `summary`. Public.

### `POST /api/jobs` (alias `POST /api/download`) — auth
```json
{ "url": "https://x.com/someone/status/1800…", "format_id": "v2176000" }
```
→ `202` `JobResponse`. The server re-resolves the URL and re-checks permission; the media file URL never
leaves the server. Rate limit: `jobs` bucket. Per-user active-job cap (default 3).

### `GET /api/jobs` — auth
Your 20 most recent jobs.

### `GET /api/jobs/{job_id}` — auth (owner)
```json
{ "id": "…", "platform": "x", "media_id": "…", "format_id": "v2176000",
  "status": "processing", "progress": 0.82, "error_code": null, "error_message": null,
  "download_id": null, "created_at": "…", "updated_at": "…" }
```
`status`: `queued → downloading → processing → uploading → completed`, or `failed | cancelled | expired`.
`progress` is `null` when not measurable (e.g. no Content-Length).

### `DELETE /api/jobs/{job_id}` — auth (owner)
Cancels an active job, deletes any stored result. `204`.

### `GET /api/downloads/{download_id}` — auth (owner)
Mints a fresh signed URL (default validity 120 s). `410 expired` once the file's 1-hour lifetime ends.
```json
{ "download_id": "…", "url": "https://…/storage/v1/object/sign/…&download=clip_x-1800.mp4",
  "filename": "clip_x-1800.mp4", "content_type": "video/mp4", "size_bytes": 1234567,
  "expires_in": 120, "file_expires_at": "2026-10-11T17:00:00Z" }
```

### Connections — auth
| Method | Path | |
|---|---|---|
| GET | `/api/connections` | Status per platform (no tokens) |
| POST | `/api/connections/{instagram\|x}/start` | → `{ "authorize_url": "…" }` |
| GET | `/api/connections/{platform}/callback` | OAuth redirect target (browser); redirects to `FRONTEND_URL/connections?status=…` |
| DELETE | `/api/connections/{platform}` | Remove connection, `204` |

### Admin — auth + `profiles.role = 'admin'`
| Method | Path | |
|---|---|---|
| GET | `/api/admin/overview?hours=24` | Requests, job outcomes, queue depth/age, per-platform counts, recent errors |
| GET | `/api/admin/usage/daily?days=14` | `[ {day, event, n} ]` |
| GET | `/api/admin/users?q=&limit=&offset=` | Users with 7-day job counts |
| PATCH | `/api/admin/users/{id}` | `{ "role": "admin" \| "user", "is_blocked": bool }` (audited; can't demote/block yourself) |
| GET/PUT | `/api/admin/rate-limits` | `{ analyze_per_minute, jobs_per_minute, max_active_jobs_per_user }` |
| PUT | `/api/admin/platforms/{platform}` | `{ "enabled": bool }` |

### Health
`GET /healthz` (liveness), `GET /readyz` (DB + ffmpeg), worker `GET :8081/healthz` (loop not stalled).
