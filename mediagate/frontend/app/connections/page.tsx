"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PlatformBadge } from "@/components/PlatformBadge";
import { useToast } from "@/components/Toasts";
import { ApiError, api } from "@/lib/api";
import { PLATFORM_META } from "@/lib/platform";
import type { ConnectionInfo } from "@/lib/types";
import { useSession } from "@/lib/useSession";

const WHY: Record<string, string> = {
  instagram:
    "Requires an Instagram Business or Creator account. We can then download media you published — Meta doesn't share files from other accounts.",
  x: "Lets us confirm which posts you authored, so you can download your own videos and images.",
  youtube: "YouTube has no authorized download API, so there's nothing to connect.",
};

export default function ConnectionsPage() {
  const toast = useToast();
  const { session, loading } = useSession();
  const [items, setItems] = useState<ConnectionInfo[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api<ConnectionInfo[]>("/api/connections"));
      setLoadError(null);
    } catch (e) {
      setLoadError((e as ApiError).message);
    }
  }, []);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  // Result of the OAuth round-trip (?platform=x&status=connected).
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const status = q.get("status");
    const platform = q.get("platform") as keyof typeof PLATFORM_META | null;
    if (!status || !platform || !(platform in PLATFORM_META)) return;
    const name = PLATFORM_META[platform].name;
    if (status === "connected") toast({ tone: "success", title: `${name} connected` });
    else if (status === "denied") toast({ tone: "info", title: `${name} connection cancelled` });
    else toast({ tone: "error", title: `Couldn't connect ${name}`, body: "Please try again." });
    window.history.replaceState(null, "", "/connections");
  }, [toast]);

  async function connect(platform: string) {
    setBusy(platform);
    try {
      const { authorize_url } = await api<{ authorize_url: string }>(`/api/connections/${platform}/start`, { method: "POST" });
      window.location.assign(authorize_url);
    } catch (e) {
      toast({ tone: "error", title: "Couldn't start connection", body: (e as ApiError).message });
      setBusy(null);
    }
  }

  async function disconnect(platform: string) {
    setBusy(platform);
    try {
      await api(`/api/connections/${platform}`, { method: "DELETE" });
      toast({ tone: "info", title: "Disconnected" });
      await load();
    } catch (e) {
      toast({ tone: "error", title: "Couldn't disconnect", body: (e as ApiError).message });
    } finally {
      setBusy(null);
    }
  }

  if (!loading && !session) {
    return (
      <section className="container-page py-24 text-center">
        <h1 className="font-display text-2xl font-bold text-ink">Sign in to manage connections</h1>
        <Link href="/login" className="btn-primary mt-6">Sign in</Link>
      </section>
    );
  }

  return (
    <section className="container-page max-w-3xl py-14">
      <p className="eyebrow">Accounts</p>
      <h1 className="mt-2 font-display text-3xl font-bold tracking-tight text-ink">Connections</h1>
      <p className="mt-2 max-w-xl text-ink-soft">
        Connecting an account proves which media is yours. Tokens are encrypted on our server and never sent to your
        browser. You can disconnect at any time.
      </p>

      {loadError && (
        <p className="mt-8 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert">
          {loadError} <button onClick={load} className="font-semibold underline">Retry</button>
        </p>
      )}

      <ul className="mt-8 space-y-3">
        {(items ?? [null, null, null]).map((c, i) =>
          c === null ? (
            <li key={i} className="card h-[104px] animate-pulse bg-canvas" aria-hidden />
          ) : (
            <li key={c.platform} className="card flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <PlatformBadge platform={c.platform} />
                  {c.connected && (
                    <span className="text-sm font-medium text-ink">@{c.account_name ?? "connected"}</span>
                  )}
                </div>
                <p className="mt-2 text-sm leading-relaxed text-ink-mute">{WHY[c.platform]}</p>
                {c.connectable && !c.configured && (
                  <p className="mt-2 text-xs font-medium text-amber-800">Not configured on this server yet.</p>
                )}
              </div>
              {c.connectable && (
                <div className="shrink-0">
                  {c.connected ? (
                    <button onClick={() => disconnect(c.platform)} disabled={busy === c.platform} className="btn-secondary">
                      Disconnect
                    </button>
                  ) : (
                    <button onClick={() => connect(c.platform)} disabled={!c.configured || busy === c.platform} className="btn-primary">
                      {busy === c.platform ? "Redirecting…" : `Connect ${PLATFORM_META[c.platform].name}`}
                    </button>
                  )}
                </div>
              )}
            </li>
          ),
        )}
      </ul>
    </section>
  );
}
