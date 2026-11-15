"use client";

// Demo Dashboard Header
// Clean, minimal, judge-ready top app bar with essential context, status pills, and the view switcher.
import Link from "next/link";
import { claimsAt, topoLabel, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { useTwin } from "@/components/shell/ui";
import { DashboardSwitch } from "./DashboardSwitch";

export function DemoHeader() {
  const { state, t } = useTwin();
  const mode = useStore((s) => s.mode);
  const playing = useStore((s) => s.clock.playing);
  const end = state?.end_s ?? 0;
  const w = state ? waveAt(state, t) : null;
  const viol = state ? claimsAt(state, t).filter((c) => c.evidence === "DISPUTED").length : 0;
  const complete = mode === "replay" ? state != null && t >= end - 1e-3 : !!state?.live?.complete;
  const scenario = state ? (state.spec.scenario === "judge_demo" ? "Judge Demo" : state.spec.label ?? state.spec.scenario) : "—";
  const topologyName = w ? topoLabel(w.topology) : "Hierarchical";

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-panel px-4 py-2.5 shadow-sm">
      {/* Brand & Product Identity */}
      <div className="flex items-center gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-ink text-white shadow-xs">
          <svg width="20" height="20" viewBox="0 0 18 18">
            <path d="M3 4h12L3 14h12" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-[15px] font-black tracking-tight text-ink">ZERO-HOUR</h1>
            <span className="rounded-md bg-accent-bg px-1.5 py-0.5 text-[10px] font-bold text-accent">
              SAMG GOVERNANCE
            </span>
          </div>
          <div className="text-[10px] font-medium text-muted">
            Secure Adaptive Multi-Agent Warehouse Fleet System
          </div>
        </div>
      </div>

      {/* Center Operational Status Pills (Human-readable for judges) */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Simulation State */}
        <div className="flex items-center gap-1.5 rounded-full border border-line bg-panel2/80 px-3 py-1 text-[11px] font-semibold text-ink">
          <span
            className={`h-2 w-2 rounded-full ${
              complete ? "bg-ok" : playing ? "animate-pulse bg-ok" : "bg-warn"
            }`}
          />
          <span className="text-muted">Status:</span>
          <span className={complete ? "font-bold text-ok" : playing ? "font-bold text-ok" : "font-bold text-warn"}>
            {complete ? "Completed" : playing ? "Running" : "Paused"}
          </span>
        </div>

        {/* Mission Scenario */}
        <div className="flex items-center gap-1.5 rounded-full border border-line bg-panel2/80 px-3 py-1 text-[11px] font-semibold text-ink">
          <span className="text-muted">Scenario:</span>
          <span className="font-bold text-ink">{scenario}</span>
          {w && (
            <span className="rounded bg-white px-1 text-[10px] font-mono text-muted border border-line">
              {w.mission_id}
            </span>
          )}
        </div>

        {/* Active Coordination Strategy */}
        <div className="flex items-center gap-1.5 rounded-full border border-samg/20 bg-samg-bg px-3 py-1 text-[11px] font-semibold text-samg">
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="2" width="6" height="6" rx="1" />
            <rect x="16" y="2" width="6" height="6" rx="1" />
            <rect x="9" y="16" width="6" height="6" rx="1" />
            <path d="M5 8v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8" />
            <line x1="12" y1="13" x2="12" y2="16" />
          </svg>
          <span className="text-samg/70">Strategy:</span>
          <span className="font-bold">{topologyName}</span>
        </div>

        {/* Security & ACP Assurance */}
        <div
          className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold ${
            viol
              ? "border-sec/30 bg-sec-bg text-sec"
              : "border-ok/30 bg-ok-bg text-ok"
          }`}
        >
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          <span>{viol ? `${viol} Rejected Claim` : "ACP Verified Secure"}</span>
        </div>
      </div>

      {/* Right Controls: Navigation + Dashboard Switch */}
      <div className="flex items-center gap-3">
        <nav className="flex items-center gap-1 text-[11.5px] font-medium text-ink2">
          <Link
            className="rounded-full px-2.5 py-1 transition-colors hover:bg-panel2 hover:text-ink"
            href="/compare"
          >
            Compare
          </Link>
          <Link
            className="rounded-full px-2.5 py-1 transition-colors hover:bg-panel2 hover:text-ink"
            href="/replays"
          >
            Replays
          </Link>
        </nav>

        {/* Dashboard View Switch */}
        <DashboardSwitch />
      </div>
    </header>
  );
}

export default DemoHeader;
