import type { Platform } from "./types";

// Cosmetic, client-side hint only. The server performs the authoritative validation.
const HOSTS: Record<Platform, string[]> = {
  youtube: ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"],
  instagram: ["instagram.com", "www.instagram.com"],
  x: ["x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"],
};

export const PLATFORM_META: Record<Platform, { name: string; dot: string; tint: string }> = {
  youtube: { name: "YouTube", dot: "bg-[#E5484D]", tint: "bg-[#FFF1F1] text-[#B4232A]" },
  instagram: { name: "Instagram", dot: "bg-[#C2449F]", tint: "bg-[#FCF0F8] text-[#8E2A72]" },
  x: { name: "X", dot: "bg-ink", tint: "bg-[#EEF0F4] text-ink" },
};

export function detectPlatform(input: string): Platform | null {
  const raw = input.trim();
  if (!raw) return null;
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    const host = url.hostname.toLowerCase();
    for (const [p, hosts] of Object.entries(HOSTS) as [Platform, string[]][]) {
      if (hosts.includes(host)) return p;
    }
  } catch {
    return null;
  }
  return null;
}

export function formatDuration(seconds: number | null): string | null {
  if (!seconds || seconds <= 0) return null;
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}

export function formatBytes(n: number | null): string | null {
  if (!n) return null;
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}
