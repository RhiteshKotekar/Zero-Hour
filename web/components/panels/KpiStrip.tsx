"use client";
// Streamlined KPI strip: Focuses on the 5 core operational metrics with ample whitespace and clear typography.
import { fmtS, kpisAt, pct } from "@/lib/derive";
import { useTwin } from "@/components/shell/ui";

export interface KpiStripProps {
  className?: string;
}

export function KpiStrip({ className }: KpiStripProps) {
  const { state, t } = useTwin();
  const k = state ? kpisAt(state, t) : null;

  const items: [label: string, value: string, sub: string, color?: string][] = k
    ? [
        ["Order Completion", pct(k.ocr), k.ocrN],
        ["Fleet Utilization", pct(k.util), "active mobile fleet"],
        ["Avg Task Latency", fmtS(k.lat), "release → start"],
        ["Congestion Delay", fmtS(k.cong), "aisle-lock wait time"],
        ["Failed Tasks", String(k.fails), k.fails === 0 ? "zero task failures" : "executed then failed", k.fails ? "var(--bad)" : "var(--ok)"],
      ]
    : [];

  return (
    <div className={`grid grid-cols-5 rounded-2xl border border-line bg-panel shadow-sm overflow-hidden ${className ?? ""}`}>
      {items.map(([label, value, sub, color]) => (
        <div key={label} className="flex flex-col justify-center border-r border-line px-5 py-2.5 last:border-r-0">
          <span className="text-[9.5px] font-bold uppercase tracking-wider text-muted">{label}</span>
          <div className="mt-0.5 flex items-baseline gap-2">
            <span className="mono text-[19px] font-bold tracking-tight" style={{ color: color ?? "var(--ink)" }}>
              {value}
            </span>
            <span className="truncate text-[11px] font-medium text-muted">{sub}</span>
          </div>
        </div>
      ))}
      {!k && <div className="zh-empty col-span-5 text-center">Loading telemetry metrics…</div>}
    </div>
  );
}

export default KpiStrip;
