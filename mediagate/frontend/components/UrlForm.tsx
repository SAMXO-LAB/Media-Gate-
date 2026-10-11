"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useId, useRef } from "react";
import { detectPlatform } from "@/lib/platform";
import { PlatformBadge } from "./PlatformBadge";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
}

export function UrlForm({ value, onChange, onSubmit, busy }: Props) {
  const inputId = useId();
  const hintId = useId();
  const ref = useRef<HTMLInputElement>(null);
  const platform = detectPlatform(value);
  const looksForeign = value.trim().length > 8 && !platform && /\.[a-z]{2,}/i.test(value);

  async function paste() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) onChange(text.trim().slice(0, 2048));
      ref.current?.focus();
    } catch {
      ref.current?.focus();
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!busy && value.trim()) onSubmit();
      }}
      className="w-full"
      noValidate
    >
      <label htmlFor={inputId} className="sr-only">
        Video or post link
      </label>
      <div
        className="group relative flex flex-col gap-2 rounded-[1.6rem] border border-line bg-white p-2 shadow-lift transition
          focus-within:border-brand-300 focus-within:shadow-[0_0_0_5px_rgba(61,109,255,0.14),0_24px_48px_-24px_rgba(23,60,196,0.35)]
          sm:flex-row sm:items-center"
      >
        <div className="flex min-w-0 flex-1 items-center gap-3 pl-3">
          <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0 text-brand-500" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1" strokeLinecap="round" />
            <path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1" strokeLinecap="round" />
          </svg>
          <input
            id={inputId}
            ref={ref}
            type="url"
            inputMode="url"
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            maxLength={2048}
            placeholder="Paste a YouTube, Instagram or X link"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            aria-describedby={hintId}
            className="h-14 min-w-0 flex-1 bg-transparent text-base text-ink placeholder:text-ink-mute focus:outline-none sm:text-[1.05rem]"
          />
          <AnimatePresence mode="popLayout">
            {platform && (
              <motion.span
                key={platform}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                className="hidden shrink-0 sm:block"
              >
                <PlatformBadge platform={platform} />
              </motion.span>
            )}
          </AnimatePresence>
          {!value && (
            <button type="button" onClick={paste} className="btn-ghost hidden shrink-0 px-3 py-1.5 text-xs sm:inline-flex">
              Paste
            </button>
          )}
        </div>
        <button type="submit" disabled={busy || !value.trim()} className="btn-primary h-12 px-7 text-[0.95rem] sm:h-14 sm:rounded-[1.2rem]">
          {busy ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden />
              Analyzing
            </>
          ) : (
            <>
              Analyze
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M4 10h12m0 0-4-4m4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </>
          )}
        </button>
      </div>
      <p id={hintId} className="mt-3 min-h-[1.25rem] px-2 text-sm text-ink-mute" aria-live="polite">
        {looksForeign ? (
          <span className="text-amber-700">Only YouTube, Instagram and X links are supported.</span>
        ) : platform ? (
          <span className="sm:hidden">
            Detected <PlatformBadge platform={platform} size="sm" />
          </span>
        ) : (
          "Links are checked on our server before anything is fetched."
        )}
      </p>
    </form>
  );
}
