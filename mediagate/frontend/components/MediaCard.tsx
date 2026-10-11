"use client";

import { motion } from "framer-motion";
import { useState } from "react";
import { PLATFORM_META, formatDuration } from "@/lib/platform";
import type { MediaInfo } from "@/lib/types";
import { PlatformBadge } from "./PlatformBadge";

export function MediaCard({ media }: { media: MediaInfo }) {
  const [imgFailed, setImgFailed] = useState(false);
  const duration = formatDuration(media.duration_seconds);
  const published = media.published_at
    ? new Date(media.published_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
    : null;
  const hasDetails = Boolean(media.title || media.author);

  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}
      className="card overflow-hidden"
    >
      <div className="relative aspect-video w-full overflow-hidden bg-brand-50">
        {media.thumbnail_url && !imgFailed ? (
          // eslint-disable-next-line @next/next/no-img-element -- remote CDN thumbnails, already CSP-restricted
          <img
            src={media.thumbnail_url}
            alt={media.title ? `Thumbnail for ${media.title}` : "Media thumbnail"}
            className="h-full w-full object-cover"
            referrerPolicy="no-referrer"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-brand-300">
            <svg viewBox="0 0 48 48" className="h-12 w-12" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <rect x="6" y="10" width="36" height="28" rx="5" />
              <path d="M21 19v10l8-5-8-5Z" fill="currentColor" stroke="none" />
            </svg>
            <span className="text-xs font-medium text-brand-400">No preview available</span>
          </div>
        )}
        {duration && (
          <span className="absolute bottom-3 right-3 rounded-md bg-ink/80 px-2 py-0.5 font-mono text-xs font-medium text-white">
            {duration}
          </span>
        )}
      </div>
      <div className="space-y-3 p-5 sm:p-6">
        <div className="flex flex-wrap items-center gap-2">
          <PlatformBadge platform={media.platform} />
          {media.media_type && (
            <span className="rounded-full bg-canvas px-2.5 py-1 text-xs font-medium capitalize text-ink-soft ring-1 ring-line">
              {media.media_type.replace("_", " ")}
            </span>
          )}
        </div>
        {hasDetails ? (
          <>
            <h2 className="font-display text-lg font-bold leading-snug text-ink sm:text-xl">
              {media.title ?? `${PLATFORM_META[media.platform].name} media`}
            </h2>
            <p className="text-sm text-ink-mute">
              {[media.author, published].filter(Boolean).join(" · ")}
            </p>
          </>
        ) : (
          <p className="text-sm leading-relaxed text-ink-soft">
            {PLATFORM_META[media.platform].name} doesn&apos;t share details for this post with us yet. See below for why.
          </p>
        )}
        <a
          href={media.canonical_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:text-brand-800"
        >
          Open on {PLATFORM_META[media.platform].name}
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
            <path d="M6 3h7v7M13 3 4 12" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </a>
      </div>
    </motion.article>
  );
}

export function MediaCardSkeleton() {
  return (
    <div className="card overflow-hidden" aria-hidden>
      <div className="relative aspect-video overflow-hidden bg-brand-50">
        <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/70 to-transparent" />
      </div>
      <div className="space-y-3 p-6">
        <div className="h-5 w-24 rounded-full bg-brand-50" />
        <div className="h-6 w-4/5 rounded-lg bg-brand-50" />
        <div className="h-4 w-1/3 rounded-lg bg-brand-50" />
      </div>
    </div>
  );
}
