"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Platform, PlatformStatus } from "@/lib/types";
import { PlatformBadge } from "./PlatformBadge";

// Static fallback mirrors docs/ARCHITECTURE.md, used until /api/platforms responds.
const FALLBACK: Record<Platform, { rows: [string, boolean | "own"][]; note: string }> = {
  youtube: {
    rows: [["Title, thumbnail, duration", true], ["Real format list", false], ["File download", false]],
    note: "YouTube's terms allow downloads only through YouTube's own features.",
  },
  instagram: {
    rows: [["Details & preview", "own"], ["Original file", "own"], ["Audio extract", "own"]],
    note: "Meta's API only shares media with the professional account that owns it.",
  },
  x: {
    rows: [["Details & preview", true], ["Real bitrate variants", true], ["File download", "own"]],
    note: "Downloads are limited to posts you authored, after connecting your X account.",
  },
};

function Mark({ v }: { v: boolean | "own" }) {
  if (v === "own")
    return <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-semibold text-brand-700">Your posts</span>;
  return v ? (
    <span className="text-emerald-600" aria-label="Supported">
      <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="m4.5 10 3.5 3.5 7.5-7.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </span>
  ) : (
    <span className="text-ink-mute" aria-label="Not supported">
      <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 10h10" strokeLinecap="round" /></svg>
    </span>
  );
}

export function CapabilityGrid() {
  const [status, setStatus] = useState<Record<string, PlatformStatus>>({});
  useEffect(() => {
    api<PlatformStatus[]>("/api/platforms")
      .then((list) => setStatus(Object.fromEntries(list.map((p) => [p.platform, p]))))
      .catch(() => setStatus({}));
  }, []);

  return (
    <section id="platforms" className="container-page scroll-mt-24 py-20" aria-labelledby="platforms-title">
      <div className="max-w-2xl">
        <p className="eyebrow">Straight answers</p>
        <h2 id="platforms-title" className="mt-2 font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          What each platform actually allows
        </h2>
        <p className="mt-3 text-base leading-relaxed text-ink-soft">
          We only use official APIs. When a platform doesn&apos;t authorize a download, we tell you why instead of
          working around it.
        </p>
      </div>
      <div className="mt-10 grid gap-4 md:grid-cols-3">
        {(Object.keys(FALLBACK) as Platform[]).map((p) => {
          const s = status[p];
          const unavailable = s && (!s.enabled || !s.configured);
          return (
            <article key={p} className="card flex flex-col p-6">
              <div className="flex items-center justify-between">
                <PlatformBadge platform={p} />
                {unavailable && (
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200">
                    {s.enabled ? "Not configured" : "Paused"}
                  </span>
                )}
              </div>
              <ul className="mt-5 divide-y divide-line">
                {FALLBACK[p].rows.map(([label, v]) => (
                  <li key={label} className="flex items-center justify-between py-2.5 text-sm text-ink-soft">
                    {label}
                    <Mark v={v} />
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-xs leading-relaxed text-ink-mute">{FALLBACK[p].note}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
