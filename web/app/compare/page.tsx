"use client";
// /compare — the same orders/layout/fleet/seeds under every policy (samg.twin.compare_policies via POST /api/compare).
// The UI only formats the backend's numbers; "best" is marked on the mean among eligible policies, nothing more.
import { useEffect, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";
import { OfflineNote } from "@/components/live/SessionDrawer";
import { topoLabel } from "@/lib/derive";

type Dir = "max" | "min" | null;
const METRIC: Record<string, { label: string; dir: Dir; fmt: (x: number) => string }> = {
  order_completion_rate: { label: "Order completion", dir: "max", fmt: (x) => `${(x * 100).toFixed(0)}%` },
  avg_fulfilment_s: { label: "Avg fulfilment", dir: "min", fmt: (x) => `${x.toFixed(1)} s` },
  robot_utilization: { label: "Robot utilization", dir: null, fmt: (x) => `${(x * 100).toFixed(1)}%` },
  congestion_s: { label: "Congestion wait", dir: "min", fmt: (x) => `${x.toFixed(1)} s` },
  coordination_cost: { label: "Coordination cost", dir: "min", fmt: (x) => x.toFixed(2) },
  reward_first_wave: { label: "Secure reward (wave 1)", dir: "max", fmt: (x) => x.toFixed(3) },
  security_violations: { label: "Security violations", dir: "min", fmt: (x) => x.toFixed(1) },
  travel_m: { label: "Travel", dir: "min", fmt: (x) => `${x.toFixed(0)} m` },
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
    <main className="mx-auto max-w-[1280px] p-4">
      <header className="flex flex-wrap items-center gap-3 rounded-[10px] border border-line bg-panel px-4 py-2.5">
        <Link href="/" className="btn">
          ← Control center
        </Link>
        <div>
          <h1 className="text-[14px] font-extrabold tracking-[0.12em]">TOPOLOGY COMPARISON</h1>
          <div className="text-[11px] text-muted">Fixed-topology baselines vs adaptive LinUCB on the identical warehouse workload</div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <input
            className="mono w-[150px] rounded-[6px] border border-line2 bg-white px-2 py-1 text-[12px]"
            placeholder="seeds (config default)"
            value={seeds}
            onChange={(e) => setSeeds(e.target.value)}
          />
          <label className="flex items-center gap-1.5 text-[12px]">
            <input type="checkbox" checked={cpsat} onChange={(e) => setCpsat(e.target.checked)} /> CP-SAT
          </label>
          <button className="btn primary" disabled={busy != null || online === false} onClick={run}>
            {busy != null ? "Running…" : res ? "Re-run comparison" : "Run comparison"}
          </button>
        </div>
      </header>

      {online === false && (
        <div className="mt-3">
          <OfflineNote onRetry={ping} />
        </div>
      )}
      {busy != null && (
        <div className="mt-3 rounded-[10px] border border-line bg-panel p-3">
          <div className="flex items-center gap-2 text-[12px]">
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            Running every policy × seed through the full SAMG pipeline… <span className="mono">{elapsed.toFixed(0)} s</span>
          </div>
          <div className="mt-1 text-[11px] text-muted">The first call is slow (every run is simulated; adaptive starts from the trained snapshot); results are cached afterwards.</div>
        </div>
      )}
      {err && <div className="mt-3 rounded-[8px] border border-bad/40 bg-bad-bg px-3 py-2 text-[12px]">{err}</div>}

      {res && (
        <section className="mt-3 overflow-x-auto rounded-[10px] border border-line bg-panel">
          <table className="w-full min-w-[980px] border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-line bg-panel2 text-left">
                <th className="px-3 py-2">
                  <span className="cap">Policy</span>
                </th>
                <th className="px-3 py-2">
                  <span className="cap">Topology chosen (per seed)</span>
                </th>
                {res.metrics.map((m) => (
                  <th key={m} className="px-3 py-2 text-right">
                    <span className="cap">
                      {METRIC[m]?.label ?? m} {METRIC[m]?.dir === "max" ? "↑" : METRIC[m]?.dir === "min" ? "↓" : ""}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {res.policies.map((r) => (
                <tr key={r.policy} className={`border-b border-line last:border-0 ${r.policy === "adaptive" ? "bg-accent-bg/40" : ""}`}>
                  <td className="px-3 py-2 align-top">
                    <div className="font-bold">{r.label}</div>
                    <div className="mono text-[10.5px] text-muted">{r.policy}</div>
                    {!eligible(r) && (
                      <div className="mt-0.5 text-[10.5px] font-semibold text-warn">
                        not eligible on {r.infeasible}/{r.runs.length} seeds
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 align-top">
                    {Object.entries(r.topologies).map(([k, n]) => (
                      <div key={k} className="whitespace-nowrap text-[11.5px]">
                        <span className={k === "not eligible" ? "text-warn" : ""}>{topoLabel(k)}</span> <span className="mono text-muted">×{n}</span>
                      </div>
                    ))}
                  </td>
                  {res.metrics.map((m) => {
                    const s = r.summary[m];
                    const isBest = best(m) === r.policy;
                    return (
                      <td key={m} className="px-3 py-2 text-right align-top">
                        {s?.mean == null ? (
                          <span className="text-faint">not measured</span>
                        ) : (
                          <>
                            <span className={`mono font-semibold ${isBest ? "rounded bg-ok-bg px-1 text-ok" : ""}`}>{(METRIC[m]?.fmt ?? String)(s.mean)}</span>
                            <div className="mono text-[10.5px] text-muted">
                              ± {s.std == null ? "—" : fmtStd(m, s.std)} · n={s.n}
                            </div>
                          </>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="border-t border-line bg-panel2 px-3 py-2 text-[11.5px] text-ink2">
            <b>Honesty note.</b> {res.note} The highlighted cell is only the best <i>mean</i> among policies eligible on every seed;
            where the difference is within the ± spread no superiority is claimed. Seeds: <span className="mono">{res.seeds.join(", ")}</span>.
            Utilization has no preferred direction and is not marked.
          </div>
        </section>
      )}
      {!res && busy == null && online !== false && (
        <div className="mt-3 rounded-[10px] border border-line bg-panel p-4 text-[12px] text-ink2">
          Runs the identical order book, layout and initial fleet under P0-H (hierarchical), P0-F (functional cells), P0-D
          (distributed) and adaptive LinUCB for each seed, and reports mean ± population std. Press <b>Run comparison</b>.
        </div>
      )}
    </main>
  );
}
