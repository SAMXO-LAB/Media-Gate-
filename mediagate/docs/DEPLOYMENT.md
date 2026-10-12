# Deployment

Three deployables plus Supabase:

| Component | Runs | Scale |
|---|---|---|
| `frontend/` | Next.js (Vercel, or the Docker image) | stateless |
| `backend/` API | `uvicorn app.main:app` | stateless; >1 replica needs `REDIS_URL` |
| `backend/` worker | `python -m app.worker.main` | horizontally; jobs claimed with `SKIP LOCKED` |
| Supabase | Postgres, Auth, Storage (`media-temp` private bucket) | managed |

## 1. Database
```bash
npm i -g supabase            # or use npx
supabase link --project-ref YOUR-REF
supabase db push             # applies supabase/migrations/*.sql in order
```
Or paste the three files, in order, into the SQL editor. Then make yourself admin:
```sql
update public.profiles set role = 'admin' where email = 'you@example.com';
```
The third migration creates the private `media-temp` bucket (500 MB object limit). No storage policies
are added on purpose: only the service role can touch it; users get signed URLs.

## 2. Backend API
Requirements: Python 3.12+, FFmpeg ≥ 5 (`ffmpeg` and `ffprobe` on PATH, or `FFMPEG_PATH`/`FFPROBE_PATH`).

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # fill in
uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
```
Docker: `docker build -t mediagate-backend backend/` then run with `--env-file .env -p 8000:8000`.
Good hosts: Fly.io, Render, Railway, Cloud Run (API), any container platform.
Put it behind HTTPS (the platform's TLS or a reverse proxy) and set `TRUST_PROXY_HEADERS=true` only then.

## 3. Worker
Same image, different command:
```bash
docker run --env-file .env mediagate-backend python -m app.worker.main
```
- Needs FFmpeg (included in the image), outbound HTTPS to platform CDNs, and writable `TEMP_DIR`.
- Size CPU/RAM for `WORKER_CONCURRENCY` (remux/copy is cheap; audio transcode uses ~1 core per job).
- Don't run the worker on scale-to-zero platforms; it must stay up to process jobs and run cleanup.
- Graceful shutdown: SIGTERM stops claiming, waits up to 60 s for running jobs; anything interrupted is
  requeued by the stale-job sweeper (max 3 attempts).

## 4. Frontend
```bash
cd frontend
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
npm ci && npm run build && npm start
```
Vercel: see **Vercel (single project with Services)** below. Docker: see `frontend/Dockerfile`
(build args are inlined at build time). Add the frontend origin to the backend's `CORS_ORIGINS`.

## Vercel (single project with Services)
`vercel.json` sits at the **repository root** (next to the `mediagate/` folder) and defines two services
on one domain:

| Service | Root | Public path | Notes |
|---|---|---|---|
| `backend` | `mediagate/backend` | `/api/*` | FastAPI as a Vercel Function (`app.main:app`); receives the full path, e.g. `/api/analyze` |
| `frontend` | `mediagate/frontend` | everything else | Next.js; calls `/api/*` on its own origin from the browser |

No service bindings: the frontend only calls the API from the browser, and the API never calls the frontend.

**The worker cannot run on Vercel.** It is a long-running process (job queue loop, FFmpeg, cleanup every
minute). Run it on Render, Railway or Fly.io with the backend Docker image and
`python -m app.worker.main`, using the same `DATABASE_URL`, Supabase and platform settings. Without it,
download jobs stay queued (analysis still works).

Steps:
1. New Project → import the repo → Root Directory `./` → Application Preset **Services** (Vercel reads `vercel.json`).
2. Environment variables (shared by both services):
   - Backend: everything in `.env.example` except `TEMP_DIR`, plus `STORAGE_BACKEND=supabase`,
     `TRUST_PROXY_HEADERS=true`, `REDIS_URL` (e.g. Upstash — needed because each function instance
     otherwise keeps its own rate-limit counters), `PUBLIC_API_URL` and `FRONTEND_URL` = your Vercel domain,
     `CORS_ORIGINS` = your Vercel domain.
   - `DATABASE_URL`: use the Supabase **transaction pooler** (port 6543); each function instance opens at most 3 connections.
   - Frontend: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Leave `NEXT_PUBLIC_API_URL` **unset** (same origin).
3. Settings → Functions → Function Region: pick the region closest to your Supabase project.
4. Deploy, then check `https://<domain>/api/healthz` and `/api/readyz` (`ffmpeg: not_installed` is expected on Vercel).
5. OAuth redirect URIs become `https://<domain>/api/connections/{instagram|x}/callback`; add
   `https://<domain>/auth/callback` in Supabase Auth → URL configuration.
6. Local: `vercel dev` runs both services; or run uvicorn + `next dev` with `NEXT_PUBLIC_API_URL=http://localhost:8000`.

## 5. All-in-one (single host)
```bash
cp .env.example .env
docker compose up --build -d
docker compose --profile redis up -d   # if you scale the API
```

## FFmpeg
- Debian/Ubuntu: `apt-get install ffmpeg` · macOS: `brew install ffmpeg` · Alpine: `apk add ffmpeg`.
- Used operations: stream-copy remux to MP4 (`+faststart`), audio extraction to M4A (copy, or AAC 192k).
- Hardening in `app/worker/ffmpeg.py`: argv lists (no shell), forced `mov` demuxer, `file`-only protocols,
  `-threads 2`, hard timeout, paths confined to the job's work dir.

## Logging & monitoring
- Logs are JSON on stdout (`ts, level, logger, msg, request_id, job_id, platform, status, duration_ms`).
  Tokens and credentials are redacted; request query strings and file paths aren't logged.
- Every response carries `X-Request-ID` (honors an incoming one) for tracing across proxy → API.
- Health: API `/healthz` (liveness), `/readyz` (DB + ffmpeg → 503 when degraded); worker `:8081/healthz`.
- Alert on: `/readyz` failing; admin overview `oldest_queued_seconds > 120` (worker down/undersized);
  `jobs_failed / (completed+failed) > 10%`; error codes `platform_quota`, `platform_billing`,
  `platform_permission_denied` (credential or billing problems); 5xx rate.
- Ship logs to your platform's log drain (Datadog, Grafana Loki, Better Stack…). Sentry can be added
  via `sentry-sdk[fastapi]` with `send_default_pii=False`.

## Testing
```bash
cd backend && pip install -r requirements-dev.txt
pytest                                    # unit + API + SSRF + ffmpeg tests
# DB integration (RLS, queue, cleanup, end-to-end worker) against a disposable Postgres:
createdb mg_test && psql mg_test -f tests/supabase_stub.sql
for f in ../supabase/migrations/*.sql; do psql mg_test -f "$f"; done
TEST_DATABASE_URL=postgresql://localhost/mg_test pytest tests/test_db_integration.py
cd ../frontend && npm run typecheck && npm run build
```

## Production checklist
- [ ] `APP_ENV=production`, HTTPS everywhere, `CORS_ORIGINS` exact.
- [ ] `TOKEN_ENCRYPTION_KEY`, `STATE_SIGNING_KEY` generated fresh and stored in a secret manager.
- [ ] Supabase service key only on API/worker hosts.
- [ ] `REDIS_URL` set if more than one API replica.
- [ ] Instagram App Review + Business Verification complete; X credits funded with a spend alert.
- [ ] Egress firewall (defense in depth): worker allowed to `*.cdninstagram.com`, `*.fbcdn.net`,
      `video.twimg.com`, `pbs.twimg.com`, Supabase; API to the platform API hosts and Supabase.
- [ ] Terms of use and privacy policy published; DMCA/takedown contact listed.
