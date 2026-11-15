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

type Dir = "min" | "max" | null;
type M = Record<string, unknown>;
interface Row {
  label: string;
  key: string;
  fmt: (v: unknown, m: M) => string;
  dir: Dir;
  hint?: string;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const secs = (v: unknown) => (num(v) == null ? "—" : `${num(v)!.toFixed(1)} s`);
const count = (v: unknown) => (num(v) == null ? "—" : `${v}`);

// Grouped so the page reads as an argument: what SAMG guarantees, what that costs, and how it coordinates.
const GROUPS: { id: string; title: string; sub: string; tone: "ok" | "warn" | "ink"; rows: Row[] }[] = [
  {
    id: "trust",
    title: "Trust & integrity",
    sub: "what actually got done, checked against ground truth",
    tone: "ok",
    rows: [
      { label: "Orders truly fulfilled", key: "orders_truly_fulfilled", fmt: (v, m) => `${v} / ${m.orders_total}`, dir: "max" },
      { label: "Orders shipped incomplete", key: "orders_shipped_incomplete", fmt: count, dir: "min" },
      { label: "False reports accepted", key: "false_claims_accepted", fmt: (v, m) => `${v} / ${m.false_claims}`, dir: "min" },
      { label: "Phantom tasks (believed done, not done)", key: "corrupted_tasks", fmt: count, dir: "min" },
    ],
  },
  {
    id: "cost",
    title: "Price of verification",
    sub: "time spent checking claims and re-planning rejected work",
    tone: "warn",
    rows: [
      { label: "Average fulfilment", key: "avg_fulfilment_s", fmt: secs, dir: "min" },
      { label: "Average task latency", key: "avg_task_latency_s", fmt: secs, dir: "min" },
      { label: "Makespan", key: "makespan_s", fmt: secs, dir: "min" },
      { label: "Travel", key: "travel_m", fmt: (v) => (num(v) == null ? "—" : `${num(v)!.toFixed(0)} m`), dir: "min" },
      { label: "Robot utilization", key: "robot_utilization", fmt: (v) => (num(v) == null ? "—" : `${(num(v)! * 100).toFixed(1)}%`), dir: null },
    ],
  },
  {
    id: "coord",
    title: "Coordination & resilience",
    sub: "how the fleet talks and recovers",
    tone: "ink",
    rows: [
      { label: "Task failures", key: "task_failures", fmt: count, dir: "min" },
      { label: "Congestion events", key: "congestion_events", fmt: count, dir: "min" },
      { label: "Message retransmissions", key: "retransmissions", fmt: count, dir: "min" },
      { label: "Handoff hops", key: "handoff_hops", fmt: count, dir: "min" },
      { label: "Re-plans", key: "replans", fmt: count, dir: null },
    ],
  },
];

function better(dir: Dir, a: unknown, b: unknown): Mode | null {
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
  const curPreset = index?.presets.find((p) => p.preset === preset);
  const attackPreset = index?.presets.find((p) => p.preset !== preset && p.injections.some((i) => /malicious/i.test(i)));
  const pct = end > 0 ? Math.min(100, (t / end) * 100) : 0;
  const S = meta?.metrics.samg;
  const B = meta?.metrics.baseline;

  return (
    <main className="mx-auto flex max-w-[1600px] flex-col gap-2.5 p-3.5">
      {/* Header — same brand block and pill styling as the control center */}
      <header className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-2xl border border-line bg-panel px-4 py-2 shadow-xs">
        <Link href="/" className="flex flex-none items-center gap-3" title="Back to the control center">
          <div className="grid h-[32px] w-[32px] place-items-center rounded-xl bg-ink shadow-xs">
            <svg width="18" height="18" viewBox="0 0 18 18">
              <path d="M3 4h12L3 14h12" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <div className="text-[14px] font-extrabold leading-tight tracking-[0.14em] text-ink">ZERO-HOUR</div>
            <div className="text-[9.5px] font-semibold tracking-[0.18em] text-muted">SAMG VS CONVENTIONAL</div>
          </div>
        </Link>

        <div className="min-w-0">
          <h1 className="text-[13px] font-bold text-ink">
            <span className="text-samg">SAMG</span> <span className="font-normal text-muted">vs</span> Conventional dispatch
          </h1>
          <div className="text-[11px] text-muted">same seed · same orders · same robots · same faults</div>
        </div>

        <nav className="flex flex-none items-center gap-1.5 text-[11.5px] font-semibold">
          <Link className="rounded-full px-3 py-1 text-ink2 transition-colors hover:bg-panel2 hover:text-ink" href="/">
            Control center
          </Link>
          <Link className="rounded-full px-3 py-1 text-ink2 transition-colors hover:bg-panel2 hover:text-ink" href="/compare">
            Compare
          </Link>
          <Link className="rounded-full px-3 py-1 text-ink2 transition-colors hover:bg-panel2 hover:text-ink" href="/replays">
            Replays
          </Link>
        </nav>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <span className="cap" id="preset-label">Mission</span>
          <select
            aria-labelledby="preset-label"
            className="rounded-full border border-line2 bg-panel px-3 py-1 text-[12px] font-semibold text-ink shadow-xs"
            value={preset ?? ""}
            onChange={(e) => choose(e.target.value)}
          >
            {index?.presets.map((p) => (
              <option key={p.preset} value={p.preset}>
                {p.label} (seed {p.seed})
              </option>
            ))}
          </select>
        </div>
      </header>

      {err && <p className="rounded-2xl border border-bad/30 bg-bad-bg px-4 py-3 text-[12px] font-semibold text-bad">{err}</p>}

      {/* Verdict + KPIs */}
      {S && B && meta ? (
        <>
          <Verdict S={S} B={B} attack={attackPreset} onAttack={() => attackPreset && choose(attackPreset.preset)} />
          <section className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi
              label="Orders truly fulfilled"
              hint="verified against simulator ground truth"
              dir="max"
              a={S.orders_truly_fulfilled}
              b={B.orders_truly_fulfilled}
              fmt={(v) => `${v}/${S.orders_total}`}
              unit="order"
            />
            <Kpi
              label="False reports accepted"
              hint={`out of ${num(S.false_claims) ?? 0} lying completion reports`}
              dir="min"
              a={S.false_claims_accepted}
              b={B.false_claims_accepted}
              fmt={(v) => `${v}`}
              unit="report"
            />
            <Kpi
              label="Orders shipped incomplete"
              hint="customer receives a short order"
              dir="min"
              a={S.orders_shipped_incomplete}
              b={B.orders_shipped_incomplete}
              fmt={(v) => `${v}`}
              unit="order"
            />
            <Kpi
              label="Phantom tasks"
              hint="system believes done, never happened"
              dir="min"
              a={S.corrupted_tasks}
              b={B.corrupted_tasks}
              fmt={(v) => `${v}`}
              unit="task"
            />
          </section>
        </>
      ) : (
        !err && (
          <section className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-[112px] animate-pulse rounded-2xl border border-line bg-panel" />
            ))}
          </section>
        )
      )}

      {/* Transport bar — one clock drives both scenes */}
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-panel px-4 py-2 shadow-xs">
        <button className="btn primary" onClick={() => st.togglePlay()} disabled={!end}>
          {playing ? "❚❚ Pause" : "▶ Play"}
        </button>
        <button className="btn" onClick={() => st.seek(0)} disabled={!end}>
          ↺ Restart
        </button>
        <div className="seg" role="group" aria-label="Playback speed">
          {[1, 2, 4, 8, 16].map((x) => (
            <button key={x} className={speed === x ? "on" : ""} onClick={() => st.setSpeed(x)}>
              {x}×
            </button>
          ))}
        </div>
        <input
          type="range"
          aria-label="Seek"
          className="min-w-[160px] flex-1 accent-[var(--samg)]"
          min={0}
          max={end || 1}
          step={0.1}
          value={Math.min(t, end || 1)}
          onChange={(e) => st.seek(Number(e.target.value))}
          disabled={!end}
        />
        <span className="mono flex-none text-[12px] font-semibold text-ink">
          {fmtS(t)} <span className="text-muted">/ {fmtS(end)}</span>
        </span>
        <span className="sr-only">{pct.toFixed(0)}% played</span>
        {curPreset && curPreset.injections.length > 0 && (
          <span className="flex-none rounded-full bg-warn-bg px-2.5 py-0.5 text-[11px] font-bold text-warn" title={curPreset.injections.join("; ")}>
            ⚡ {curPreset.injections.length} fault{curPreset.injections.length > 1 ? "s" : ""} injected
          </span>
        )}
      </div>

      {/* Two scenes */}
      <section className="grid gap-2.5 md:grid-cols-2">
        {MODES.map((m) => {
          const caps = meta?.capabilities[m];
          const isSamg = m === "samg";
          return (
            <div key={m} className="zh-card" style={{ boxShadow: `inset 0 3px 0 ${isSamg ? "var(--samg)" : "var(--faint)"}` }}>
              <div className="zh-ch flex-wrap !gap-2">
                <span className={`zh-dot ${isSamg ? "bg-samg" : "bg-faint"}`} />
                <h2 className={isSamg ? "!text-samg" : ""}>{TITLE[m]}</h2>
                {caps && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Chip on tone={isSamg ? "samg" : "plain"}>{caps.coordination}</Chip>
                    <Chip on={isSamg} tone={isSamg ? "samg" : "plain"}>Topology: {caps.topology_selection}</Chip>
                    <Chip on tone={isSamg ? "samg" : "plain"}>Allocator: {caps.allocator}</Chip>
                    <Chip on={caps.learning} tone="samg">LinUCB {caps.learning ? "active" : "off"}</Chip>
                    <Chip on={caps.witness} tone="sec">Witness {caps.witness ? "active" : "off"}</Chip>
                    <Chip on={caps.evidence_gate} tone="sec">Evidence gate {caps.evidence_gate ? "active" : "off"}</Chip>
                  </div>
                )}
              </div>
              <div className="h-[48vh] min-h-[300px] bg-panel2">
                {states[m] ? (
                  <SceneCanvas state={states[m]!} />
                ) : (
                  <div className="grid h-full place-items-center">
                    <span className="cap">Loading…</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </section>

      {/* How each system treats a robot's "done" report */}
      <HowItWorks />

      {/* Grouped metric comparison */}
      {S && B && meta && (
        <section className="grid gap-2.5 lg:grid-cols-3">
          {GROUPS.map((g) => (
            <div key={g.id} className="zh-card">
              <div className="zh-ch">
                <span className="zh-dot" style={{ background: `var(--${g.tone === "ink" ? "ink2" : g.tone})` }} />
                <h2>{g.title}</h2>
                <span className="sub">{g.sub}</span>
              </div>
              <div className="flex flex-col gap-3 px-4 py-3">
                {g.rows.map((r) => (
                  <BarRow key={r.key} row={r} S={S} B={B} />
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      {/* Multi-seed evidence */}
      <Evidence />

      {meta && (
        <p className="mono rounded-2xl border border-line bg-panel px-4 py-2.5 text-[10.5px] leading-relaxed text-muted">
          This mission: seed {meta.manifest.seed} · faults: {meta.manifest.injections.join("; ") || "none"} · simulator model{" "}
          {meta.manifest.model} · commit {meta.manifest.git_commit?.slice(0, 8) ?? "unknown"} · exported {meta.manifest.generated_at}.
          One seed is an illustration, not a statistical result. Baseline task state is what its controller believed (claims); both
          columns are scored against simulator ground truth.
        </p>
      )}
    </main>
  );
}

/* ---------- pieces ---------- */

function Verdict({ S, B, attack, onAttack }: { S: M; B: M; attack?: { label: string }; onAttack: () => void }) {
  const fc = num(S.false_claims) ?? 0;
  const faS = num(S.false_claims_accepted) ?? 0;
  const faB = num(B.false_claims_accepted) ?? 0;
  const dF = (num(S.avg_fulfilment_s) ?? 0) - (num(B.avg_fulfilment_s) ?? 0);
  const slower = dF > 0.05;
  const total = num(S.orders_total) ?? 0;

  if (fc > 0) {
    const trustWin = faB > faS;
    return (
      <section className="flex flex-wrap items-center gap-4 rounded-2xl border border-ok/30 bg-ok-bg px-5 py-3.5 shadow-xs">
        <div className="grid h-10 w-10 flex-none place-items-center rounded-xl bg-ok text-[18px] text-white">✓</div>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-bold text-ink">
            {trustWin ? (
              <>
                Robots lied {fc}× in this mission. The conventional dispatcher believed{" "}
                <span className="text-bad">{faB}</span>; SAMG rejected <span className="text-ok">{fc - faS}</span>.
              </>
            ) : (
              <>
                Robots lied {fc}× in this mission. SAMG accepted {faS}, conventional accepted {faB}.
              </>
            )}
          </div>
          <div className="mt-0.5 text-[12px] text-ink2">
            SAMG truly fulfilled <b>{String(S.orders_truly_fulfilled)}/{total}</b> orders vs <b>{String(B.orders_truly_fulfilled)}/{total}</b>
            {num(B.orders_shipped_incomplete) ? <> — the baseline shipped {String(B.orders_shipped_incomplete)} incomplete and never knew</> : null}.{" "}
            {slower ? (
              <span className="text-muted">
                The price: {dF.toFixed(1)} s longer average fulfilment, spent re-planning the work it refused to trust.
              </span>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="flex flex-wrap items-center gap-4 rounded-2xl border border-line bg-panel px-5 py-3.5 shadow-xs">
      <div className="grid h-10 w-10 flex-none place-items-center rounded-xl bg-panel2 text-[18px] text-muted">=</div>
      <div className="min-w-0 flex-1">
        <div className="text-[15px] font-bold text-ink">No robot lied in this mission, so both systems report the truth.</div>
        <div className="mt-0.5 text-[12px] text-ink2">
          Both truly fulfil {String(S.orders_truly_fulfilled)}/{total} orders.{" "}
          {slower
            ? `Without lies to catch, the greedy baseline is ${dF.toFixed(1)} s faster on average — SAMG's checks are overhead here.`
            : "Speed is on par."}{" "}
          SAMG&apos;s advantage appears when reports can&apos;t be trusted.
        </div>
      </div>
      {attack && (
        <button className="btn primary flex-none" onClick={onAttack}>
          Watch the attack mission →
        </button>
      )}
    </section>
  );
}

function Kpi({
  label,
  hint,
  dir,
  a,
  b,
  fmt,
  unit,
}: {
  label: string;
  hint: string;
  dir: Dir;
  a: unknown;
  b: unknown;
  fmt: (v: unknown) => string;
  unit: string;
}) {
  const win = better(dir, a, b);
  const d = Math.abs((num(a) ?? 0) - (num(b) ?? 0));
  const tag =
    win === "samg"
      ? { cls: "bg-ok-bg text-ok", txt: `SAMG ${dir === "max" ? "+" : "−"}${d} ${unit}${d === 1 ? "" : "s"}` }
      : win === "baseline"
        ? { cls: "bg-warn-bg text-warn", txt: `Baseline ${dir === "max" ? "+" : "−"}${d}` }
        : { cls: "bg-panel2 text-muted", txt: "Tie" };
  return (
    <div
      className="flex flex-col gap-2 rounded-2xl border border-line bg-panel px-4 py-3 shadow-xs"
      style={win === "samg" ? { boxShadow: "inset 3px 0 0 var(--ok)" } : undefined}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="cap">{label}</div>
          <div className="text-[10.5px] text-faint">{hint}</div>
        </div>
        <span className={`flex-none rounded-full px-2 py-0.5 text-[10.5px] font-bold ${tag.cls}`}>{tag.txt}</span>
      </div>
      <div className="flex items-end gap-4">
        <div>
          <div className="text-[9px] font-bold uppercase tracking-wider text-samg">SAMG</div>
          <div className="mono text-[28px] font-bold leading-none text-ink">{fmt(a)}</div>
        </div>
        <div className="pb-0.5">
          <div className="text-[9px] font-bold uppercase tracking-wider text-muted">Conventional</div>
          <div className={`mono text-[18px] font-semibold leading-none ${win === "samg" ? "text-bad" : "text-ink2"}`}>{fmt(b)}</div>
        </div>
      </div>
    </div>
  );
}

function BarRow({ row, S, B }: { row: Row; S: M; B: M }) {
  const a = S[row.key];
  const b = B[row.key];
  const win = better(row.dir, a, b);
  const max = Math.max(num(a) ?? 0, num(b) ?? 0) || 1;
  const bar = (mode: Mode, v: unknown) => {
    const w = ((num(v) ?? 0) / max) * 100;
    const isWin = win === mode;
    const color = mode === "samg" ? "var(--samg)" : "var(--faint)";
    return (
      <div className="grid grid-cols-[78px_minmax(0,1fr)_76px] items-center gap-2">
        <span className={`text-[10.5px] font-semibold ${mode === "samg" ? "text-samg" : "text-muted"}`}>
          {mode === "samg" ? "SAMG" : "Conventional"}
        </span>
        <div className="h-2 overflow-hidden rounded-full bg-line/60">
          <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${Math.max(w, num(v) ? 2 : 0)}%`, background: color }} />
        </div>
        <span
          className={`mono justify-self-end rounded-md px-1.5 text-[11.5px] ${
            isWin ? "bg-ok-bg font-bold text-ok" : "text-ink2"
          }`}
        >
          {row.fmt(v, mode === "samg" ? S : B)}
        </span>
      </div>
    );
  };
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[12px] font-medium text-ink">{row.label}</span>
        <span className={`text-[10px] font-bold ${win === "samg" ? "text-ok" : win === "baseline" ? "text-warn" : "text-faint"}`}>
          {win === "samg" ? "▲ SAMG" : win === "baseline" ? "▲ Conventional" : row.dir ? "tie" : "context"}
        </span>
      </div>
      <div className="flex flex-col gap-1">
        {bar("samg", a)}
        {bar("baseline", b)}
      </div>
    </div>
  );
}

function Step({ children, tone }: { children: React.ReactNode; tone: "samg" | "sec" | "plain" | "bad" | "ok" }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
        tone === "samg"
          ? "border-samg/30 bg-samg-bg text-samg"
          : tone === "sec"
            ? "border-sec/30 bg-sec-bg text-sec"
            : tone === "bad"
              ? "border-bad/30 bg-bad-bg text-bad"
              : tone === "ok"
                ? "border-ok/30 bg-ok-bg text-ok"
                : "border-line2 bg-panel text-ink2"
      }`}
    >
      {children}
    </span>
  );
}
const Arrow = () => <span className="text-faint">→</span>;

function HowItWorks() {
  return (
    <section className="zh-card">
      <div className="zh-ch">
        <h2>Why the numbers differ</h2>
        <span className="sub">what happens when a robot reports &ldquo;task done&rdquo;</span>
      </div>
      <div className="grid gap-3 px-4 py-3 md:grid-cols-2">
        <div className="flex flex-col gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-muted">Conventional dispatch</span>
          <div className="flex flex-wrap items-center gap-1.5">
            <Step tone="plain">Robot: &ldquo;done&rdquo;</Step>
            <Arrow />
            <Step tone="plain">Marked done</Step>
            <Arrow />
            <Step tone="bad">Lie goes unnoticed → order ships short</Step>
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-samg">SAMG</span>
          <div className="flex flex-wrap items-center gap-1.5">
            <Step tone="samg">Signed claim</Step>
            <Arrow />
            <Step tone="sec">Independent witness</Step>
            <Arrow />
            <Step tone="sec">Evidence gate</Step>
            <Arrow />
            <Step tone="ok">Admit, or reject &amp; re-plan</Step>
          </div>
        </div>
      </div>
    </section>
  );
}

// Recorded 30-seed results (docs/RESULTS_BASELINE.md, R16). Copied verbatim from that report; not computed here.
function Evidence() {
  return (
    <section className="zh-card">
      <div className="zh-ch">
        <h2>Beyond one seed</h2>
        <span className="sub">30 seeds per scenario, paired · docs/RESULTS_BASELINE.md (R16)</span>
      </div>
      <div className="grid gap-2.5 px-4 py-3 md:grid-cols-3">
        <div className="rounded-xl border border-ok/30 bg-ok-bg px-3.5 py-3">
          <div className="cap !text-ok">Under malicious reports (W5)</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="mono text-[26px] font-bold text-ok">+28.6</span>
            <span className="text-[12px] font-semibold text-ink">pts orders truly fulfilled</span>
          </div>
          <div className="mt-1 text-[11.5px] text-ink2">
            SAMG 100% vs conventional 71.4%. Conventional accepts 2/2 false claims per run; SAMG accepts 0. Significant (95% CI excludes 0).
          </div>
        </div>
        <div className="rounded-xl border border-line bg-panel2 px-3.5 py-3">
          <div className="cap">Under communication failure (W4)</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="mono text-[26px] font-bold text-ink">+3.2</span>
            <span className="text-[12px] font-semibold text-ink">pts truly fulfilled</span>
          </div>
          <div className="mt-1 text-[11.5px] text-ink2">SAMG 100% vs 96.8%, at +26 s average fulfilment.</div>
        </div>
        <div className="rounded-xl border border-warn/30 bg-warn-bg px-3.5 py-3">
          <div className="cap !text-warn">The trade-off</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="mono text-[26px] font-bold text-warn">+13.6 s</span>
            <span className="text-[12px] font-semibold text-ink">avg fulfilment, normal load</span>
          </div>
          <div className="mt-1 text-[11.5px] text-ink2">
            With no attacks, the travel-aware greedy baseline is faster. Under overload SAMG can fail to plan (W2); admission control is
            queued as a fix.
          </div>
        </div>
      </div>
    </section>
  );
}

const CHIP_TONE = {
  samg: "border-samg/30 bg-samg-bg text-samg",
  sec: "border-sec/30 bg-sec-bg text-sec",
  plain: "border-line2 bg-panel text-ink2",
} as const;

function Chip({ on, tone = "plain", children }: { on: boolean; tone?: keyof typeof CHIP_TONE; children: React.ReactNode }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-0.5 text-[10.5px] font-semibold ${
        on ? CHIP_TONE[tone] : "border-dashed border-line2 bg-panel2 text-faint line-through"
      }`}
    >
      {children}
    </span>
  );
}
