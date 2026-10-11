# MediaGate — Architecture & Platform Capabilities

MediaGate is a media analyzer and **authorized** downloader for YouTube, Instagram and X.
It only uses official APIs and only offers a download when the platform grants an
authorized path to the media file. Where no such path exists, the UI says so plainly.

## 1. What each platform actually permits (verified October 2026)

| Capability | YouTube | Instagram | X |
|---|---|---|---|
| Official API used | YouTube Data API v3 (`videos.list`) | Instagram API with Instagram Login (`graph.instagram.com`) | X API v2 (`GET /2/tweets/:id`) |
| Credentials | Google Cloud API key | Meta app (App ID/secret), user OAuth, App Review for production | X developer app, Bearer token + OAuth 2.0 PKCE client, **pay‑per‑use credits** |
| Public metadata (title, thumbnail, duration) | ✅ any public video | ⚠️ Only for the connected user's own media. Meta oEmbed no longer returns `thumbnail_url` / `author_name` (removed 3 Nov 2025) and needs App Review + business verification, so it is not used | ✅ any public post (billed per post read) |
| Real format list | ❌ API exposes no stream/format list | ✅ one original file (`media_url`), resolution not reported | ✅ `media.variants` (mp4 bitrates, HLS) |
| Authorized file download | ❌ **None.** YouTube ToS forbid downloading except via a download link YouTube itself provides. The Data API has no media download, even for owners | ✅ **Own content only**: the connected professional account's media via `media_url`. Meta omits `media_url` for media containing or flagged for copyrighted material — MediaGate treats that as "not downloadable" | ✅ **Own posts only** (MediaGate policy): variant URLs come from the API, but downloads are enabled only when the connected X user authored the post, to respect creators' rights and X's developer terms |
| What the UI shows when blocked | Metadata + "YouTube doesn't allow downloads through its API. Owners can download their uploads in YouTube Studio." | "Connect the Instagram professional account that owns this post" / "Instagram withheld this file (copyright)" | "Only the post's author can download this media here. Connect your X account." |
| Derived formats (FFmpeg) | — | MP4 remux (faststart), M4A audio extract | MP4 remux, M4A audio extract |

Notes
- Instagram personal accounts are not supported by Meta's API (Basic Display API shut down Dec 2024). Users must have a Business or Creator account.
- X API cost: post reads are billed per resource (≈ $0.005 at time of writing; check `docs.x.com/x-api/getting-started/pricing`). Metadata responses are cached for 10 minutes to limit spend.
- Platform rules change. Each adapter returns a `configured` flag and a `reason` so a missing key, missing approval or policy change surfaces as a clear UI state, never a fake result.

## 2. System overview

```
 Browser (Next.js)
   │  Supabase Auth (JWT)          ┌───────────────────────────┐
   ├──────────────────────────────▶│ Supabase (Postgres + Auth │
   │                               │  + private Storage bucket)│
   │  REST + Bearer JWT            └──────▲───────────▲────────┘
   ▼                                      │           │
 FastAPI API ──── asyncpg (service role) ─┘           │
   │  • URL validation, platform detection             │
   │  • adapters (metadata, formats, permission)       │
   │  • enqueue job row (status=queued)                │
   │                                                   │
 Worker (same codebase, separate process)              │
   • claims jobs with FOR UPDATE SKIP LOCKED           │
   • SSRF-safe download from allowlisted CDN hosts ────┘ upload result
   • FFmpeg via argv list (no shell)                     (expires in 1h)
   • cleanup loop: temp dir + expired objects + stale jobs
```

### Request flow
1. `POST /api/analyze` — server parses URL strictly, matches hostname allowlist, picks adapter. Adapter calls the official API and returns metadata, real formats and a `download` block (`allowed`, `reason_code`, `message`).
2. `POST /api/jobs` (alias `POST /api/download`) — auth required. Server **re-runs** the adapter permission check (never trusts the client), stores the resolved media URL server-side, inserts a `queued` job.
3. Worker claims job → streams the file with size cap → optional FFmpeg → uploads to private bucket → creates a `downloads` row with `expires_at`.
4. `GET /api/jobs/{id}` — status/progress (owner only).
5. `GET /api/downloads/{id}` — owner only; returns a **fresh signed URL valid 120 s**. Expired records return `410 Gone`.
6. `DELETE /api/jobs/{id}` — cancel / delete job and its files.

### Endpoint adjustments vs. the brief
- `POST /api/download` is kept as an alias of `POST /api/jobs` (clearer resource naming).
- Download links are never stored or returned at job completion; they are minted per request after an ownership check, so leaked job IDs are useless.
- OAuth connection endpoints added: `GET /api/connections`, `POST /api/connections/{platform}/start`, `GET /api/connections/{platform}/callback`, `DELETE /api/connections/{platform}`.
- Admin endpoints under `/api/admin/*` require `profiles.role = 'admin'`, checked server-side on every call.

## 3. Security model (summary)
- **SSRF**: outbound requests go through `SafeHttpClient`: https only, host allowlist per purpose (API hosts vs media CDN hosts), DNS resolved and every IP checked against private/loopback/link-local/reserved/metadata ranges, connection pinned to the vetted IP, redirects followed manually (max 3) with full re‑validation each hop.
- **Command injection**: FFmpeg invoked with `asyncio.create_subprocess_exec` and a fixed argv; file names are server-generated UUIDs; user strings never reach argv.
- **Files**: temp files live under one root, paths built from UUIDs and checked with `resolve().is_relative_to(root)`. Paths never appear in responses or logs.
- **Limits**: max file size, max duration, per-request timeout, worker concurrency, per-user active-job cap, rate limits per IP/user (configurable from admin dashboard).
- **Tokens**: platform OAuth tokens encrypted at rest (Fernet), never sent to the browser; log filter redacts `access_token`, `Authorization`, etc.
- **RLS** on all user tables; the API uses the service role but also filters by `user_id` in every query (defense in depth).
- **Headers**: CSP, HSTS, X-Content-Type-Options, Referrer-Policy, frame-ancestors none; strict CORS origin list.

## 4. Folder structure

```
mediagate/
├── README.md
├── .env.example
├── docker-compose.yml
├── docs/
│   ├── ARCHITECTURE.md        (this file)
│   ├── API.md
│   ├── PLATFORM_SETUP.md      how to obtain each credential
│   └── DEPLOYMENT.md
├── supabase/migrations/
│   ├── 0001_schema.sql
│   ├── 0002_rls.sql
│   └── 0003_seed_and_functions.sql
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt / requirements-dev.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py                     FastAPI app factory, middleware
│   │   ├── core/   config, errors, auth, ratelimit, logging, crypto, signing
│   │   ├── net/    url_validation, safe_http (SSRF guard)
│   │   ├── models/ schemas (Pydantic)
│   │   ├── adapters/ base, youtube, instagram, x, registry
│   │   ├── services/ db, jobs, storage, connections, admin, cache
│   │   ├── routes/ health, analyze, jobs, downloads, connections, admin
│   │   └── worker/ main, processor, ffmpeg, cleanup
│   └── tests/
└── frontend/
    ├── package.json, next.config.mjs, tailwind.config.ts, tsconfig.json
    ├── app/ layout, page (analyzer), login, auth/callback, connections, admin
    ├── components/ Navbar, Hero, UrlForm, PlatformBadge, MediaCard,
    │               FormatPicker, PermissionNotice, JobProgress, Toasts, admin/*
    └── lib/ api.ts, supabase.ts, types.ts, platform.ts
```
