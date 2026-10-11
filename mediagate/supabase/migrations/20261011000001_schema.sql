-- MediaGate schema. Downloaded media is never stored permanently: result objects live in a
-- private storage bucket and are deleted when downloads.expires_at passes (default 1 hour).

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- profiles
create table public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  email        text,
  display_name text,
  role         text not null default 'user' check (role in ('user', 'admin')),
  is_blocked   boolean not null default false,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index profiles_email_idx on public.profiles (lower(email));

-- ---------------------------------------------------------------- platform configuration
create table public.platform_config (
  platform    text primary key check (platform in ('youtube', 'instagram', 'x')),
  enabled     boolean not null default true,
  notes       text,
  updated_by  uuid references public.profiles (id) on delete set null,
  updated_at  timestamptz not null default now()
);

create table public.app_settings (
  key         text primary key,
  value       jsonb not null,
  updated_by  uuid references public.profiles (id) on delete set null,
  updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------- platform account connections
-- Tokens are Fernet-encrypted by the API before insert; clients can never read these columns.
create table public.platform_connections (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references public.profiles (id) on delete cascade,
  platform           text not null check (platform in ('instagram', 'x')),
  account_id         text not null,
  account_name       text,
  access_token_enc   text not null,
  refresh_token_enc  text,
  expires_at         timestamptz,
  scopes             text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (user_id, platform)
);

create table public.oauth_states (
  state_hash         text primary key,
  user_id            uuid not null references public.profiles (id) on delete cascade,
  platform           text not null,
  code_verifier_enc  text,
  expires_at         timestamptz not null,
  created_at         timestamptz not null default now()
);
create index oauth_states_expires_idx on public.oauth_states (expires_at);

-- ---------------------------------------------------------------- jobs
create table public.jobs (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references public.profiles (id) on delete cascade,
  platform       text not null check (platform in ('youtube', 'instagram', 'x')),
  media_id       text not null check (length(media_id) <= 64),
  format_id      text not null check (length(format_id) <= 64),
  operation      text not null check (operation in ('passthrough', 'remux_mp4', 'extract_m4a')),
  title          text check (length(title) <= 200),
  status         text not null default 'queued'
                 check (status in ('queued','downloading','processing','uploading','completed','failed','cancelled','expired')),
  progress       real check (progress is null or (progress >= 0 and progress <= 1)),
  error_code     text,
  error_message  text,
  attempts       int not null default 0,
  locked_by      text,
  locked_at      timestamptz,
  heartbeat_at   timestamptz,
  started_at     timestamptz,
  finished_at    timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create index jobs_user_created_idx on public.jobs (user_id, created_at desc);
create index jobs_queue_idx on public.jobs (created_at) where status = 'queued';
create index jobs_active_idx on public.jobs (heartbeat_at) where status in ('downloading','processing','uploading');
create index jobs_failed_idx on public.jobs (finished_at desc) where status = 'failed';

-- Server-only: the authorized media URL resolved from the platform API. Deleted when the job ends.
create table public.job_sources (
  job_id             uuid primary key references public.jobs (id) on delete cascade,
  source_url         text not null,
  content_type       text not null,
  extension          text not null check (extension in ('mp4','m4a','jpg','png','webp')),
  expected_duration  real,
  created_at         timestamptz not null default now()
);

-- ---------------------------------------------------------------- downloads (temporary results)
create table public.downloads (
  id              uuid primary key default gen_random_uuid(),
  job_id          uuid not null references public.jobs (id) on delete cascade,
  user_id         uuid not null references public.profiles (id) on delete cascade,
  storage_key     text not null,
  filename        text not null,
  content_type    text not null,
  size_bytes      bigint,
  expires_at      timestamptz not null,
  deleted_at      timestamptz,
  download_count  int not null default 0,
  last_link_at    timestamptz,
  created_at      timestamptz not null default now()
);
create index downloads_user_idx on public.downloads (user_id, created_at desc);
create index downloads_expiry_idx on public.downloads (expires_at) where deleted_at is null;
create unique index downloads_job_live_idx on public.downloads (job_id) where deleted_at is null;

-- ---------------------------------------------------------------- usage statistics
create table public.usage_events (
  id           bigint generated always as identity primary key,
  event        text not null check (event in ('analyze','job_created','job_completed','job_failed','download_link')),
  user_id      uuid references public.profiles (id) on delete set null,
  platform     text,
  status_code  int,
  error_code   text,
  created_at   timestamptz not null default now()
);
create index usage_events_created_idx on public.usage_events (created_at desc);
create index usage_events_event_idx on public.usage_events (event, created_at desc);

create view public.usage_daily with (security_invoker = true) as
  select date_trunc('day', created_at)::date as day, event, platform, count(*)::int as total
  from public.usage_events group by 1, 2, 3;

-- ---------------------------------------------------------------- admin audit
create table public.admin_audit (
  id          bigint generated always as identity primary key,
  admin_id    uuid references public.profiles (id) on delete set null,
  action      text not null,
  target      text,
  detail      jsonb,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------- optional subscriptions
create table public.subscriptions (
  user_id               uuid primary key references public.profiles (id) on delete cascade,
  plan                  text not null default 'free' check (plan in ('free', 'pro', 'team')),
  status                text not null default 'active' check (status in ('active','trialing','past_due','canceled')),
  provider              text,
  provider_customer_id  text,
  current_period_end    timestamptz,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);
