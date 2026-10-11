"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { DailyChart } from "@/components/admin/DailyChart";
import { PlatformBadge } from "@/components/PlatformBadge";
import { useToast } from "@/components/Toasts";
import { ApiError, api } from "@/lib/api";
import type { AdminOverview, AdminUser, Platform, PlatformStatus, RateLimitConfig } from "@/lib/types";

type Tab = "overview" | "users" | "settings";

function Stat({ label, value, tone = "default", hint }: { label: string; value: string | number; tone?: "default" | "good" | "bad"; hint?: string }) {
  const color = tone === "good" ? "text-emerald-700" : tone === "bad" ? "text-rose-700" : "text-ink";
  return (
    <div className="card p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-mute">{label}</p>
      <p className={`mt-2 font-display text-3xl font-bold tabular-nums ${color}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-mute">{hint}</p>}
    </div>
  );
}

export default function AdminPage() {
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("overview");
  const [hours, setHours] = useState(24);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [daily, setDaily] = useState<{ day: string; event: string; n: number }[]>([]);
  const [denied, setDenied] = useState<null | "auth" | "forbidden">(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [o, d] = await Promise.all([
        api<AdminOverview>(`/api/admin/overview?hours=${hours}`),
        api<{ day: string; event: string; n: number }[]>("/api/admin/usage/daily?days=14"),
      ]);
      setOverview(o);
      setDaily(d);
      setError(null);
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 401) setDenied("auth");
      else if (err.status === 403) setDenied("forbidden");
      else setError(err.message);
    }
  }, [hours]);

  useEffect(() => {
    load();
    const t = window.setInterval(load, 15000);
    return () => window.clearInterval(t);
  }, [load]);

  if (denied) {
    return (
      <section className="container-page py-24 text-center">
        <h1 className="font-display text-2xl font-bold text-ink">
          {denied === "auth" ? "Sign in required" : "Administrators only"}
        </h1>
        <p className="mt-2 text-ink-soft">
          {denied === "auth" ? "Please sign in with an administrator account." : "Your account doesn't have access to this page."}
        </p>
        <Link href={denied === "auth" ? "/login" : "/"} className="btn-primary mt-6">
          {denied === "auth" ? "Sign in" : "Back to MediaGate"}
        </Link>
      </section>
    );
  }

  const successRate =
    overview && overview.jobs_completed + overview.jobs_failed > 0
      ? Math.round((overview.jobs_completed / (overview.jobs_completed + overview.jobs_failed)) * 100)
      : null;
  const queueHealthy = overview ? (overview.oldest_queued_seconds ?? 0) < 120 : true;

  return (
    <section className="container-page py-12">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">Administration</p>
          <h1 className="mt-1 font-display text-3xl font-bold tracking-tight text-ink">Dashboard</h1>
        </div>
        <div role="tablist" aria-label="Admin sections" className="inline-flex rounded-full border border-line bg-canvas p-1">
          {(["overview", "users", "settings"] as Tab[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium capitalize transition ${tab === t ? "bg-white text-ink shadow-sm" : "text-ink-mute hover:text-ink"}`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p className="mt-6 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert">
          {error}
        </p>
      )}

      {tab === "overview" && (
        <div className="mt-8 space-y-6">
          <div className="flex items-center gap-2 text-sm text-ink-soft">
            <label htmlFor="window">Window</label>
            <select id="window" value={hours} onChange={(e) => setHours(Number(e.target.value))} className="input h-9 w-auto py-1">
              <option value={1}>Last hour</option>
              <option value={24}>Last 24 hours</option>
              <option value={168}>Last 7 days</option>
              <option value={720}>Last 30 days</option>
            </select>
          </div>
          {!overview ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[0, 1, 2, 3].map((i) => <div key={i} className="card h-28 animate-pulse bg-canvas" />)}
            </div>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Stat label="Requests" value={overview.requests_total} hint={`${overview.analyze_total} analyses`} />
                <Stat label="Completed jobs" value={overview.jobs_completed} tone="good" hint={successRate !== null ? `${successRate}% success rate` : undefined} />
                <Stat label="Failed jobs" value={overview.jobs_failed} tone={overview.jobs_failed ? "bad" : "default"} />
                <Stat
                  label="Queue"
                  value={overview.queue_depth}
                  tone={queueHealthy ? "default" : "bad"}
                  hint={`${overview.jobs_active} processing · oldest ${overview.oldest_queued_seconds ? Math.round(overview.oldest_queued_seconds) + "s" : "—"}`}
                />
              </div>

              <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
                <div className="card p-5">
                  <h2 className="text-sm font-semibold text-ink">Daily activity · 14 days</h2>
                  <div className="mt-4">
                    <DailyChart rows={daily} />
                  </div>
                </div>
                <div className="card p-5">
                  <h2 className="text-sm font-semibold text-ink">By platform</h2>
                  <table className="mt-4 w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-ink-mute">
                        <th className="pb-2 font-medium">Platform</th>
                        <th className="pb-2 text-right font-medium">Analyze</th>
                        <th className="pb-2 text-right font-medium">Done</th>
                        <th className="pb-2 text-right font-medium">Failed</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {(["youtube", "instagram", "x"] as Platform[]).map((p) => {
                        const r = overview.by_platform[p] ?? {};
                        return (
                          <tr key={p}>
                            <td className="py-2.5"><PlatformBadge platform={p} size="sm" /></td>
                            <td className="py-2.5 text-right font-mono tabular-nums">{r.analyze ?? 0}</td>
                            <td className="py-2.5 text-right font-mono tabular-nums">{r.job_completed ?? 0}</td>
                            <td className="py-2.5 text-right font-mono tabular-nums">{r.job_failed ?? 0}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="card overflow-hidden">
                <h2 className="border-b border-line px-5 py-4 text-sm font-semibold text-ink">Recent processing errors</h2>
                {overview.recent_errors.length === 0 ? (
                  <p className="px-5 py-8 text-center text-sm text-ink-mute">No errors in this window.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[600px] text-sm">
                      <thead className="bg-canvas text-left text-xs text-ink-mute">
                        <tr>
                          <th className="px-5 py-2 font-medium">When</th>
                          <th className="px-5 py-2 font-medium">Platform</th>
                          <th className="px-5 py-2 font-medium">Code</th>
                          <th className="px-5 py-2 font-medium">Message</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line">
                        {overview.recent_errors.map((e) => (
                          <tr key={e.id}>
                            <td className="whitespace-nowrap px-5 py-2.5 text-ink-mute">{new Date(e.finished_at).toLocaleString()}</td>
                            <td className="px-5 py-2.5"><PlatformBadge platform={e.platform as Platform} size="sm" /></td>
                            <td className="px-5 py-2.5 font-mono text-xs">{e.error_code}</td>
                            <td className="px-5 py-2.5 text-ink-soft">{e.error_message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {tab === "users" && <UsersPanel onError={(m) => toast({ tone: "error", title: "Update failed", body: m })} />}
      {tab === "settings" && <SettingsPanel />}
    </section>
  );
}

function UsersPanel({ onError }: { onError: (m: string) => void }) {
  const [q, setQ] = useState("");
  const [users, setUsers] = useState<AdminUser[] | null>(null);

  const load = useCallback(async (search: string) => {
    try {
      setUsers(await api<AdminUser[]>(`/api/admin/users${search ? `?q=${encodeURIComponent(search)}` : ""}`));
    } catch (e) {
      onError((e as ApiError).message);
    }
  }, [onError]);

  useEffect(() => {
    const t = window.setTimeout(() => load(q), 250);
    return () => window.clearTimeout(t);
  }, [q, load]);

  async function patch(u: AdminUser, body: Partial<Pick<AdminUser, "role" | "is_blocked">>) {
    try {
      const updated = await api<AdminUser>(`/api/admin/users/${u.id}`, { method: "PATCH", json: body });
      setUsers((list) => list?.map((x) => (x.id === u.id ? { ...updated, jobs_7d: u.jobs_7d } : x)) ?? null);
    } catch (e) {
      onError((e as ApiError).message);
    }
  }

  return (
    <div className="mt-8">
      <label htmlFor="user-search" className="sr-only">Search users by email</label>
      <input id="user-search" className="input h-10 max-w-sm" placeholder="Search by email" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="card mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-canvas text-left text-xs text-ink-mute">
            <tr>
              <th className="px-5 py-2.5 font-medium">Email</th>
              <th className="px-5 py-2.5 font-medium">Joined</th>
              <th className="px-5 py-2.5 text-right font-medium">Jobs (7d)</th>
              <th className="px-5 py-2.5 font-medium">Role</th>
              <th className="px-5 py-2.5 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {users === null ? (
              <tr><td colSpan={5} className="px-5 py-8 text-center text-ink-mute">Loading…</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={5} className="px-5 py-8 text-center text-ink-mute">No users found.</td></tr>
            ) : (
              users.map((u) => (
                <tr key={u.id}>
                  <td className="px-5 py-3 font-medium text-ink">{u.email ?? "—"}</td>
                  <td className="px-5 py-3 text-ink-mute">{new Date(u.created_at).toLocaleDateString()}</td>
                  <td className="px-5 py-3 text-right font-mono tabular-nums">{u.jobs_7d}</td>
                  <td className="px-5 py-3">
                    <select aria-label={`Role for ${u.email}`} value={u.role} onChange={(e) => patch(u, { role: e.target.value as AdminUser["role"] })} className="input h-8 w-auto py-0 text-xs">
                      <option value="user">User</option>
                      <option value="admin">Admin</option>
                    </select>
                  </td>
                  <td className="px-5 py-3">
                    <button
                      onClick={() => patch(u, { is_blocked: !u.is_blocked })}
                      className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${u.is_blocked ? "bg-rose-50 text-rose-700 ring-rose-200" : "bg-emerald-50 text-emerald-700 ring-emerald-200"}`}
                    >
                      {u.is_blocked ? "Blocked · unblock" : "Active · block"}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SettingsPanel() {
  const toast = useToast();
  const [limits, setLimits] = useState<RateLimitConfig | null>(null);
  const [platforms, setPlatforms] = useState<PlatformStatus[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<RateLimitConfig>("/api/admin/rate-limits").then(setLimits).catch(() => null);
    api<PlatformStatus[]>("/api/platforms").then(setPlatforms).catch(() => null);
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!limits) return;
    setSaving(true);
    try {
      setLimits(await api<RateLimitConfig>("/api/admin/rate-limits", { method: "PUT", json: limits }));
      toast({ tone: "success", title: "Rate limits saved", body: "Applied to all API instances within 30 seconds." });
    } catch (err) {
      toast({ tone: "error", title: "Couldn't save", body: (err as ApiError).message });
    } finally {
      setSaving(false);
    }
  }

  async function toggle(p: PlatformStatus) {
    try {
      await api(`/api/admin/platforms/${p.platform}`, { method: "PUT", json: { enabled: !p.enabled } });
      setPlatforms((list) => list.map((x) => (x.platform === p.platform ? { ...x, enabled: !x.enabled } : x)));
    } catch (err) {
      toast({ tone: "error", title: "Couldn't update platform", body: (err as ApiError).message });
    }
  }

  const fields: { key: keyof RateLimitConfig; label: string; hint: string; max: number }[] = [
    { key: "analyze_per_minute", label: "Analyze requests / minute", hint: "Per user, or per IP when signed out.", max: 1000 },
    { key: "jobs_per_minute", label: "New jobs / minute", hint: "Per user.", max: 200 },
    { key: "max_active_jobs_per_user", label: "Concurrent jobs per user", hint: "Jobs queued or processing at once.", max: 50 },
  ];

  return (
    <div className="mt-8 grid gap-6 lg:grid-cols-2">
      <form onSubmit={save} className="card space-y-5 p-6">
        <h2 className="text-sm font-semibold text-ink">Rate limits</h2>
        {!limits ? (
          <div className="h-40 animate-pulse rounded-xl bg-canvas" />
        ) : (
          fields.map((f) => (
            <div key={f.key}>
              <label htmlFor={f.key} className="block text-sm font-medium text-ink">{f.label}</label>
              <input
                id={f.key}
                type="number"
                min={1}
                max={f.max}
                required
                value={limits[f.key]}
                onChange={(e) => setLimits({ ...limits, [f.key]: Number(e.target.value) })}
                className="input mt-1.5 h-10 max-w-[10rem]"
              />
              <p className="mt-1 text-xs text-ink-mute">{f.hint}</p>
            </div>
          ))
        )}
        <button className="btn-primary" disabled={!limits || saving}>{saving ? "Saving…" : "Save limits"}</button>
      </form>

      <div className="card p-6">
        <h2 className="text-sm font-semibold text-ink">Platforms</h2>
        <ul className="mt-4 divide-y divide-line">
          {platforms.map((p) => (
            <li key={p.platform} className="flex items-center gap-4 py-4">
              <div className="flex-1">
                <PlatformBadge platform={p.platform} />
                <p className="mt-1.5 text-xs text-ink-mute">
                  {p.configured ? p.summary : `Missing configuration: ${p.missing.join(", ")}`}
                </p>
              </div>
              <button
                role="switch"
                aria-checked={p.enabled}
                aria-label={`${p.platform} enabled`}
                onClick={() => toggle(p)}
                className={`relative h-6 w-11 shrink-0 rounded-full transition ${p.enabled ? "bg-brand-600" : "bg-line"}`}
              >
                <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${p.enabled ? "left-[22px]" : "left-0.5"}`} />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
