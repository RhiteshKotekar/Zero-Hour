"use client";

import { useStore } from "@/lib/store";

export function DashboardSwitch({ className }: { className?: string }) {
  const dashboardMode = useStore((s) => s.dashboardMode);
  const setDashboardMode = useStore((s) => s.setDashboardMode);

  return (
    <div
      className={`inline-flex items-center rounded-full border border-line bg-panel2/80 p-0.5 shadow-xs backdrop-blur-sm ${className ?? ""}`}
      role="group"
      aria-label="Dashboard View Switch"
    >
      <button
        type="button"
        onClick={() => setDashboardMode("demo")}
        className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-bold transition-all ${
          dashboardMode === "demo"
            ? "bg-accent text-white shadow-sm"
            : "text-muted hover:text-ink"
        }`}
        title="Switch to the streamlined, presentation-ready Demo Dashboard"
      >
        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
        </svg>
        <span>Demo View</span>
      </button>

      <button
        type="button"
        onClick={() => setDashboardMode("detailed")}
        className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-bold transition-all ${
          dashboardMode === "detailed"
            ? "bg-ink text-white shadow-sm"
            : "text-muted hover:text-ink"
        }`}
        title="Switch to the comprehensive Detailed Operational Dashboard"
      >
        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="8" y1="6" x2="21" y2="6" />
          <line x1="8" y1="12" x2="21" y2="12" />
          <line x1="8" y1="18" x2="21" y2="18" />
          <line x1="3" y1="6" x2="3.01" y2="6" />
          <line x1="3" y1="12" x2="3.01" y2="12" />
          <line x1="3" y1="18" x2="3.01" y2="18" />
        </svg>
        <span>Detailed View</span>
      </button>
    </div>
  );
}

export default DashboardSwitch;
