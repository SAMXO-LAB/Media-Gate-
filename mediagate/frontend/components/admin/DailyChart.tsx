"use client";

import { useMemo, useState } from "react";

interface Row {
  day: string;
  event: string;
  n: number;
}

const SERIES = [
  { key: "analyze", label: "Analyses", color: "#9CB9FF" },
  { key: "job_completed", label: "Completed jobs", color: "#1F4FF0" },
  { key: "job_failed", label: "Failed jobs", color: "#E5484D" },
] as const;

export function DailyChart({ rows }: { rows: Row[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const days = useMemo(() => {
    const map = new Map<string, Record<string, number>>();
    for (const r of rows) {
      const d = map.get(r.day) ?? {};
      d[r.event] = (d[r.event] ?? 0) + r.n;
      map.set(r.day, d);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [rows]);

  if (days.length === 0) {
    return <p className="py-12 text-center text-sm text-ink-mute">No activity in this period yet.</p>;
  }

  const max = Math.max(1, ...days.map(([, d]) => Math.max(...SERIES.map((s) => d[s.key] ?? 0))));
  const W = 720;
  const H = 200;
  const pad = { l: 32, r: 8, t: 8, b: 24 };
  const groupW = (W - pad.l - pad.r) / days.length;
  const barW = Math.max(2, Math.min(14, (groupW - 6) / SERIES.length));
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-4 text-xs text-ink-soft">
        {SERIES.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} aria-hidden />
            {s.label}
          </span>
        ))}
      </div>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Daily activity chart">
          {[0, 0.5, 1].map((f) => (
            <g key={f}>
              <line x1={pad.l} x2={W - pad.r} y1={y(max * f)} y2={y(max * f)} stroke="#E3E8F2" />
              <text x={pad.l - 6} y={y(max * f) + 3} textAnchor="end" fontSize="10" fill="#6B7894">
                {Math.round(max * f)}
              </text>
            </g>
          ))}
          {days.map(([day, d], i) => {
            const x0 = pad.l + i * groupW + (groupW - barW * SERIES.length) / 2;
            return (
              <g key={day} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                <rect x={pad.l + i * groupW} y={pad.t} width={groupW} height={H - pad.t - pad.b} fill={hover === i ? "#F2F6FF" : "transparent"} />
                {SERIES.map((s, j) => {
                  const v = d[s.key] ?? 0;
                  return <rect key={s.key} x={x0 + j * barW} y={y(v)} width={barW - 1} height={Math.max(0, H - pad.b - y(v))} rx="1.5" fill={s.color} />;
                })}
                {(days.length <= 14 || i % 2 === 0) && (
                  <text x={pad.l + i * groupW + groupW / 2} y={H - 8} textAnchor="middle" fontSize="10" fill="#6B7894">
                    {day.slice(5)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        {hover !== null && days[hover] && (
          <div className="pointer-events-none absolute right-2 top-0 rounded-xl border border-line bg-white px-3 py-2 text-xs shadow-card">
            <p className="font-semibold text-ink">{days[hover][0]}</p>
            {SERIES.map((s) => (
              <p key={s.key} className="text-ink-soft">
                {s.label}: <span className="font-mono text-ink">{days[hover]![1][s.key] ?? 0}</span>
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
