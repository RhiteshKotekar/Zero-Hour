"use client";
// Header: Brand, LIVE/REPLAY mode, Navigation, and streamlined Telemetry ribbon with clean whitespace.
import Link from "next/link";
import { claimsAt, topoLabel, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { useTwin } from "@/components/shell/ui";
import { DashboardSwitch } from "@/components/dashboard/DashboardSwitch";

export interface HeaderProps {
  className?: string;
}

export function Header({ className }: HeaderProps) {
  const { state, t } = useTwin();
  const mode = useStore((s) => s.mode);
  const source = useStore((s) => s.source);
  const playing = useStore((s) => s.clock.playing);
  const end = state?.end_s ?? 0;
  const w = state ? waveAt(state, t) : null;
  const viol = state ? claimsAt(state, t).filter((c) => c.evidence === "DISPUTED").length : 0;
  const complete = mode === "replay" ? state != null && t >= end - 1e-3 : !!state?.live?.complete;
  const scenario = state ? (state.spec.scenario === "judge_demo" ? "Judge demo" : state.spec.label ?? state.spec.scenario) : "—";
  const policyLabel = state ? state.spec.policy_label.split("(")[0].trim() : "—";

  return (
    <header className={`flex items-center gap-5 rounded-2xl border border-line bg-panel px-4 py-2 shadow-xs ${className ?? ""}`}>
      {/* Brand & Mission Title */}
      <div className="flex flex-none items-center gap-3">
        <div className="grid h-[32px] w-[32px] place-items-center rounded-xl bg-ink shadow-xs">
          <svg width="18" height="18" viewBox="0 0 18 18">
            <path d="M3 4h12L3 14h12" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <h1 className="text-[14px] font-extrabold leading-tight tracking-[0.14em] text-ink">ZERO-HOUR</h1>
          <div className="text-[9.5px] font-semibold tracking-[0.18em] text-muted">SAMG MISSION CONTROL</div>
        </div>
      </div>

      {/* Mode Badge (Live / Replay) */}
      <span
        className={`flex flex-none items-center rounded-full border px-3 py-1 text-[11px] font-bold shadow-xs transition-colors ${
          mode === "live" ? "border-ok/30 bg-ok-bg text-ok" : "border-line bg-panel2 text-ink"
        }`}
        title={source}
      >
        <span className={`zh-dot ${mode === "live" ? "pulse bg-ok" : "bg-samg"}`} />
        {mode === "live" ? "LIVE" : "REPLAY"}
        <span className="ml-1.5 font-normal text-muted">
          · {mode === "live" ? `session ${state?.live?.session_id?.slice(0, 8) ?? "—"}` : source.replace(/^REPLAY · /, "") || "recorded SAMG run"}
        </span>
      </span>

      {/* Navigation */}
      <nav className="flex flex-none items-center gap-1.5 text-[11.5px] font-semibold">
        <Link className="rounded-full px-3 py-1 text-ink2 transition-colors hover:bg-panel2 hover:text-ink" href="/compare">
          Compare
        </Link>
        <Link
          className="inline-flex items-center gap-1.5 rounded-full border border-samg/30 bg-samg-bg px-3 py-1 text-samg transition-colors hover:border-samg hover:bg-panel"
          href="/compare-replay"
          title="Side-by-side replay: SAMG vs conventional baseline on the identical mission"
        >
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <rect x="0.75" y="1.75" width="4.5" height="8.5" rx="1" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <rect x="6.75" y="1.75" width="4.5" height="8.5" rx="1" fill="none" stroke="currentColor" strokeWidth="1.4" />
          </svg>
          SAMG vs Baseline
        </Link>
        <Link className="rounded-full px-3 py-1 text-ink2 transition-colors hover:bg-panel2 hover:text-ink" href="/replays">
          Replays
        </Link>
      </nav>

      {/* View Mode Switch */}
      <DashboardSwitch />

      {/* Clean Telemetry Ribbon (Proper whitespace, no heavy boxy frames) */}
      <div className="ml-auto flex min-w-0 items-center gap-4 text-left">
        {/* Simulation State Pill */}
        <div className="flex flex-col items-start">
          <span className="text-[9px] font-bold uppercase tracking-wider text-muted">Status</span>
          <span className={`mt-0.5 inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
            complete ? "bg-ok-bg text-ok" : playing ? "bg-ok-bg text-ok" : "bg-warn-bg text-warn"
          }`}>
            {complete ? "● COMPLETE" : playing ? <><span className="zh-dot pulse bg-ok !mr-1" />RUNNING</> : "❚❚ PAUSED"}
          </span>
        </div>

        <div className="h-7 w-px bg-line/80" />

        {/* Scenario & Wave */}
        <div className="flex flex-col">
          <span className="text-[9px] font-bold uppercase tracking-wider text-muted">Scenario · Wave</span>
          <div className="mt-0.5 text-[12px] font-semibold text-ink">
            {scenario} <span className="mono font-bold text-accent">· {w ? `${w.mission_id}${w.status === "preview" ? " (preview)" : ""}` : "—"}</span>
          </div>
        </div>

        <div className="h-7 w-px bg-line/80" />

        {/* Topology & Policy */}
        <div className="flex flex-col">
          <span className="text-[9px] font-bold uppercase tracking-wider text-muted">Topology · Policy</span>
          <div className="mt-0.5 text-[12px] font-bold text-ink">
            {w ? topoLabel(w.topology) : "—"} <span className="text-[11px] font-normal text-muted">({policyShort(policyLabel)})</span>
          </div>
        </div>

        <div className="h-7 w-px bg-line/80" />

        {/* Security / ACP Assurance */}
        <div className="flex flex-col">
          <span className="text-[9px] font-bold uppercase tracking-wider text-muted">Assurance</span>
          <div className="mt-0.5">
            {viol ? (
              <span className="inline-flex items-center rounded-md bg-sec-bg px-2 py-0.5 text-[11px] font-bold text-sec">
                ⚠ {viol} rejected
              </span>
            ) : (
              <span className="inline-flex items-center rounded-md bg-ok-bg px-2 py-0.5 text-[11px] font-bold text-ok">
                ● SECURE
              </span>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

function policyShort(label: string): string {
  if (label.includes("LinUCB")) return "LinUCB";
  if (label.includes("UCB1")) return "UCB1";
  if (label.includes("P0")) return "Fixed";
  return label;
}

export default Header;
