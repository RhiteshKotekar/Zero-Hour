"use client";
// Live quick controls, shared by the Demo and Detailed views:
//  • replay → "Go live": starts a live SAMG session for the chosen scenario and presses Play (shortcut L);
//  • live   → topology switch Auto | Hierarchical | Functional cell | Distributed (shortcuts 0–3), applied by the
//             server from the next wave it plans (samg.twin.live set_topology), plus "Back to replay".
// Space toggles play/pause in either mode. Shortcuts ignore keystrokes typed into inputs.
import { useEffect, useState, useSyncExternalStore } from "react";
import * as api from "@/lib/api";
import { startSession, switchToReplay, useLive } from "@/lib/live";
import { topoLabel, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import type { Topology } from "@/lib/types";

export const LIVE_SCENARIOS: { id: string; label: string }[] = [
  { id: "continuous", label: "Continuous demand (many waves)" },
  { id: "aisle_failure", label: "Aisle failure + reroute" },
  { id: "judge_demo", label: "Judge demo (attack + failure)" },
  { id: "clean", label: "Clean operations" },
  { id: "rush", label: "Rush order stream" },
];
const TOPOS: { id: Topology | null; short: string; key: string }[] = [
  { id: null, short: "Auto", key: "0" },
  { id: "HIERARCHICAL", short: "Hierarchical", key: "1" },
  { id: "FUNCTIONAL_CELL", short: "Cell", key: "2" },
  { id: "DISTRIBUTED", short: "Distributed", key: "3" },
];
const SCENARIO_KEY = "zh_live_scenario";
const noSubscribe = () => () => undefined;

function savedScenario(): string {
  try {
    const v = localStorage.getItem(SCENARIO_KEY);
    if (v && LIVE_SCENARIOS.some((s) => s.id === v)) return v;
  } catch {
    // storage blocked
  }
  return "continuous";
}

/** Start a live session and press play. */
export async function goLive(scenario: string): Promise<void> {
  const push = useStore.getState().pushToast;
  try {
    localStorage.setItem(SCENARIO_KEY, scenario);
  } catch {
    // storage blocked
  }
  try {
    await startSession({ scenario });
    const r = await api.control("play");
    useStore.getState().applyServerClock(r.clock);
    push("ok", `Live session started: ${LIVE_SCENARIOS.find((s) => s.id === scenario)?.label ?? scenario}`);
  } catch (e) {
    push("bad", `Could not start the live session: ${(e as Error).message}`);
  }
}

export async function forceTopology(topology: Topology | null): Promise<void> {
  const push = useStore.getState().pushToast;
  try {
    const r = await api.setTopology(topology);
    push(topology ? "warn" : "ok", r.effect);
  } catch (e) {
    push("bad", `Topology override failed: ${(e as Error).message}`);
  }
}

/** A real injection on the live session (replay: explains how to go live). */
export async function liveInject(req: api.InjectRequest, label: string): Promise<void> {
  const s = useStore.getState();
  if (s.mode !== "live") {
    s.pushToast("info", `${label}: injections need a live session — press L or "Go live"`);
    return;
  }
  try {
    const r = await api.inject(req);
    s.pushToast(r.accepted ? "warn" : "info", `${label}: ${r.effect}`);
  } catch (e) {
    s.pushToast("bad", `${label} failed: ${(e as Error).message}`);
  }
}

/** Keyboard shortcuts (mount once per page). */
export function useLiveShortcuts(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (e.ctrlKey || e.metaKey || e.altKey || (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)))) return;
      const s = useStore.getState();
      if (e.key === " ") {
        if (!s.state) return;
        e.preventDefault();
        s.togglePlay();
      } else if ((e.key === "l" || e.key === "L") && s.mode !== "live" && !useLive.getState().starting) {
        void goLive(savedScenario());
      } else if (s.mode === "live") {
        const t = TOPOS.find((x) => x.key === e.key);
        if (t) void forceTopology(t.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

export function LiveDock({ className }: { className?: string }) {
  const mode = useStore((s) => s.mode);
  const state = useStore((s) => s.state);
  const t = useStore((s) => s.clock.t);
  const starting = useLive((s) => s.starting);
  // saved choice on the client, the default during SSR (no hydration mismatch)
  const saved = useSyncExternalStore(noSubscribe, savedScenario, () => "continuous");
  const [picked, setScenario] = useState<string | null>(null);
  const scenario = picked ?? saved;

  if (mode !== "live") {
    return (
      <div className={`flex items-center gap-1.5 ${className ?? ""}`}>
        <select
          aria-label="Live scenario"
          className="rounded-full border border-line2 bg-panel px-2.5 py-1 text-[11.5px] font-semibold text-ink"
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
        >
          {LIVE_SCENARIOS.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
        <button
          className="btn primary"
          disabled={!!starting}
          onClick={() => void goLive(scenario)}
          title="Start a live SAMG session for this scenario and press play (shortcut: L)"
        >
          <span className="inline-block h-[7px] w-[7px] rounded-full bg-bad" />
          {starting ? "Starting…" : "Go live"}
          <kbd className="ml-0.5 rounded border border-white/30 px-1 text-[9.5px] font-bold opacity-80">L</kbd>
        </button>
      </div>
    );
  }

  const forced = (state?.live?.forced_topology ?? null) as Topology | null;
  const w = state ? waveAt(state, t) : null;
  const pending = !!forced && w?.topology !== forced;
  const offered = new Set((w?.arms ?? []).filter((a) => a.offered).map((a) => a.topology));
  return (
    <div className={`flex flex-wrap items-center gap-2 ${className ?? ""}`}>
      <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted">
        <span className="inline-block h-[7px] w-[7px] rounded-full bg-bad pulse" />
        Topology
      </span>
      <div className="seg" role="group" aria-label="Force coordination topology">
        {TOPOS.map((o) => {
          const on = forced === o.id;
          const ineligible = o.id != null && w != null && !offered.has(o.id);
          return (
            <button
              key={o.short}
              className={on ? "on" : ""}
              style={{ fontFamily: "var(--font-sans)", opacity: ineligible ? 0.55 : 1 }}
              onClick={() => void forceTopology(o.id)}
              title={`${o.id ? `Force ${topoLabel(o.id)}` : "Let SAMG's policy choose"} from the next wave (key ${o.key})${
                ineligible ? " · not feasible for the current wave; the server falls back if it stays infeasible" : ""
              }`}
            >
              {o.short}
            </button>
          );
        })}
      </div>
      <span className="text-[11px] text-ink2">
        {w ? (
          <>
            wave {w.number}: <b>{topoLabel(w.topology ?? "none")}</b>
            {w.policy === "P0-OPERATOR" ? <span className="text-warn"> (operator)</span> : null}
            {pending ? <span className="text-warn"> · {topoLabel(forced!)} from the next wave</span> : null}
          </>
        ) : (
          "waiting for the first wave"
        )}
      </span>
      <button
        className="btn"
        onClick={() => void api.control("pause").catch(() => undefined).then(() => switchToReplay())}
        title="Pause the live session and return to the recorded replay"
      >
        Back to replay
      </button>
    </div>
  );
}
