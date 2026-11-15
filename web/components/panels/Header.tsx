"use client";
// Header (plan §6.4/§6.6): brand, LIVE/REPLAY, simulation state, scenario, topology, mission, policy, security, nav.
import Link from "next/link";
import { claimsAt, topoLabel, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { useTwin } from "@/components/shell/ui";

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

  return (
    <header className={`flex items-center gap-4 rounded-[10px] border border-line bg-panel px-4 py-1.5 ${className ?? ""}`}>
      <div className="flex flex-none items-center gap-3">
        <div className="grid h-[30px] w-[30px] place-items-center rounded-[7px] bg-ink">
          <svg width="18" height="18" viewBox="0 0 18 18">
            <path d="M3 4h12L3 14h12" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <h1 className="text-[14.5px] font-extrabold leading-tight tracking-[0.14em]">ZERO-HOUR</h1>
          <div className="text-[9.5px] font-semibold tracking-[0.2em] text-muted">SECURE ADAPTIVE MISSION CONTROL · SAMG</div>
        </div>
      </div>

      <span
        className={`flex flex-none items-center rounded-[7px] border px-2.5 py-1 text-[11px] font-bold ${
          mode === "live" ? "border-[#a7e3cd] bg-ok-bg text-ok" : "border-line bg-panel2 text-ink"
        }`}
        title={source}
      >
        <span className={`zh-dot ${mode === "live" ? "pulse bg-ok" : "bg-samg"}`} />
        {mode === "live" ? "LIVE" : "REPLAY"}
        <span className="ml-1.5 font-semibold text-muted">· {mode === "live" ? `session ${state?.live?.session_id?.slice(0, 8) ?? "—"}` : source.replace(/^REPLAY · /, "") || "recorded SAMG run"}</span>
      </span>

      <nav className="flex flex-none items-center gap-1 text-[11.5px] font-semibold">
        <Link className="rounded-md px-2 py-1 text-ink2 hover:bg-panel2" href="/compare">
          Compare
        </Link>
        <Link className="rounded-md px-2 py-1 text-ink2 hover:bg-panel2" href="/replays">
          Replays
        </Link>
      </nav>

      <div className="ml-auto flex min-w-0 flex-wrap justify-end gap-1.5">
        <Hs label="Simulation">
          {complete ? (
            <span className="text-ok">● COMPLETE</span>
          ) : playing ? (
            <span className="pulse text-ok">● RUNNING</span>
          ) : (
            <span className="text-warn">❚❚ PAUSED</span>
          )}
        </Hs>
        <Hs label="Scenario">{scenario}</Hs>
        <Hs label="Topology">{w ? topoLabel(w.topology) : "—"}</Hs>
        <Hs label="Mission">
          <span className="mono">{w ? `${w.mission_id}${w.status === "preview" ? " · preview" : ""}` : "—"}</span>
        </Hs>
        <Hs label="Policy">{state ? state.spec.policy_label.split("(")[0].trim() : "—"}</Hs>
        <Hs label="Security">
          {viol ? <span className="text-sec">⚠ {viol} rejected</span> : <span className="text-ok">● SECURE</span>}
        </Hs>
      </div>
    </header>
  );
}

function Hs({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="zh-hs">
      <label>{label}</label>
      <b>{children}</b>
    </div>
  );
}

export default Header;
