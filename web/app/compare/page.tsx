"use client";

// /compare — Material 3 Policy & Topology Comparison Screen
// Evaluates fixed-topology baselines vs adaptive LinUCB on identical warehouse workloads.
import { useEffect, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";
import { OfflineNote } from "@/components/live/SessionDrawer";
import { topoLabel } from "@/lib/derive";
import { useStore } from "@/lib/store";

type Dir = "max" | "min" | null;
const METRIC: Record<string, { label: string; dir: Dir; fmt: (x: number) => string }> = {
  order_completion_rate: { label: "Order Completion", dir: "max", fmt: (x) => `${(x * 100).toFixed(0)}%` },
  avg_fulfilment_s: { label: "Avg Fulfilment", dir: "min", fmt: (x) => `${x.toFixed(1)}s` },
  robot_utilization: { label: "Robot Utilization", dir: null, fmt: (x) => `${(x * 100).toFixed(1)}%` },
  congestion_s: { label: "Congestion Wait", dir: "min", fmt: (x) => `${x.toFixed(1)}s` },
  coordination_cost: { label: "Coordination Cost", dir: "min", fmt: (x) => x.toFixed(2) },
  reward_first_wave: { label: "Secure Reward", dir: "max", fmt: (x) => x.toFixed(3) },
  security_violations: { label: "Security Violations", dir: "min", fmt: (x) => x.toFixed(1) },
  travel_m: { label: "AMR Travel", dir: "min", fmt: (x) => `${x.toFixed(0)}m` },
};
const fmtStd = (m: string, x: number) => (METRIC[m]?.fmt ?? ((v: number) => v.toFixed(3)))(x);

export default function ComparePage() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [res, setRes] = useState<api.CompareResult | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [seeds, setSeeds] = useState("");
  const [cpsat, setCpsat] = useState(true);

  const theme = useStore((s) => s.theme);
  const toggleTheme = useStore((s) => s.toggleTheme);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.classList.toggle("dark", theme === "dark");
    }
  }, [theme]);

  const ping = () =>
    api
      .getHealth()
      .then(() => setOnline(true))
      .catch(() => setOnline(false));
  useEffect(() => {
    void ping();
  }, []);
  useEffect(() => {
    if (busy == null) return;
    const id = window.setInterval(() => setElapsed((Date.now() - busy) / 1000), 200);
    return () => window.clearInterval(id);
  }, [busy]);

  const run = async () => {
    setErr(null);
    setBusy(Date.now());
    setElapsed(0);
    try {
      const s = seeds
        .split(/[ ,]+/)
        .filter(Boolean)
        .map(Number)
        .filter((n) => Number.isFinite(n));
      setRes(await api.compare({ seeds: s.length ? s : undefined, use_cpsat: cpsat }));
      setOnline(true);
    } catch (e) {
      setErr((e as Error).message);
      if ((e as api.ApiError).status === 0) setOnline(false);
    } finally {
      setBusy(null);
    }
  };

  const eligible = (r: api.CompareRow) => r.infeasible === 0;
  const best = (m: string): string | null => {
    const d = METRIC[m]?.dir;
    if (!res || !d) return null;
    const cands = res.policies.filter((r) => eligible(r) && r.summary[m]?.mean != null);
    if (cands.length < 2) return null;
    cands.sort((a, b) => (d === "max" ? b.summary[m].mean! - a.summary[m].mean! : a.summary[m].mean! - b.summary[m].mean!));
    if (cands[0].summary[m].mean === cands[1].summary[m].mean) return null;
    return cands[0].policy;
  };

  return (
    <main className="min-h-screen bg-bg text-ink p-6 transition-colors">
      <div className="mx-auto max-w-7xl space-y-6">
        {/* Top App Bar Header */}
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-3xl border border-line bg-panel p-5 shadow-sm">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="flex items-center gap-2 rounded-2xl border border-line bg-panel2 px-4 py-2 text-sm font-bold text-ink hover:bg-panel transition-all active:scale-95 shadow-xs"
            >
              ← Mission Control
            </Link>
            <div>
              <h1 className="text-xl font-black tracking-tight text-ink">POLICY & TOPOLOGY BENCHMARK</h1>
              <div className="text-xs font-semibold text-muted">Fixed-topology baselines vs adaptive LinUCB on identical warehouse workloads</div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <input
              className="mono w-44 rounded-2xl border border-line bg-panel2 px-3 py-2 text-xs font-bold placeholder:text-muted focus:outline-none focus:border-accent"
              placeholder="Seeds (e.g. 42, 101)"
              value={seeds}
              onChange={(e) => setSeeds(e.target.value)}
            />
            <label className="flex items-center gap-2 rounded-2xl border border-line bg-panel2 px-3.5 py-2 text-xs font-bold text-ink cursor-pointer hover:bg-panel">
              <input
                type="checkbox"
                checked={cpsat}
                onChange={(e) => setCpsat(e.target.checked)}
                className="accent-accent h-4 w-4 rounded"
              />
              CP-SAT
            </label>

            {/* Dark Mode Toggle */}
            <button
              onClick={toggleTheme}
              className="flex h-10 w-10 items-center justify-center rounded-2xl border border-line bg-panel2 text-ink hover:bg-panel transition-all active:scale-95"
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

            <button
              className="flex items-center gap-2 rounded-2xl bg-accent px-5 py-2.5 text-xs font-black text-white shadow-md hover:bg-accent-hover transition-all active:scale-95 disabled:opacity-50"
              disabled={busy != null || online === false}
              onClick={run}
            >
              {busy != null ? (
                <>
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  Running ({elapsed.toFixed(0)}s)…
                </>
              ) : res ? (
                "Re-run Benchmark"
              ) : (
                "Run Comparison"
              )}
            </button>
          </div>
        </header>

        {online === false && (
          <div>
            <OfflineNote onRetry={ping} />
          </div>
        )}

        {busy != null && (
          <div className="rounded-3xl border border-line bg-panel p-6 shadow-sm">
            <div className="flex items-center gap-3 text-sm font-bold text-ink">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              Running every coordination policy through the simulation pipeline… <span className="mono font-black text-accent">{elapsed.toFixed(0)}s</span>
            </div>
            <div className="mt-2 text-xs text-muted font-medium">
              Each policy arm is evaluated on identical seeds. Adaptive LinUCB learns online to pick the optimal topology for the workload.
            </div>
          </div>
        )}

        {err && (
          <div className="rounded-3xl border border-bad/40 bg-bad-bg p-4 text-xs font-bold text-bad">
            {err}
          </div>
        )}

        {/* Comparison Table */}
        {res && (
          <section className="rounded-3xl border border-line bg-panel shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="border-b border-line bg-panel2 text-left">
                    <th className="px-5 py-3.5 text-xs font-black uppercase tracking-wider text-muted">Policy Arm</th>
                    <th className="px-5 py-3.5 text-xs font-black uppercase tracking-wider text-muted">Topologies Selected</th>
                    {res.metrics.map((m) => (
                      <th key={m} className="px-5 py-3.5 text-right text-xs font-black uppercase tracking-wider text-muted">
                        {METRIC[m]?.label ?? m} {METRIC[m]?.dir === "max" ? "↑" : METRIC[m]?.dir === "min" ? "↓" : ""}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {res.policies.map((r) => {
                    const isAdaptive = r.policy === "adaptive";
                    return (
                      <tr
                        key={r.policy}
                        className={`transition-colors hover:bg-panel2/60 ${
                          isAdaptive ? "bg-accent-bg/40 dark:bg-accent-bg/20 font-bold" : ""
                        }`}
                      >
                        <td className="px-5 py-4 align-top">
                          <div className="text-sm font-black text-ink flex items-center gap-2">
                            {r.label}
                            {isAdaptive && (
                              <span className="rounded-md bg-accent px-1.5 py-0.2 text-[10px] font-black text-white">
                                ADAPTIVE
                              </span>
                            )}
                          </div>
                          <div className="mono text-xs text-muted mt-0.5">{r.policy}</div>
                          {!eligible(r) && (
                            <div className="mt-1 text-xs font-bold text-warn">
                              Infeasible on {r.infeasible}/{r.runs.length} seeds
                            </div>
                          )}
                        </td>

                        <td className="px-5 py-4 align-top">
                          {Object.entries(r.topologies).map(([k, n]) => (
                            <div key={k} className="text-xs font-bold text-ink whitespace-nowrap">
                              <span className={k === "not eligible" ? "text-warn" : ""}>{topoLabel(k)}</span>{" "}
                              <span className="mono text-muted font-normal">×{n}</span>
                            </div>
                          ))}
                        </td>

                        {res.metrics.map((m) => {
                          const s = r.summary[m];
                          const isBest = best(m) === r.policy;
                          return (
                            <td key={m} className="px-5 py-4 text-right align-top">
                              {s?.mean == null ? (
                                <span className="text-muted">not measured</span>
                              ) : (
                                <>
                                  <div
                                    className={`mono text-sm font-black ${
                                      isBest
                                        ? "inline-block rounded-lg bg-ok-bg px-2 py-0.5 text-ok border border-ok/30"
                                        : "text-ink"
                                    }`}
                                  >
                                    {(METRIC[m]?.fmt ?? String)(s.mean)}
                                  </div>
                                  <div className="mono text-[11px] text-muted font-semibold mt-0.5">
                                    ± {s.std == null ? "—" : fmtStd(m, s.std)}
                                  </div>
                                </>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="border-t border-line bg-panel2/60 px-6 py-4 text-xs text-muted font-medium">
              <b>Statistical Methodology:</b> {res.note} Highlighted cells indicate the best mean among policies eligible on all seeds. Evaluated over seeds: <span className="mono font-bold text-ink">{res.seeds.join(", ")}</span>.
            </div>
          </section>
        )}

        {!res && busy == null && online !== false && (
          <div className="rounded-3xl border border-line bg-panel p-8 shadow-sm text-center">
            <h3 className="text-base font-black text-ink mb-1">Ready to benchmark warehouse coordination policies</h3>
            <p className="text-xs text-muted font-medium max-w-lg mx-auto mb-5">
              Simulates identical order books, warehouse racks, and AMR fleets across fixed baselines (Hierarchical, Functional Cells, Distributed) and Adaptive LinUCB reinforcement learning.
            </p>
            <button
              onClick={run}
              className="inline-flex items-center gap-2 rounded-2xl bg-accent px-6 py-3 text-xs font-black text-white shadow-md hover:bg-accent-hover transition-all active:scale-95"
            >
              Run Policy Comparison
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
