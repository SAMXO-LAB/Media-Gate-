"use client";
import type React from "react";

import { formatBytes } from "@/lib/platform";
import type { MediaFormat } from "@/lib/types";

interface Props {
  formats: MediaFormat[];
  selected: string | null;
  onSelect: (id: string) => void;
  disabled: boolean;
}

const kindIcon: Record<MediaFormat["kind"], React.ReactElement> = {
  video: <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h7A2.5 2.5 0 0 1 16 6.5v7a2.5 2.5 0 0 1-2.5 2.5h-7A2.5 2.5 0 0 1 4 13.5v-7ZM16 8.5l4-2.5v8l-4-2.5" />,
  audio: <path d="M9 17V5l10-2v12M9 17a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm10-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />,
  image: <path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6Zm0 10 4-4 4 4 3-3 5 5M15 9h.01" />,
};

export function FormatPicker({ formats, selected, onSelect, disabled }: Props) {
  if (formats.length === 0) return null;
  return (
    <fieldset disabled={disabled} className="space-y-2.5">
      <legend className="mb-3 text-sm font-semibold text-ink">Available formats</legend>
      <div role="radiogroup" aria-label="Choose a format" className="grid gap-2.5">
        {formats.map((f) => {
          const active = selected === f.id;
          const size = formatBytes(f.filesize);
          const dims = f.width && f.height ? `${f.width}×${f.height}` : null;
          return (
            <label
              key={f.id}
              className={`relative flex cursor-pointer items-center gap-3.5 rounded-2xl border px-4 py-3.5 transition
                ${!f.available ? "cursor-not-allowed border-dashed border-line bg-canvas opacity-70" : ""}
                ${f.available && active ? "border-brand-500 bg-brand-50/70 shadow-ring" : ""}
                ${f.available && !active ? "border-line bg-white hover:border-brand-200 hover:bg-brand-50/40" : ""}`}
            >
              <input
                type="radio"
                name="format"
                value={f.id}
                checked={active}
                disabled={!f.available || disabled}
                onChange={() => onSelect(f.id)}
                className="peer sr-only"
              />
              <span
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${
                  active ? "bg-brand-600 text-white" : "bg-brand-50 text-brand-600"
                }`}
                aria-hidden
              >
                <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  {kindIcon[f.kind]}
                </svg>
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-semibold text-ink">
                  {f.label}
                  {f.derived && (
                    <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-medium text-ink-soft ring-1 ring-line">
                      Converted
                    </span>
                  )}
                </span>
                <span className="mt-0.5 block text-xs text-ink-mute">
                  {f.available
                    ? [dims, size, f.container?.toUpperCase()].filter(Boolean).join(" · ") || "Size reported after processing"
                    : f.unavailable_reason ?? "Not available"}
                </span>
              </span>
              <span
                className={`h-5 w-5 shrink-0 rounded-full border-2 transition ${
                  active ? "border-brand-600 bg-brand-600 shadow-[inset_0_0_0_3px_white]" : "border-line"
                } peer-focus-visible:ring-2 peer-focus-visible:ring-brand-500 peer-focus-visible:ring-offset-2`}
                aria-hidden
              />
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
