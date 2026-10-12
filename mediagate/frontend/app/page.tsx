"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { CapabilityGrid } from "@/components/CapabilityGrid";
import { FormatPicker } from "@/components/FormatPicker";
import { JobProgress } from "@/components/JobProgress";
import { MediaCard, MediaCardSkeleton } from "@/components/MediaCard";
import { PermissionNotice } from "@/components/PermissionNotice";
import { useToast } from "@/components/Toasts";
import { UrlForm } from "@/components/UrlForm";
import { ApiError, api } from "@/lib/api";
import type { AnalyzeResponse, DownloadLink, Job } from "@/lib/types";
import { useSession } from "@/lib/useSession";

type View =
  | { kind: "idle" }
  | { kind: "analyzing" }
  | { kind: "result"; data: AnalyzeResponse }
  | { kind: "error"; error: ApiError };

const ACTIVE = new Set(["queued", "downloading", "processing", "uploading"]);

const ERROR_COPY: Record<string, { title: string; hint?: string }> = {
  unsupported_platform: { title: "That site isn't supported", hint: "Paste a link from YouTube, Instagram or X." },
  invalid_url: { title: "That link doesn't look right", hint: "Copy the link to a single video or post and try again." },
  media_unavailable: { title: "We couldn't find that media", hint: "It may be private, deleted, or region-restricted." },
  rate_limited: { title: "Slow down a little", hint: "You've made a lot of requests. Try again in a moment." },
  platform_rate_limited: { title: "The platform is busy", hint: "Its API is rate-limiting requests right now." },
  platform_quota: { title: "Daily API quota reached", hint: "This server's quota resets soon. Please try later." },
  platform_not_configured: { title: "Not available on this server yet", hint: "The administrator hasn't added credentials for this platform." },
  platform_disabled: { title: "Temporarily paused", hint: "This platform has been paused by the administrator." },
  connection_expired: { title: "Your connection expired", hint: "Reconnect your account on the Connections page." },
  network_error: { title: "Can't reach the server", hint: "Check your connection and try again." },
  server_unavailable: { title: "The server had a problem", hint: "It didn't finish this request. Please try again in a moment." },
  database_unavailable: { title: "Temporarily unavailable", hint: "Our database can't be reached right now. Please try again shortly." },
  internal_error: { title: "Something went wrong", hint: "An unexpected error occurred. Please try again." },
};

export default function HomePage() {
  const toast = useToast();
  const { session } = useSession();
  const [url, setUrl] = useState("");
  const [view, setView] = useState<View>({ kind: "idle" });
  const [format, setFormat] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [linkBusy, setLinkBusy] = useState(false);
  const analyzedUrl = useRef("");
  const resultsRef = useRef<HTMLDivElement>(null);

  const analyze = useCallback(async () => {
    setView({ kind: "analyzing" });
    setJob(null);
    setFormat(null);
    analyzedUrl.current = url.trim();
    try {
      const data = await api<AnalyzeResponse>("/api/analyze", { method: "POST", json: { url: url.trim() } });
      setView({ kind: "result", data });
      const first = data.download.allowed ? data.formats.find((f) => f.available) : undefined;
      setFormat(first?.id ?? null);
    } catch (e) {
      setView({ kind: "error", error: e instanceof ApiError ? e : new ApiError(0, "unknown", "Something went wrong.") });
    }
    requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [url]);

  // Poll job status while it is active.
  useEffect(() => {
    if (!job || !ACTIVE.has(job.status)) return;
    let stopped = false;
    const t = window.setTimeout(async () => {
      try {
        const next = await api<Job>(`/api/jobs/${job.id}`);
        if (stopped) return;
        setJob(next);
        if (next.status === "completed") toast({ tone: "success", title: "Your file is ready", body: "Download it within the next hour." });
        if (next.status === "failed") toast({ tone: "error", title: "Processing failed", body: next.error_message ?? undefined });
      } catch {
        // Transient error (network, 429): re-arm the poll with a fresh object.
        if (!stopped) setJob({ ...job });
      }
    }, 1500);
    return () => {
      stopped = true;
      window.clearTimeout(t);
    };
  }, [job, toast]);

  async function startJob() {
    if (!format) return;
    setSubmitting(true);
    try {
      const created = await api<Job>("/api/jobs", { method: "POST", json: { url: analyzedUrl.current, format_id: format } });
      setJob(created);
      toast({ tone: "info", title: "Processing started", body: "We'll let you know when it's ready." });
    } catch (e) {
      const err = e as ApiError;
      toast({ tone: "error", title: ERROR_COPY[err.code]?.title ?? "Couldn't start processing", body: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  async function download() {
    if (!job?.download_id) return;
    setLinkBusy(true);
    try {
      const link = await api<DownloadLink>(`/api/downloads/${job.download_id}`);
      // Short-lived signed URL; navigating triggers the browser's download (Content-Disposition: attachment).
      window.location.assign(link.url);
    } catch (e) {
      const err = e as ApiError;
      if (err.code === "expired") setJob({ ...job, status: "expired", error_message: err.message });
      toast({ tone: "error", title: "Download unavailable", body: err.message });
    } finally {
      setLinkBusy(false);
    }
  }

  async function cancel() {
    if (!job) return;
    try {
      await api(`/api/jobs/${job.id}`, { method: "DELETE" });
      setJob({ ...job, status: "cancelled", error_message: "You cancelled this job." });
    } catch (e) {
      toast({ tone: "error", title: "Couldn't cancel", body: (e as ApiError).message });
    }
  }

  function reset() {
    setJob(null);
    setView({ kind: "idle" });
    setUrl("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const result = view.kind === "result" ? view.data : null;
  const jobLocked = Boolean(job && (ACTIVE.has(job.status) || job.status === "completed"));

  return (
    <>
      <section className="relative overflow-hidden">
        <div className="hero-grid pointer-events-none absolute inset-0" aria-hidden />
        <div className="container-page relative pb-14 pt-16 sm:pb-20 sm:pt-24">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.2, 0.8, 0.2, 1] }}
            className="mx-auto max-w-3xl text-center"
          >
            <p className="inline-flex items-center gap-2 rounded-full border border-brand-100 bg-white px-3 py-1 text-xs font-semibold text-brand-700 shadow-sm">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-500" aria-hidden />
              Official APIs only · Files auto-delete after 1 hour
            </p>
            <h1 className="mt-6 font-display text-[2.4rem] font-extrabold leading-[1.05] tracking-tight text-ink sm:text-6xl">
              Every link, <span className="text-brand-600">handled honestly.</span>
            </h1>
            <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-ink-soft sm:text-lg">
              Paste a YouTube, Instagram or X link. See the real details and formats, and download whatever the
              platform actually authorizes — nothing more.
            </p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.08, ease: [0.2, 0.8, 0.2, 1] }}
            className="mx-auto mt-10 max-w-3xl"
          >
            <UrlForm value={url} onChange={setUrl} onSubmit={analyze} busy={view.kind === "analyzing"} />
          </motion.div>
        </div>
      </section>

      <div ref={resultsRef} className="container-page scroll-mt-20">
        <AnimatePresence mode="wait">
          {view.kind === "analyzing" && (
            <motion.div key="loading" exit={{ opacity: 0 }} className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[1.1fr_1fr]" aria-busy="true" aria-label="Analyzing link">
              <MediaCardSkeleton />
              <div className="card space-y-3 p-6" aria-hidden>
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-16 rounded-2xl bg-brand-50" />
                ))}
              </div>
            </motion.div>
          )}

          {view.kind === "error" && (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              role="alert"
              className="card mx-auto flex max-w-2xl flex-col items-center px-6 py-10 text-center"
            >
              <span className="grid h-12 w-12 place-items-center rounded-full bg-rose-50 text-rose-600" aria-hidden>
                <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M12 8v5m0 3h.01" />
                  <circle cx="12" cy="12" r="9" />
                </svg>
              </span>
              <h2 className="mt-4 font-display text-xl font-bold text-ink">
                {ERROR_COPY[view.error.code]?.title ?? "Something went wrong"}
              </h2>
              <p className="mt-2 max-w-md text-sm leading-relaxed text-ink-soft">
                {ERROR_COPY[view.error.code]?.hint ?? view.error.message}
              </p>
              {view.error.retryAfter && (
                <p className="mt-2 text-xs text-ink-mute">Try again in about {view.error.retryAfter}s.</p>
              )}
              <button onClick={analyze} className="btn-secondary mt-6">
                Try again
              </button>
            </motion.div>
          )}

          {result && (
            <motion.div
              key={result.media.canonical_url}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="mx-auto grid max-w-5xl items-start gap-6 lg:grid-cols-[1.1fr_1fr]"
            >
              <MediaCard media={result.media} />
              <div className="space-y-5">
                <PermissionNotice eligibility={result.download} />
                {result.formats.length > 0 ? (
                  <div className="card p-5 sm:p-6">
                    <FormatPicker formats={result.formats} selected={format} onSelect={setFormat} disabled={!result.download.allowed || jobLocked} />
                    {result.download.allowed && !job && (
                      <button onClick={startJob} disabled={!format || submitting || !session} className="btn-primary mt-5 w-full py-3">
                        {submitting ? "Starting…" : "Prepare download"}
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-line px-5 py-6 text-sm text-ink-mute">
                    No downloadable formats are offered for this media.
                  </div>
                )}
                {job && <JobProgress job={job} onDownload={download} onCancel={cancel} onReset={reset} linkBusy={linkBusy} />}
                {result.notices.length > 0 && (
                  <ul className="space-y-1.5 px-1 text-xs leading-relaxed text-ink-mute">
                    {result.notices.map((n) => (
                      <li key={n} className="flex gap-2">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-mute" aria-hidden />
                        {n}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </motion.div>
          )}

          {view.kind === "idle" && (
            <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mx-auto grid max-w-4xl gap-3 sm:grid-cols-3">
              {[
                ["1", "Paste a link", "A single video, reel or post from YouTube, Instagram or X."],
                ["2", "See what's real", "Actual formats from the platform — never invented quality options."],
                ["3", "Download if allowed", "Your own Instagram and X media, via a link that expires in minutes."],
              ].map(([n, t, d]) => (
                <div key={n} className="rounded-2xl border border-line bg-white p-5">
                  <span className="grid h-7 w-7 place-items-center rounded-full bg-brand-50 font-mono text-xs font-semibold text-brand-700">{n}</span>
                  <p className="mt-3 text-sm font-semibold text-ink">{t}</p>
                  <p className="mt-1 text-sm leading-relaxed text-ink-mute">{d}</p>
                </div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <CapabilityGrid />
    </>
  );
}
