"use client";

import { AnimatePresence, motion } from "framer-motion";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

type Tone = "info" | "success" | "error";
interface Toast {
  id: number;
  tone: Tone;
  title: string;
  body?: string;
}

const Ctx = createContext<{ push: (t: Omit<Toast, "id">) => void } | null>(null);

export function useToast() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx.push;
}

const toneStyles: Record<Tone, { bar: string; icon: string }> = {
  info: { bar: "bg-brand-500", icon: "text-brand-600" },
  success: { bar: "bg-emerald-500", icon: "text-emerald-600" },
  error: { bar: "bg-rose-500", icon: "text-rose-600" },
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const push = useCallback(
    (t: Omit<Toast, "id">) => {
      const id = ++seq.current;
      setToasts((list) => [...list.slice(-3), { ...t, id }]);
      window.setTimeout(() => dismiss(id), t.tone === "error" ? 8000 : 5000);
    },
    [dismiss],
  );
  const value = useMemo(() => ({ push }), [push]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4 sm:bottom-6 sm:items-end sm:pr-6"
      >
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 420, damping: 32 }}
              role={t.tone === "error" ? "alert" : "status"}
              className="pointer-events-auto relative w-full max-w-sm overflow-hidden rounded-2xl border border-line bg-white py-3 pl-4 pr-10 shadow-lift"
            >
              <span className={`absolute inset-y-0 left-0 w-1 ${toneStyles[t.tone].bar}`} aria-hidden />
              <p className="text-sm font-semibold text-ink">{t.title}</p>
              {t.body && <p className="mt-0.5 text-sm text-ink-soft">{t.body}</p>}
              <button
                onClick={() => dismiss(t.id)}
                className="absolute right-2 top-2 rounded-full p-1.5 text-ink-mute hover:bg-brand-50 hover:text-ink"
                aria-label="Dismiss notification"
              >
                <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
                </svg>
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}
