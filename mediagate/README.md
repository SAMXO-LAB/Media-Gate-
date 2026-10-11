# MediaGate

A media analyzer and **authorized** downloader for YouTube, Instagram and X.
Paste a link → see real metadata and the formats the platform actually provides → download only what the
platform permits, via a link that expires in minutes. No scraping, no DRM or login bypass, no fake formats.

| Platform | What works | What doesn't, and why |
|---|---|---|
| YouTube | Title, thumbnail, duration (Data API v3) | Downloads — YouTube's terms forbid third-party downloading; the API has no download endpoint |
| Instagram | Preview + original file + audio extract **for your own posts** (connected Business/Creator account) | Other accounts' media — Meta's API doesn't expose it |
| X | Metadata + real MP4 bitrate variants for any public post; download **for posts you authored** | Others' media is shown but not downloadable (creator-rights policy) |

Full rationale and sources: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Stack
Next.js 15 + TypeScript + Tailwind + Framer Motion · FastAPI (async) · separate worker with FFmpeg ·
Supabase Postgres/Auth/Storage with RLS.

## Repository map
```
docs/            ARCHITECTURE (capability matrix, flow, security) · API · PLATFORM_SETUP · DEPLOYMENT
supabase/        SQL migrations: schema, RLS, functions/seed/bucket
backend/app/     core (config, auth, errors, rate limit, crypto, logging) · net (URL validation, SSRF-safe HTTP)
                 adapters (youtube, instagram, x) · services · routes · worker (processor, ffmpeg, cleanup)
backend/tests/   155 tests: URL validation, allowlists, SSRF, adapters, auth, rate limits, expiry, cleanup,
                 real FFmpeg, and Postgres integration (RLS, queue, end-to-end worker)
frontend/        app (analyzer, login, connections, admin) · components · lib
```

## Quick start (local)
```bash
cp .env.example .env                       # fill Supabase + whichever platforms you have keys for
supabase db push                           # or run supabase/migrations/*.sql in order
cd backend && pip install -r requirements-dev.txt
uvicorn app.main:app --reload              # API on :8000, docs at /docs
python -m app.worker.main                  # in another terminal
cd ../frontend && cp .env.local.example .env.local && npm install && npm run dev   # :3000
```
Platforms without credentials show a clear "Not configured" state. See [docs/PLATFORM_SETUP.md](docs/PLATFORM_SETUP.md).

## Tests
```bash
cd backend && pytest                       # DB tests run when TEST_DATABASE_URL is set (see DEPLOYMENT.md)
cd frontend && npm run typecheck && npm run build
```

## Responsible use
Operators are responsible for their platform agreements (Google API Services Terms, Meta Platform Terms,
X Developer Agreement), for publishing terms of use and a privacy policy, and for honoring takedown requests.
Processed files are deleted after `RESULT_TTL_SECONDS` (default 1 hour); nothing is stored permanently.
