import { PLATFORM_META } from "@/lib/platform";
import type { Platform } from "@/lib/types";

export function PlatformBadge({ platform, size = "md" }: { platform: Platform; size?: "sm" | "md" }) {
  const meta = PLATFORM_META[platform];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold ${meta.tint} ${
        size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} aria-hidden />
      {meta.name}
    </span>
  );
}
