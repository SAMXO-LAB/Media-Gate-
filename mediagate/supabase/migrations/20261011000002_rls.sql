-- Row Level Security. The FastAPI service connects with a privileged role (bypasses RLS) and
-- additionally filters by user_id in code. These policies govern any direct access through
-- Supabase's REST/Realtime APIs with a user JWT (role `authenticated`) or the anon key.

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where id = auth.uid() and role = 'admin' and not is_blocked);
$$;
revoke all on function public.is_admin() from public;
grant execute on function public.is_admin() to authenticated;

alter table public.profiles             enable row level security;
alter table public.platform_config      enable row level security;
alter table public.app_settings         enable row level security;
alter table public.platform_connections enable row level security;
alter table public.oauth_states         enable row level security;
alter table public.jobs                 enable row level security;
alter table public.job_sources          enable row level security;
alter table public.downloads            enable row level security;
alter table public.usage_events         enable row level security;
alter table public.admin_audit          enable row level security;
alter table public.subscriptions        enable row level security;

-- Start from zero privileges for client roles, then grant narrowly.
revoke all on all tables in schema public from anon, authenticated;

-- profiles: read own (admins read all); users may only edit display_name.
create policy profiles_select on public.profiles for select to authenticated
  using (id = auth.uid() or public.is_admin());
create policy profiles_update_self on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());
grant select on public.profiles to authenticated;
grant update (display_name) on public.profiles to authenticated;

-- platform_config: public read (drives UI capability badges).
create policy platform_config_read on public.platform_config for select to anon, authenticated using (true);
grant select on public.platform_config to anon, authenticated;

-- platform_connections: owners can see that a connection exists, never the tokens.
create policy connections_select_own on public.platform_connections for select to authenticated
  using (user_id = auth.uid());
create policy connections_delete_own on public.platform_connections for delete to authenticated
  using (user_id = auth.uid());
grant select (id, user_id, platform, account_name, created_at, updated_at) on public.platform_connections to authenticated;
grant delete on public.platform_connections to authenticated;

-- jobs / downloads: read own. All writes go through the API.
create policy jobs_select_own on public.jobs for select to authenticated
  using (user_id = auth.uid() or public.is_admin());
grant select (id, user_id, platform, media_id, format_id, title, status, progress, error_code, error_message,
              created_at, updated_at, finished_at) on public.jobs to authenticated;

create policy downloads_select_own on public.downloads for select to authenticated
  using (user_id = auth.uid());
grant select (id, job_id, user_id, filename, content_type, size_bytes, expires_at, deleted_at, created_at)
  on public.downloads to authenticated;

create policy subscriptions_select_own on public.subscriptions for select to authenticated
  using (user_id = auth.uid() or public.is_admin());
grant select on public.subscriptions to authenticated;

-- Admin-only reads.
create policy usage_admin on public.usage_events for select to authenticated using (public.is_admin());
create policy audit_admin on public.admin_audit for select to authenticated using (public.is_admin());
create policy settings_admin on public.app_settings for select to authenticated using (public.is_admin());
grant select on public.usage_events, public.admin_audit, public.app_settings to authenticated;
grant select on public.usage_daily to authenticated;

-- oauth_states and job_sources: no policies => no client access at all.
