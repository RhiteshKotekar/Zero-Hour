"use client";

// Floating Top Glass HUD for Full-Screen 3D Demo Dashboard
import Link from "next/link";
import { claimsAt, topoLabel, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { useTwin } from "@/components/shell/ui";
import { DashboardSwitch } from "./DashboardSwitch";

export interface DemoFloatingHeaderProps {
  onToggleSidebar: () => void;
  isSidebarOpen: boolean;
  activeSection?: string;
}

export function DemoFloatingHeader({
  onToggleSidebar,
  isSidebarOpen,
}: DemoFloatingHeaderProps) {
  const { state, t } = useTwin();
  const mode = useStore((s) => s.mode);
  const playing = useStore((s) => s.clock.playing);
  const end = state?.end_s ?? 0;
  const w = state ? waveAt(state, t) : null;
  const viol = state ? claimsAt(state, t).filter((c) => c.evidence === "DISPUTED").length : 0;
  const complete = mode === "replay" ? state != null && t >= end - 1e-3 : !!state?.live?.complete;
  const scenario = state ? (state.spec.scenario === "judge_demo" ? "Judge Demo" : state.spec.label ?? state.spec.scenario) : "—";
  const topologyName = w ? topoLabel(w.topology) : "Hierarchical";

  const orderCount = state?.orders.length ?? 0;
  const robotCount = state?.robots.filter((r) => r.mobile).length ?? 10;

  return (
    <header className="pointer-events-none absolute inset-x-4 top-4 z-30 flex items-center justify-between gap-3 select-none">
      {/* Left Island: Brand, Mode, and Scenario */}
      <div className="pointer-events-auto flex items-center gap-2.5 rounded-2xl border border-line/80 bg-white/90 px-3.5 py-2 shadow-lg backdrop-blur-md transition-all hover:bg-white">
        <div className="grid h-8 w-8 place-items-center rounded-xl bg-ink text-white shadow-xs">
          <svg width="18" height="18" viewBox="0 0 18 18">
            <path d="M3 4h12L3 14h12" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
            <span className="text-[13px] font-black tracking-tight text-ink">ZERO-HOUR</span>
            <span className="rounded bg-accent/10 px-1.5 py-0.2 text-[9.5px] font-bold text-accent">
              SAMG
            </span>
          </div>
          <span className="text-[9.5px] font-semibold text-muted">
            {scenario} {w ? `· ${w.mission_id}` : ""}
          </span>
        </div>

        <div className="mx-1 h-5 w-px bg-line/80" />

        {/* Live / Replay status */}
        <div className="flex items-center gap-1.5 text-[11px] font-semibold">
          <span
            className={`h-2 w-2 rounded-full ${
              complete ? "bg-ok" : playing ? "animate-pulse bg-ok" : "bg-warn"
            }`}
          />
          <span className={complete ? "font-bold text-ok" : playing ? "font-bold text-ok" : "font-bold text-warn"}>
            {complete ? "Completed" : playing ? "Live Run" : "Paused"}
          </span>
        </div>

        <div className="mx-1 h-5 w-px bg-line/80" />

        {/* Quick Nav Links */}
        <nav className="flex items-center gap-1 text-[11px] font-semibold text-muted">
          <Link href="/compare" className="rounded-md px-2 py-0.5 hover:bg-panel2 hover:text-ink transition-colors">
            Compare
          </Link>
          <Link href="/replays" className="rounded-md px-2 py-0.5 hover:bg-panel2 hover:text-ink transition-colors">
            Replays
          </Link>
        </nav>
      </div>

      {/* Center Floating Badges (Subtle status indicator) */}
      <div className="pointer-events-auto hidden md:flex items-center gap-2 rounded-full border border-line/80 bg-white/85 px-4 py-1.5 shadow-md backdrop-blur-md">
        <div className="flex items-center gap-1 text-[11px] text-muted">
          <span>Topology:</span>
          <span className="font-bold text-ink">{topologyName}</span>
        </div>
        <span className="text-line">•</span>
        <div className="flex items-center gap-1 text-[11px] text-muted">
          <span>Security:</span>
          {viol > 0 ? (
            <span className="font-bold text-sec">⚠ {viol} disputed</span>
          ) : (
            <span className="font-bold text-ok">✓ 100% ACP Verified</span>
          )}
        </div>
        <span className="text-line">•</span>
        <div className="flex items-center gap-1 text-[11px] text-muted">
          <span>Fleet:</span>
          <span className="font-bold text-ink">{robotCount} AMRs</span>
        </div>
      </div>

      {/* Right Controls: View Switcher and Telemetry Sidebar Trigger */}
      <div className="pointer-events-auto flex items-center gap-2">
        {/* Toggle between Demo and Detailed dashboard */}
        <div className="rounded-2xl border border-line/80 bg-white/90 p-1 shadow-lg backdrop-blur-md">
          <DashboardSwitch />
        </div>

        {/* Sidebar Toggle Button */}
        <button
          onClick={onToggleSidebar}
          className={`group flex items-center gap-2 rounded-2xl border px-3.5 py-2.5 text-xs font-bold shadow-lg backdrop-blur-md transition-all hover:scale-[1.02] active:scale-[0.98] ${
            isSidebarOpen
              ? "border-accent bg-accent text-white shadow-accent/25"
              : "border-line/80 bg-white/95 text-ink hover:bg-white hover:border-accent/40"
          }`}
          title={isSidebarOpen ? "Collapse telemetry sidebar" : "Open telemetry & data sidebar"}
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            {isSidebarOpen ? (
              <>
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M15 3v18" />
                <path d="m11 9 3 3-3 3" />
              </>
            ) : (
              <>
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M15 3v18" />
                <path d="m9 9-3 3 3 3" />
              </>
            )}
          </svg>
          <span className="hidden sm:inline">
            {isSidebarOpen ? "Close Sidebar" : "Mission Telemetry"}
          </span>
          <span className={`flex h-4 items-center rounded-full px-1.5 text-[9.5px] font-extrabold ${
            isSidebarOpen ? "bg-white/20 text-white" : "bg-accent-bg text-accent"
          }`}>
            {orderCount} Orders
          </span>
        </button>
      </div>
    </header>
  );
}

export default DemoFloatingHeader;
