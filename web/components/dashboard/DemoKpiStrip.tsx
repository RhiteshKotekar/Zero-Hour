"use client";

// Demo Dashboard KPI Strip
// Displays the key operational & governance metrics with clean enterprise typography,
// clear iconography, and human-understandable labels for hackathon judges.
import { fmtS, kpisAt, pct, topoLabel } from "@/lib/derive";
import { useTwin } from "@/components/shell/ui";

export interface DemoKpiStripProps {
  className?: string;
  onSelectMetric?: (tabKey: string) => void;
}

export function DemoKpiStrip({ className, onSelectMetric }: DemoKpiStripProps) {
  const { state, t } = useTwin();
  const k = state ? kpisAt(state, t) : null;

  if (!k) {
    return (
      <div className={`grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 rounded-2xl border border-line bg-panel p-3 shadow-sm ${className ?? ""}`}>
        <div className="col-span-full py-4 text-center text-xs text-muted">
          Loading operational metrics…
        </div>
      </div>
    );
  }

  const cards = [
    {
      id: "orders",
      label: "Order Completion",
      value: pct(k.ocr),
      subtext: `${k.ocrN} orders fulfilled`,
      color: "text-ink",
      targetTab: "alloc",
      icon: (
        <svg className="h-4 w-4 text-emerald-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
      ),
    },
    {
      id: "utilization",
      label: "Fleet Utilization",
      value: pct(k.util),
      subtext: "Mobile robots active",
      color: "text-ink",
      targetTab: "fleet",
      icon: (
        <svg className="h-4 w-4 text-blue-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
          <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
        </svg>
      ),
    },
    {
      id: "latency",
      label: "Avg Task Latency",
      value: fmtS(k.lat),
      subtext: "Release to start wait",
      color: "text-ink",
      targetTab: "alloc",
      icon: (
        <svg className="h-4 w-4 text-indigo-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <polyline points="12 6 12 12 16 14" />
        </svg>
      ),
    },
    {
      id: "travel",
      label: "Travel Distance",
      value: `${Math.round(k.dist)} m`,
      subtext: "Fleet total traveled",
      color: "text-ink",
      targetTab: "fleet",
      icon: (
        <svg className="h-4 w-4 text-teal-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="4 17 10 11 4 5" />
          <line x1="12" y1="19" x2="20" y2="19" />
        </svg>
      ),
    },
    {
      id: "congestion",
      label: "Congestion Wait",
      value: fmtS(k.cong),
      subtext: "Narrow aisle locks",
      color: k.cong > 15 ? "text-amber-600" : "text-ink",
      targetTab: "events",
      icon: (
        <svg className="h-4 w-4 text-amber-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      ),
    },
    {
      id: "failures",
      label: "Failed & Recovered",
      value: String(k.fails),
      subtext: k.fails > 0 ? "Replanned dynamically" : "0 hardware faults",
      color: k.fails > 0 ? "text-red-600" : "text-ink",
      targetTab: "events",
      icon: (
        <svg className="h-4 w-4 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
      ),
    },
    {
      id: "security",
      label: "Security Verification",
      value: k.viol ? `${k.viol} Rejected` : "100% Valid",
      subtext: "ACP cryptographic gate",
      color: k.viol ? "text-purple-600 font-bold" : "text-emerald-700",
      targetTab: "sec",
      icon: (
        <svg className="h-4 w-4 text-purple-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
      ),
    },
    {
      id: "policy",
      label: "Coordination Policy",
      value: topoLabel(k.topo),
      subtext: k.rew == null ? "Learning active" : `Score: ${k.rew.toFixed(3)}`,
      color: "text-samg font-bold",
      targetTab: "prov",
      icon: (
        <svg className="h-4 w-4 text-cyan-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="12 2 2 7 12 12 22 7 12 2" />
          <polyline points="2 17 12 22 22 17" />
          <polyline points="2 12 12 17 22 12" />
        </svg>
      ),
    },
  ];

  return (
    <div
      className={`grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 rounded-2xl border border-line bg-panel p-2.5 shadow-sm ${
        className ?? ""
      }`}
    >
      {cards.map((card) => (
        <div
          key={card.id}
          onClick={() => onSelectMetric?.(card.targetTab)}
          className="group flex flex-col justify-between rounded-xl border border-line/60 bg-panel2/50 p-2.5 transition-all hover:border-line2 hover:bg-white hover:shadow-xs cursor-pointer select-none"
        >
          <div className="flex items-center justify-between gap-1 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted truncate">
              {card.label}
            </span>
            <div className="p-1 rounded-lg bg-white border border-line/80 shadow-2xs group-hover:scale-105 transition-transform">
              {card.icon}
            </div>
          </div>

          <div>
            <div className={`mono text-[16px] font-black tracking-tight leading-snug ${card.color}`}>
              {card.value}
            </div>
            <div className="text-[10px] font-medium text-muted truncate mt-0.5">
              {card.subtext}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default DemoKpiStrip;
