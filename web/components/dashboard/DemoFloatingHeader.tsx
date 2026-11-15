"use client";

// Floating Top Glass HUD for Full-Screen 3D Demo Dashboard
import { useEffect } from "react";
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
  const theme = useStore((s) => s.theme);
  const toggleTheme = useStore((s) => s.toggleTheme);
  const end = state?.end_s ?? 0;
  const w = state ? waveAt(state, t) : null;
  const viol = state ? claimsAt(state, t).filter((c) => c.evidence === "DISPUTED").length : 0;
  const complete = mode === "replay" ? state != null && t >= end - 1e-3 : !!state?.live?.complete;
  const scenario = state ? (state.spec.scenario === "judge_demo" ? "Judge Demo" : state.spec.label ?? state.spec.scenario) : "—";
  const topologyName = w ? topoLabel(w.topology) : "—";

  const orderCount = state?.orders.length ?? 0;
  const robotCount = state?.robots.filter((r) => r.mobile).length ?? 10;

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.classList.toggle("dark", theme === "dark");
    }
  }, [theme]);

  return (
    <header className="pointer-events-none absolute inset-x-4 top-4 z-30 flex items-center justify-between gap-3 select-none">
      {/* Left Island: Brand, Mode, and Scenario */}
      <div className="pointer-events-auto flex items-center gap-3.5 rounded-3xl border border-line bg-panel/92 px-5 py-3 shadow-lg backdrop-blur-xl transition-all hover:bg-panel">
        <div className="grid h-10 w-10 place-items-center rounded-2xl bg-ink text-white shadow-xs">
          <svg width="22" height="22" viewBox="0 0 18 18">
            <path d="M3 4h12L3 14h12" stroke="#fff" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <span className="text-base font-black tracking-tight text-ink">ZERO-HOUR</span>
            <span className="rounded-md bg-accent-bg px-2 py-0.5 text-xs font-black text-accent">
              SAMG
            </span>
          </div>
          <span className="text-xs font-bold text-muted">
            {scenario} {w ? `· ${w.mission_id}` : ""}
          </span>
        </div>

        <div className="mx-1 h-6 w-px bg-line" />

        {/* Live / Replay status */}
        <div className="flex items-center gap-2 text-xs font-bold">
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              complete ? "bg-ok" : playing ? "animate-pulse bg-ok" : "bg-warn"
            }`}
          />
          <span className={complete ? "font-extrabold text-ok" : playing ? "font-extrabold text-ok" : "font-extrabold text-warn"}>
            {complete ? "Completed" : playing ? "Live Run" : "Paused"}
          </span>
        </div>

        <div className="mx-1 h-6 w-px bg-line" />

        {/* Quick Nav Links */}
        <nav className="flex items-center gap-1.5 text-xs font-bold text-muted">
          <Link href="/compare" className="rounded-xl px-3 py-1.5 hover:bg-panel2 hover:text-ink transition-colors">
            Compare
          </Link>
          <Link href="/replays" className="rounded-xl px-3 py-1.5 hover:bg-panel2 hover:text-ink transition-colors">
            Replays
          </Link>
          <Link
            href="/compare-replay"
            className="rounded-xl border border-samg/30 bg-samg-bg px-3 py-1.5 text-samg transition-colors hover:border-samg"
            title="Side-by-side replay: SAMG vs conventional baseline on the identical mission"
          >
            SAMG vs Baseline
          </Link>
        </nav>
      </div>

      {/* Center Floating Badges (Subtle status indicator) */}
      <div className="pointer-events-auto hidden md:flex items-center gap-3 rounded-full border border-line bg-panel/90 px-5 py-2.5 shadow-md backdrop-blur-xl">
        <div className="flex items-center gap-2 text-xs font-bold text-muted">
          <span>Topology:</span>
          <span className="font-black text-ink">{topologyName}</span>
        </div>
        <span className="text-line">•</span>
        <div className="flex items-center gap-2 text-xs font-bold text-muted">
          <span>Security:</span>
          {viol > 0 ? (
            <span className="font-black text-sec">⚠ {viol} disputed</span>
          ) : (
            <span className="font-black text-ok">✓ 100% ACP Verified</span>
          )}
        </div>
        <span className="text-line">•</span>
        <div className="flex items-center gap-2 text-xs font-bold text-muted">
          <span>Fleet:</span>
          <span className="font-black text-ink">{robotCount} AMRs</span>
        </div>
      </div>

      {/* Right Controls: Dark Mode Toggle, View Switcher, and Telemetry Trigger */}
      <div className="pointer-events-auto flex items-center gap-2.5">
        {/* Dark/Light Mode Switcher */}
        <button
          onClick={toggleTheme}
          className="flex h-11 w-11 items-center justify-center rounded-2xl border border-line bg-panel text-ink shadow-md backdrop-blur-xl transition-all hover:bg-panel2 hover:scale-105 active:scale-95"
          title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        >
          {theme === "dark" ? (
            <svg className="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          ) : (
            <svg className="h-5 w-5 text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
          )}
        </button>

        {/* Toggle between Demo and Detailed dashboard */}
        <div className="rounded-2xl border border-line bg-panel p-1 shadow-md backdrop-blur-xl">
          <DashboardSwitch />
        </div>

        {/* Sidebar Toggle Button */}
        <button
          onClick={onToggleSidebar}
          className={`group flex items-center gap-3 rounded-2xl border px-4 py-2.5 text-xs font-black shadow-lg backdrop-blur-xl transition-all hover:scale-[1.02] active:scale-[0.98] ${
            isSidebarOpen
              ? "border-accent bg-accent text-white shadow-accent/25"
              : "border-line bg-panel text-ink hover:bg-panel2 hover:border-accent/40"
          }`}
          title={isSidebarOpen ? "Collapse telemetry sidebar" : "Open telemetry & data sidebar"}
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
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
          <span className={`flex h-5 items-center rounded-full px-2 text-xs font-black ${
            isSidebarOpen ? "bg-white/25 text-white" : "bg-accent-bg text-accent"
          }`}>
            {orderCount} Orders
          </span>
        </button>
      </div>
    </header>
  );
}

export default DemoFloatingHeader;
