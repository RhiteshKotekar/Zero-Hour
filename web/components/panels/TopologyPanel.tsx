"use client";
// Topology decision (plan §6.4/§6.6): which topology SAMG uses in each wave and the numbers behind it —
// coordination graph (waves[i].graph), LinUCB score = mean + uncertainty bonus over the eligible arms,
// ineligibility reasons, the context vector, and the wave history. The policy exposes scores, not reasons:
// nothing here is a generated explanation.
import { fmtS, topoLabel, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import type { TwinState, Wave } from "@/lib/types";
import { Badge, Card, CTX_NAMES, useSel, useTwin } from "@/components/shell/ui";
import { ROLE_COLOR } from "@/lib/derive";

export interface TopologyPanelProps {
  className?: string;
}

export function TopologyPanel({ className }: TopologyPanelProps) {
  const { state, t } = useTwin();
  const { sel, selRobot } = useSel();
  const select = useStore((s) => s.select);
  if (!state || !state.waves.length)
    return (
      <Card title="Coordination topology" className={className}>
        <div className="zh-empty">{state ? "No SAMG wave planned yet." : "Loading…"}</div>
      </Card>
    );

  const current = waveAt(state, t)!;
  const picked = sel?.kind === "wave" ? state.waves.find((w) => String(w.number) === sel.id && w.t0 <= t) : undefined;
  const w = picked ?? current;
  const offered = w.arms.filter((a) => a.offered);
  // learning policies report mean/bonus per arm; fixed baselines report none (all zero)
  const learn = w.arms.some((a) => (a.bonus ?? 0) > 0 || (a.mean ?? 0) > 0);
  const maxS = Math.max(...w.arms.map((a) => (a.offered ? a.score || 0 : 0)), 0.01);
  const sela = w.arms.find((a) => a.selected);
  const ineligible = w.arms.filter((a) => !a.offered);

  return (
    <Card
      title="Coordination topology"
      sub={
        <>
          wave {w.number} · <span className="mono">{w.mission_id}</span>
          {w.number > 1 ? " (replanned)" : ""}
          {w.status === "preview" ? " · preview" : ""}
          {picked && picked !== current ? " · history" : ""}
        </>
      }
      right={
        picked && picked !== current ? (
          <button className="zh-chip" onClick={() => select(null)}>
            current wave
          </button>
        ) : undefined
      }
      className={className}
    >
      <div className="grid grid-cols-[200px_1fr]">
        <div className="border-r border-line bg-panel2">
          <TopoGraph state={state} w={w} selRobot={selRobot} />
        </div>
        <div className="min-w-0 px-3 py-2">
          <div className="cap mb-1">{learn ? "LinUCB score = mean + uncertainty bonus" : "Fixed baseline"}</div>
          {w.arms.map((a) => (
            <div key={a.topology} className={`zh-arm ${a.selected ? "sel" : ""} ${a.offered ? "" : "off"}`}>
              <div className="h">
                <span>
                  {a.selected ? "◆ " : ""}
                  {topoLabel(a.topology)}
                </span>
                <span>{!a.offered ? "not eligible" : learn ? (a.score ?? 0).toFixed(3) : a.selected ? "set by policy" : ""}</span>
              </div>
              {learn && a.offered ? (
                <>
                  <div className="zh-bar">
                    <div className="m" style={{ width: `${((a.mean || 0) / maxS) * 100}%` }} />
                    <div className="b" style={{ left: `${((a.mean || 0) / maxS) * 100}%`, width: `${((a.bonus || 0) / maxS) * 100}%` }} />
                  </div>
                  <small>
                    mean {(a.mean ?? 0).toFixed(3)} + bonus {(a.bonus ?? 0).toFixed(3)}
                  </small>
                </>
              ) : a.reasons.length ? (
                <small className="mono" style={{ color: "var(--bad)" }}>
                  {a.reasons.join(", ")}
                </small>
              ) : null}
            </div>
          ))}
          <div className="text-[10.5px] text-muted">
            {offered.length} of {w.arms.length} arms eligible (feasible_topologies)
            {ineligible.length ? ` · excluded before scoring: ${ineligible.map((a) => topoLabel(a.topology)).join(", ")}` : ""}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 border-t border-line bg-samg-bg px-3 py-1.5 text-[11.5px]">
        <Badge cls="samg">{w.policy.includes("LinUCB") || learn ? "ADAPTIVE DECISION" : "FIXED POLICY"}</Badge>
        <span className="min-w-0">
          Selected <b className="text-[12.5px]">{topoLabel(w.topology ?? "none")}</b> by <span className="mono">{w.policy}</span>
          {w.warmup ? " · warm-up" : ""}
          {sela && learn ? ` · argmax score of ${offered.length} eligible` : ""}
          {sela && learn ? (
            <span className="mono text-ink2">
              {" "}
              ({(sela.score ?? 0).toFixed(3)} = {(sela.mean ?? 0).toFixed(3)} + {(sela.bonus ?? 0).toFixed(3)})
            </span>
          ) : null}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 border-t border-line px-3.5 pb-2.5 pt-2 bg-panel2/40">
        {w.context
          .filter((c) => c.name !== "intercept")
          .map((c) => (
            <div key={c.name} className="flex flex-col gap-1 p-2 rounded-xl bg-white border border-line shadow-xs">
              <div className="flex justify-between items-center text-[10.5px]">
                <span className="truncate font-medium text-ink2" title={c.name}>
                  {CTX_NAMES[c.name] ?? c.name}
                </span>
                <span className="mono font-bold text-ink">{c.value.toFixed(2)}</span>
              </div>
              <div className="zh-bar !mt-0 !h-1.5">
                <div className="m" style={{ width: `${Math.min(1, Math.max(0, c.value)) * 100}%`, background: "var(--samg)" }} />
              </div>
            </div>
          ))}
        <div className="col-span-2 text-[10px] text-muted">
          Context vector ctx-v1 passed to the policy. The policy exposes scores, not reasons; no explanation is generated.
        </div>
      </div>

      <div className="border-t border-line px-3.5 py-2">
        <div className="cap mb-1.5">Wave history</div>
        {state.waves
          .filter((x) => x.t0 <= t)
          .map((x) => (
            <WaveRow key={x.number} x={x} t={t} active={x === w} onClick={() => select(x === w && picked ? null : { kind: "wave", id: String(x.number) })} />
          ))}
      </div>
    </Card>
  );
}

function WaveRow({ x, t, active, onClick }: { x: Wave; t: number; active: boolean; onClick: () => void }) {
  const done = t >= x.t1 - 1e-6 && x.status !== "preview";
  const s = x.arms.find((a) => a.selected);
  return (
    <div
      className={`mb-1.5 cursor-pointer rounded-xl border p-2 text-[11px] transition-all shadow-xs ${active ? "border-accent bg-accent-bg/80" : "border-line bg-white hover:bg-panel2"}`}
      onClick={onClick}
    >
      <div className="flex items-center gap-2">
        <span className="mono font-bold">W{x.number}</span>
        <span className="mono text-muted">{x.mission_id}</span>
        {x.number > 1 && <Badge cls="warn">REPLANNED</Badge>}
        <b className="ml-auto">{topoLabel(x.topology)}</b>
        {s?.score != null && <span className="mono text-ink2">{s.score.toFixed(3)}</span>}
      </div>
      <div className="mt-0.5 flex flex-wrap gap-x-2 text-[10.5px] text-muted">
        <span className="mono">
          t {x.t0.toFixed(0)}–{done ? x.t1.toFixed(0) : "…"} s
        </span>
        <span>{x.tasks.length} tasks</span>
        {x.allocation && (
          <span>
            {x.allocation.solver} {x.allocation.status}
            {x.allocation.fallback ? " (fallback)" : ""} · plan {fmtS(x.allocation.objective.makespan_s)}
          </span>
        )}
        {x.excluded.length > 0 && <span className="text-bad">excluded {x.excluded.join(", ")}</span>}
        {done && x.reward && <span className="text-samg">reward {x.reward.value.toFixed(4)}</span>}
        {done && x.episode && <span>{x.episode.status}</span>}
        {done && x.learning && (
          <span className={x.learning.applied ? "text-ok" : "text-warn"}>
            {x.learning.applied ? `update applied (${x.learning.source})` : x.learning.rejection ? `update blocked: ${x.learning.rejection}` : "no update"}
          </span>
        )}
        {!done && <span className="text-accent">running</span>}
      </div>
    </div>
  );
}

/** Node positions are layout only; nodes, links and coordinators come from the wave's CoordinationGraph. */
function TopoGraph({ state, w, selRobot }: { state: TwinState; w: Wave; selRobot: string | null }) {
  const g = w.graph;
  const select = useStore((s) => s.select);
  if (!g) return <div className="zh-empty">No coordination graph.</div>;
  const nodes = [...new Set([...g.links.flat(), ...g.coordinators])];
  for (const r of state.robots) if (!nodes.includes(r.id)) nodes.push(r.id);
  const pos: Record<string, [number, number]> = {};
  const hub = g.coordinators[0];
  const labels: { x: number; text: string }[] = [];
  const cells = Object.entries(g.cells).filter(([, v]) => !(v.length === 1 && v[0] === hub));
  if (g.topology === "FUNCTIONAL_CELL" && cells.length) {
    if (hub) pos[hub] = [100, 22];
    cells.forEach(([c, members], i) => {
      const cx = 22 + i * (156 / Math.max(cells.length - 1, 1));
      members.forEach((m, j) => (pos[m] = [cx, 82 + j * 26]));
      labels.push({ x: cx, text: c.toUpperCase() });
    });
    const rest = nodes.filter((n) => !pos[n]);
    rest.forEach((n, i) => (pos[n] = [20 + i * 24, 176]));
  } else if (g.topology === "HIERARCHICAL" && hub) {
    pos[hub] = [100, 24];
    const others = nodes.filter((n) => n !== hub);
    others.forEach((n, i) => {
      const row = i < 5 ? 0 : 1;
      const k = row ? i - 5 : i;
      const cnt = row ? others.length - 5 : Math.min(5, others.length);
      pos[n] = [20 + k * (160 / Math.max(cnt - 1, 1)), 96 + row * 52];
    });
  } else {
    nodes.forEach((n, i) => {
      const a = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
      pos[n] = [100 + 70 * Math.cos(a), 92 + 70 * Math.sin(a)];
    });
  }
  const coords = new Set([...g.coordinators, ...Object.values(g.cell_coordinators)]);
  return (
    <svg width="200" height="180" viewBox="0 0 200 196" className="block">
      {labels.map((l) => (
        <text key={l.text} x={l.x} y={68} fontSize={7.5} textAnchor="middle" fill="#7b8699" fontWeight={700}>
          {l.text}
        </text>
      ))}
      {g.links.map(([a, b], i) =>
        pos[a] && pos[b] ? (
          <line
            key={i}
            x1={pos[a][0]}
            y1={pos[a][1]}
            x2={pos[b][0]}
            y2={pos[b][1]}
            stroke={a === hub || b === hub ? "#0b1220" : "#94a3b8"}
            strokeWidth={a === hub || b === hub ? 1.4 : 1.1}
            opacity={0.75}
          />
        ) : null,
      )}
      {nodes.map((n) => {
        if (!pos[n]) return null;
        const r = state.robots.find((x) => x.id === n);
        const col = r ? ROLE_COLOR[r.role] ?? "#334155" : "#334155";
        const excl = w.excluded.includes(n);
        const sel = selRobot === n;
        return (
          <g key={n} style={{ cursor: r?.physical ? "pointer" : "default" }} onClick={() => r?.physical && select({ kind: "robot", id: n })}>
            <title>{`${n}${r ? ` · ${r.label}` : ""}${coords.has(n) ? " · coordinator" : ""}${excl ? " · excluded from this wave" : ""}`}</title>
            {sel && <circle cx={pos[n][0]} cy={pos[n][1]} r={n === hub ? 17 : 14} fill="none" stroke="#2563eb" strokeWidth={2} />}
            <circle
              cx={pos[n][0]}
              cy={pos[n][1]}
              r={n === hub ? 13 : 10}
              fill={excl ? "#f1f5f9" : col}
              stroke={coords.has(n) ? "#f59e0b" : "#fff"}
              strokeWidth={coords.has(n) ? 2.4 : 1.5}
              opacity={excl ? 0.6 : 1}
            />
            <text x={pos[n][0]} y={pos[n][1] + 2.6} fontSize={n === hub ? 7.6 : 7} textAnchor="middle" fill={excl ? "#94a3b8" : "#fff"} fontWeight={800}>
              {n}
            </text>
            {excl && (
              <text x={pos[n][0] + 8} y={pos[n][1] - 7} fontSize={9} fill="#d92d2d" fontWeight={800}>
                ✕
              </text>
            )}
          </g>
        );
      })}
      <text x={100} y={190} fontSize={8.5} textAnchor="middle" fill="#0b1220" fontWeight={800} letterSpacing={1}>
        {topoLabel(g.topology)} · {g.links.length} links
      </text>
    </svg>
  );
}

export default TopologyPanel;
