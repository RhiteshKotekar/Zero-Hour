"use client";
// /compare-replay — SAMG vs the conventional baseline (D042), side by side, on the identical recorded mission
// (same seed, orders, robots, layout and fault injections). Both 3D scenes follow one replay clock.
// Data: web/public/replays/compare/*, written by scripts/export_compare_replays.py. Every number on this page
// comes from those files; nothing is computed or estimated here. A single seed is an illustration — multi-seed
// results are reported separately.
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { fmtS } from "@/lib/derive";
import { useClockDriver, useSimT, useStore } from "@/lib/store";
import type { TwinState } from "@/lib/types";

const SceneCanvas = dynamic(() => import("./SceneCanvas"), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center"><span className="cap">Loading 3D…</span></div>,
});

type Mode = "samg" | "baseline";
const MODES: Mode[] = ["samg", "baseline"];
const TITLE: Record<Mode, string> = { samg: "SAMG", baseline: "Conventional baseline" };
const BASE = "/replays/compare";

interface Caps {
  coordination: string;
  topology_selection: string;
  allocator: string;
  witness: boolean;
  evidence_gate: boolean;
  learning: boolean;
}
interface MetricsFile {
  manifest: { preset: string; label: string; seed: number; injections: string[]; model: string;
    git_commit: string | null; generated_at: string };
  capabilities: Record<Mode, Caps>;
  metrics: Record<Mode, Record<string, unknown>>;
}
interface IndexFile { model: string; presets: { preset: string; label: string; seed: number; injections: string[] }[] }

// label, metric key, formatter, which direction is better (null = context-dependent, no marking)
const ROWS: [string, string, (v: unknown, m: Record<string, unknown>) => string, "min" | "max" | null][] = [
  ["Orders truly fulfilled", "orders_truly_fulfilled", (v, m) => `${v} / ${m.orders_total}`, "max"],
  ["Orders shipped incomplete", "orders_shipped_incomplete", (v) => `${v}`, "min"],
  ["False claims accepted", "false_claims_accepted", (v, m) => `${v} / ${m.false_claims}`, "min"],
  ["Tasks believed done but not done", "corrupted_tasks", (v) => `${v}`, "min"],
  ["Average fulfilment", "avg_fulfilment_s", (v) => (v == null ? "—" : `${Number(v).toFixed(1)} s`), "min"],
  ["Average task latency", "avg_task_latency_s", (v) => (v == null ? "—" : `${Number(v).toFixed(1)} s`), "min"],
  ["Makespan", "makespan_s", (v) => (v == null ? "—" : `${Number(v).toFixed(1)} s`), "min"],
  ["Robot utilization", "robot_utilization", (v) => (v == null ? "—" : `${(Number(v) * 100).toFixed(1)}%`), null],
  ["Travel", "travel_m", (v) => (v == null ? "—" : `${Number(v).toFixed(0)} m`), "min"],
  ["Congestion events", "congestion_events", (v) => `${v}`, "min"],
  ["Task failures", "task_failures", (v) => `${v}`, "min"],
  ["Message retransmissions", "retransmissions", (v) => `${v}`, "min"],
  ["Handoff hops", "handoff_hops", (v) => `${v}`, "min"],
  ["Re-plans", "replans", (v) => `${v}`, null],
];

function better(dir: "min" | "max" | null, a: unknown, b: unknown): Mode | null {
  if (dir === null || typeof a !== "number" || typeof b !== "number" || a === b) return null;
  return (dir === "min" ? a < b : a > b) ? "samg" : "baseline";
}

export default function CompareReplayPage() {
  useClockDriver(10);
  const t = useSimT();
  const playing = useStore((s) => s.clock.playing);
  const speed = useStore((s) => s.clock.speed);
  const [index, setIndex] = useState<IndexFile | null>(null);
  const [preset, setPreset] = useState<string | null>(null);
  const [states, setStates] = useState<Partial<Record<Mode, TwinState>>>({});
  const [meta, setMeta] = useState<MetricsFile | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE}/index.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`index.json: HTTP ${r.status}`))))
      .then((j: IndexFile) => {
        setIndex(j);
        setPreset(j.presets.find((p) => p.preset === "judge_demo")?.preset ?? j.presets[0]?.preset ?? null);
      })
      .catch(() => setErr("No exported comparison found. Run: python scripts/export_compare_replays.py"));
  }, []);

  useEffect(() => {
    if (!preset) return;
    let cancelled = false;
    Promise.all([
      ...MODES.map((m) => fetch(`${BASE}/${preset}.${m}.json`).then((r) => r.json() as Promise<TwinState>)),
      fetch(`${BASE}/${preset}.metrics.json`).then((r) => r.json() as Promise<MetricsFile>),
    ])
      .then(([samg, baseline, metrics]) => {
        if (cancelled) return;
        const s = samg as TwinState;
        const b = baseline as TwinState;
        setStates({ samg: s, baseline: b });
        setMeta(metrics as MetricsFile);
        // the store's replay clock spans the longer of the two runs; both scenes read it
        const longer = (b.end_s ?? 0) > (s.end_s ?? 0) ? b : s;
        useStore.getState().setState(longer, { mode: "replay", source: "COMPARE · SAMG vs baseline", resetClock: true });
        useStore.getState().play();
      })
      .catch((e) => !cancelled && setErr((e as Error).message));
    return () => {
      cancelled = true;
    };
  }, [preset]);

  // switching mission clears the previous pair before the new one loads
  const choose = (p: string) => {
    setStates({});
    setMeta(null);
    setPreset(p);
  };

  const end = useMemo(() => Math.max(states.samg?.end_s ?? 0, states.baseline?.end_s ?? 0), [states]);
  const st = useStore.getState();

  return (
    <main className="mx-auto max-w-[1600px] p-3">
      <header className="mb-3 flex flex-wrap items-center gap-3 rounded-[10px] border border-line bg-panel px-4 py-2.5">
        <h1 className="text-[15px] font-semibold">SAMG vs conventional baseline — side-by-side replay</h1>
        <span className="cap">same seed · same orders · same robots · same faults</span>
        <div className="ml-auto flex items-center gap-2">
          <label className="cap" htmlFor="preset">Mission</label>
          <select id="preset" className="rounded border border-line bg-bg px-2 py-1 text-[12px]"
            value={preset ?? ""} onChange={(e) => choose(e.target.value)}>
            {index?.presets.map((p) => (
              <option key={p.preset} value={p.preset}>{p.label} (seed {p.seed})</option>
            ))}
          </select>
          <button className="rounded border border-line px-2 py-1 text-[12px]" onClick={() => st.togglePlay()}>
            {playing ? "Pause" : "Play"}
          </button>
          <button className="rounded border border-line px-2 py-1 text-[12px]" onClick={() => st.seek(0)}>Restart</button>
          <select className="rounded border border-line bg-bg px-2 py-1 text-[12px]" value={speed}
            onChange={(e) => st.setSpeed(Number(e.target.value))} aria-label="speed">
            {[1, 2, 4, 8, 16].map((x) => <option key={x} value={x}>{x}×</option>)}
          </select>
          <span className="mono text-[12px]">{fmtS(t)} / {fmtS(end)}</span>
          <Link className="text-[12px] underline" href="/">Control center</Link>
        </div>
      </header>

      {err && <p className="mb-3 rounded border border-line bg-panel p-3 text-[12px]">{err}</p>}

      <section className="grid gap-3 md:grid-cols-2">
        {MODES.map((m) => {
          const caps = meta?.capabilities[m];
          return (
            <div key={m} className="flex flex-col overflow-hidden rounded-[10px] border border-line bg-panel">
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
                <span className="text-[13px] font-semibold">{TITLE[m]}</span>
                {caps && (
                  <>
                    <Chip on>{caps.coordination}</Chip>
                    <Chip on={m === "samg"}>Topology: {caps.topology_selection}</Chip>
                    <Chip on>Allocator: {caps.allocator}</Chip>
                    <Chip on={caps.learning}>LinUCB {caps.learning ? "ACTIVE" : "DISABLED"}</Chip>
                    <Chip on={caps.witness}>Witness {caps.witness ? "ACTIVE" : "DISABLED"}</Chip>
                    <Chip on={caps.evidence_gate}>Evidence gate {caps.evidence_gate ? "ACTIVE" : "DISABLED"}</Chip>
                  </>
                )}
              </div>
              <div className="h-[52vh] min-h-[320px]">
                {states[m] ? <SceneCanvas state={states[m]!} /> : (
                  <div className="grid h-full place-items-center"><span className="cap">Loading…</span></div>
                )}
              </div>
            </div>
          );
        })}
      </section>

      {meta && (
        <section className="mt-3 overflow-x-auto rounded-[10px] border border-line bg-panel">
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-line text-left">
                <th className="px-3 py-2">Measured on this mission (one seed)</th>
                <th className="px-3 py-2">SAMG</th>
                <th className="px-3 py-2">Conventional baseline</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map(([label, key, fmt, dir]) => {
                const a = meta.metrics.samg[key];
                const b = meta.metrics.baseline[key];
                const win = better(dir, a, b);
                return (
                  <tr key={key} className="border-b border-line/60">
                    <td className="px-3 py-1.5">{label}</td>
                    <td className={`mono px-3 py-1.5 ${win === "samg" ? "font-semibold" : ""}`}>{fmt(a, meta.metrics.samg)}</td>
                    <td className={`mono px-3 py-1.5 ${win === "baseline" ? "font-semibold" : ""}`}>{fmt(b, meta.metrics.baseline)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mono px-3 py-2 text-[10.5px] text-muted">
            Seed {meta.manifest.seed} · faults: {meta.manifest.injections.join("; ") || "none"} · simulator model{" "}
            {meta.manifest.model} · commit {meta.manifest.git_commit?.slice(0, 8) ?? "unknown"} · exported{" "}
            {meta.manifest.generated_at}. Bold = better on that metric for this one run; a single seed is an
            illustration, not a statistical result. Baseline task state is what its controller believed (claims);
            both columns are scored against simulator ground truth.
          </p>
        </section>
      )}
    </main>
  );
}

function Chip({ on, children }: { on: boolean; children: React.ReactNode }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${on ? "border-line" : "border-line/50 text-muted line-through"}`}>
      {children}
    </span>
  );
}
