"use client";
// KPI strip (plan §6.4): the 10 KPIs of derive.kpisAt(state, t) — revealed by time.
import { fmtS, kpisAt, pct, topoLabel } from "@/lib/derive";
import { useTwin } from "@/components/shell/ui";

export interface KpiStripProps {
  className?: string;
}

export function KpiStrip({ className }: KpiStripProps) {
  const { state, t } = useTwin();
  const k = state ? kpisAt(state, t) : null;
  const items: [label: string, value: string, sub: string, color?: string, small?: boolean][] = k
    ? [
        ["Order completion", pct(k.ocr), k.ocrN],
        ["Avg fulfilment", fmtS(k.ful), "witness-verified dispatch"],
        ["Avg task latency", fmtS(k.lat), "release → start"],
        ["Robot utilization", pct(k.util), "mobile fleet busy share"],
        ["Travel distance", `${Math.round(k.dist)} m`, "all robots"],
        ["Congestion time", fmtS(k.cong), "aisle-lock waits"],
        ["Failed tasks", String(k.fails), "executed then failed", k.fails ? "var(--bad)" : undefined],
        ["Security violations", String(k.viol), "claims disputed by ACP", k.viol ? "var(--sec)" : undefined],
        ["Secure reward", k.rew == null ? "pending" : k.rew.toFixed(3), k.rew == null ? "after ACP admission" : `ACP-recomputed · ${k.rewW}`, k.rew == null ? "var(--faint)" : undefined],
        ["Current topology", topoLabel(k.topo), "SAMG selection", undefined, true],
      ]
    : [];
  return (
    <div className={`grid grid-cols-10 rounded-2xl border border-line bg-panel shadow-sm overflow-hidden ${className ?? ""}`}>
      {items.map(([label, value, sub, color, small]) => (
        <div key={label} className="zh-kpi">
          <b style={{ color, fontSize: small ? 14 : undefined, lineHeight: small ? "25px" : undefined }}>{value}</b>
          <label>{label}</label>
          <small>{sub}</small>
        </div>
      ))}
      {!k && <div className="zh-empty col-span-10">Loading…</div>}
    </div>
  );
}

export default KpiStrip;
