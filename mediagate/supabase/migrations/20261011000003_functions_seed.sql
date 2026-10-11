-- Profile bootstrap, seed data and the private storage bucket.

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email)
  on conflict (id) do update set email = excluded.email;
  insert into public.subscriptions (user_id) values (new.id) on conflict do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert or update of email on auth.users
  for each row execute function public.handle_new_user();

-- Backfill for users created before this migration.
insert into public.profiles (id, email) select id, email from auth.users on conflict (id) do nothing;
insert into public.subscriptions (user_id) select id from public.profiles on conflict do nothing;

insert into public.platform_config (platform, enabled, notes) values
  ('youtube',   true, 'Metadata only — YouTube ToS prohibit third-party downloads.'),
  ('instagram', true, 'Own media of connected professional accounts only.'),
  ('x',         true, 'Downloads limited to the connected author''s own posts.')
on conflict (platform) do nothing;

insert into public.app_settings (key, value) values
  ('rate_limits', '{"analyze_per_minute": 20, "jobs_per_minute": 5, "max_active_jobs_per_user": 3}')
on conflict (key) do nothing;

-- Private bucket for temporary results (Supabase Storage). No storage policies are created,
-- so only the service role can read/write; users receive short-lived signed URLs from the API.
do $$
begin
  if exists (select 1 from information_schema.tables where table_schema = 'storage' and table_name = 'buckets') then
    insert into storage.buckets (id, name, public, file_size_limit)
    values ('media-temp', 'media-temp', false, 524288000)
    on conflict (id) do nothing;
  end if;
end $$;

-- To make the first admin (run once, in the SQL editor):
--   update public.profiles set role = 'admin' where email = 'you@example.com';
