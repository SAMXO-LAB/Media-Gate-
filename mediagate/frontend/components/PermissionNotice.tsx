"use client";

import Link from "next/link";
import type { DownloadEligibility } from "@/lib/types";

const titles: Record<DownloadEligibility["reason"], string> = {
  allowed: "Download available",
  platform_prohibits: "Downloads aren't permitted",
  not_connected: "Connect your account",
  not_owner: "Only the owner can download this",
  copyright_withheld: "Withheld for copyright",
  sign_in_required: "Sign in to continue",
  platform_not_configured: "Not available on this server yet",
  no_media: "Nothing to download",
};

export function PermissionNotice({ eligibility }: { eligibility: DownloadEligibility }) {
  const ok = eligibility.allowed;
  const action =
    eligibility.action === "sign_in" ? (
      <Link href="/login" className="btn-primary py-2">Sign in</Link>
    ) : eligibility.action === "connect" ? (
      <Link href="/connections" className="btn-primary py-2">Connect account</Link>
    ) : eligibility.action === "open_external" && eligibility.action_url ? (
      <a href={eligibility.action_url} target="_blank" rel="noopener noreferrer" className="btn-secondary py-2">
        Open YouTube Studio
      </a>
    ) : null;

  return (
    <div
      role="status"
      className={`flex flex-col gap-4 rounded-2xl border p-4 sm:flex-row sm:items-center sm:p-5 ${
        ok ? "border-emerald-200 bg-emerald-50/60" : "border-brand-100 bg-brand-50/60"
      }`}
    >
      <span
        className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${ok ? "bg-emerald-100 text-emerald-700" : "bg-white text-brand-600 ring-1 ring-brand-100"}`}
        aria-hidden
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {ok ? <path d="m5 12 4.5 4.5L19 7" /> : <path d="M12 8v5m0 3h.01M10.3 3.9 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />}
        </svg>
      </span>
      <div className="flex-1">
        <p className="text-sm font-semibold text-ink">{titles[eligibility.reason]}</p>
        <p className="mt-0.5 text-sm leading-relaxed text-ink-soft">{eligibility.message}</p>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
