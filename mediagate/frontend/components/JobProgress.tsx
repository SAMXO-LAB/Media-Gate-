"use client";

import { motion } from "framer-motion";
import type { Job, JobStatus } from "@/lib/types";

const STEPS: { key: JobStatus; label: string }[] = [
  { key: "queued", label: "Queued" },
  { key: "downloading", label: "Fetching" },
  { key: "processing", label: "Processing" },
  { key: "uploading", label: "Finalizing" },
  { key: "completed", label: "Ready" },
];

interface Props {
  job: Job;
  onDownload: () => void;
  onCancel: () => void;
  onReset: () => void;
  linkBusy: boolean;
}

export function JobProgress({ job, onDownload, onCancel, onReset, linkBusy }: Props) {
  const idx = STEPS.findIndex((s) => s.key === job.status);
  const active = idx >= 0 && job.status !== "completed";
  const failed = job.status === "failed" || job.status === "cancelled" || job.status === "expired";
  const pct = job.progress != null ? Math.round(job.progress * 100) : null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="card p-5 sm:p-6"
      aria-labelledby="job-title"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Processing job</p>
          <h3 id="job-title" className="mt-1 font-display text-lg font-bold text-ink">
            {job.status === "completed"
              ? "Your file is ready"
              : failed
                ? job.status === "cancelled"
                  ? "Job cancelled"
                  : job.status === "expired"
                    ? "This file has expired"
                    : "Processing failed"
                : "Preparing your file"}
          </h3>
        </div>
        {active && (
          <button onClick={onCancel} className="btn-ghost px-3 py-1.5 text-xs">
            Cancel
          </button>
        )}
      </div>

      {!failed && (
        <>
          <ol className="mt-5 grid grid-cols-5 gap-2" aria-label="Progress steps">
            {STEPS.map((s, i) => {
              const done = i < idx || job.status === "completed";
              const current = i === idx && job.status !== "completed";
              return (
                <li key={s.key} className="min-w-0" aria-current={current ? "step" : undefined}>
                  <div className="relative h-1.5 overflow-hidden rounded-full bg-brand-50">
                    {done && <div className="absolute inset-0 bg-brand-500" />}
                    {current &&
                      (pct != null && (s.key === "downloading" || s.key === "processing") ? (
                        <motion.div className="absolute inset-y-0 left-0 bg-brand-500" animate={{ width: `${pct}%` }} />
                      ) : (
                        <div className="absolute inset-y-0 w-2/5 animate-indeterminate rounded-full bg-brand-500" />
                      ))}
                  </div>
                  <span className={`mt-2 block truncate text-[11px] font-medium sm:text-xs ${done || current ? "text-ink" : "text-ink-mute"}`}>
                    {s.label}
                  </span>
                </li>
              );
            })}
          </ol>
          <p className="mt-3 text-xs text-ink-mute" aria-live="polite">
            {job.status === "completed"
              ? "The file stays available for one hour, then it's deleted automatically."
              : pct != null
                ? `${pct}% complete`
                : "Progress isn't measurable for this step — hang tight."}
          </p>
        </>
      )}

      {failed && (
        <p className="mt-3 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert">
          {job.error_message ?? "Something went wrong."}
        </p>
      )}

      <div className="mt-5 flex flex-wrap gap-2">
        {job.status === "completed" && job.download_id && (
          <button onClick={onDownload} disabled={linkBusy} className="btn-primary">
            {linkBusy ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden />
            ) : (
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M10 3v10m0 0-4-4m4 4 4-4M4 16h12" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
            Download file
          </button>
        )}
        {(failed || job.status === "completed") && (
          <button onClick={onReset} className="btn-secondary">
            Analyze another link
          </button>
        )}
      </div>
    </motion.section>
  );
}
