"use client";
// Topology decision: Displays coordination graph, LinUCB arm scores, context vector (ctx-v1),
// and an operator override workflow with system recommendation warnings and confirmation.
import { useState } from "react";
import { fmtS, topoLabel, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import type { TwinState, Wave, Topology } from "@/lib/types";
import { Badge, Card, CTX_NAMES, useSel, useTwin } from "@/components/shell/ui";
import { ROLE_COLOR } from "@/lib/derive";

export interface TopologyPanelProps {
  className?: string;
  bare?: boolean;
}

export function TopologyPanel({ className, bare }: TopologyPanelProps) {
  const { state, t } = useTwin();
  const { sel, selRobot } = useSel();
  const select = useStore((s) => s.select);

  // Human Operator Override state
  const [overrideTopology, setOverrideTopology] = useState<Topology | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [pendingTopology, setPendingTopology] = useState<Topology | null>(null);

  if (!state || !state.waves.length) {
    if (bare) return <div className="zh-empty">{state ? "No SAMG wave planned yet." : "Loading…"}</div>;
    return (
      <Card title="Coordination topology" className={className}>
        <div className="zh-empty">{state ? "No SAMG wave planned yet." : "Loading…"}</div>
      </Card>
    );
  }

  const current = waveAt(state, t)!;
  const picked = sel?.kind === "wave" ? state.waves.find((w) => String(w.number) === sel.id) : undefined;
  const w = picked ?? current;

  // Recommended topology by the autonomous bandit system
  const recommendedTopology = w.topology;

  // Effective topology (manual override if active, otherwise system recommended)
  const effectiveTopology = overrideTopology ?? recommendedTopology;

  const offered = w.arms.filter((a) => a.offered);
  const learn = w.arms.some((a) => (a.bonus ?? 0) > 0 || (a.mean ?? 0) > 0);
  const maxS = Math.max(...w.arms.map((a) => (a.offered ? a.score || 0 : 0)), 0.01);
  const sela = w.arms.find((a) => a.topology === effectiveTopology) ?? w.arms.find((a) => a.selected);
  const recArm = w.arms.find((a) => a.topology === recommendedTopology);
  const ineligible = w.arms.filter((a) => !a.offered);

  const openOverrideDialog = (target?: Topology) => {
    setPendingTopology(target ?? (overrideTopology ? overrideTopology : (recommendedTopology === "HIERARCHICAL" ? "FUNCTIONAL_CELL" : "HIERARCHICAL")));
    setDialogOpen(true);
  };

  const handleConfirmOverride = () => {
    if (pendingTopology === recommendedTopology) {
      setOverrideTopology(null); // Revert to autonomous recommendation
    } else {
      setOverrideTopology(pendingTopology);
    }
    setDialogOpen(false);

    // =========================================================================
    // USER EXTENSION POINT:
    // When backend logic is ready, call your API endpoint:
    //
    // import * as api from "@/lib/api";
    // if (pendingTopology && pendingTopology !== recommendedTopology) {
    //   api.control("override_topology", { mission_id: w.mission_id, wave: w.number, topology: pendingTopology })
    //     .catch((err) => console.error("Topology override error:", err));
    // } else {
    //   api.control("reset_topology", { mission_id: w.mission_id, wave: w.number })
    //     .catch((err) => console.error("Reset topology error:", err));
    // }
    // =========================================================================
  };

  const content = (
    <div className="relative flex h-full flex-col min-h-0 zh-scroll">
      {/* Sub-header Bar: Mission Wave Switcher + Topology Status & Force Switch Action */}
      <div className="flex flex-none items-center justify-between border-b border-line bg-panel2/60 px-3.5 py-2">
        {/* Left: Mission & Wave Selector */}
        <div className="flex items-center gap-2">
          <span className="mono text-[12px] font-bold text-ink">
            {w.mission_id}
          </span>
          <span className="text-[11px] text-muted">
            Wave {w.number}{w.number > 1 ? " (replanned)" : ""}
          </span>
          {state.waves.length > 1 && (
            <div className="seg ml-1">
              {state.waves.map((wv) => (
                <button
                  key={wv.number}
                  className={w.number === wv.number ? "on" : ""}
                  onClick={() => select(wv.number === current.number ? null : { kind: "wave", id: String(wv.number) })}
                  title={`View Mission ${wv.mission_id}`}
                >
                  W{wv.number}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: Topology Status & Override Trigger */}
        <div className="flex items-center gap-2.5">
          {overrideTopology ? (
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-warn font-semibold">
                Override: <span className="font-bold">{topoLabel(overrideTopology)}</span>
              </span>
              <span className="text-[10px] text-muted">
                (Rec: {topoLabel(recommendedTopology)})
              </span>
              <button
                className="btn text-[11px] text-warn hover:underline ml-1"
                onClick={() => setOverrideTopology(null)}
                title="Revert to autonomous system recommendation"
              >
                Reset to Auto
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] uppercase font-bold text-muted">Recommended:</span>
              <span className="text-[11.5px] font-bold text-ink">
                {topoLabel(recommendedTopology)}
              </span>
            </div>
          )}

          <button
            className={`btn text-[11px] font-semibold ${dialogOpen ? "on" : ""}`}
            onClick={() => (dialogOpen ? setDialogOpen(false) : openOverrideDialog())}
          >
            {overrideTopology ? "Change Override" : "Force Switch..."}
          </button>
        </div>
      </div>

      {/* Human Override Modal Dialog with explicit System Recommendation Warning */}
      {dialogOpen && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-black/25 backdrop-blur-[2px] p-3">
          <div className="w-full max-w-[420px] rounded-2xl border border-line bg-panel p-4 shadow-xl space-y-3.5 my-auto">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-line pb-2.5">
              <div>
                <div className="text-[13px] font-bold text-ink">Change Coordination Topology</div>
                <div className="text-[10.5px] text-muted mt-0.5">
                  Mission <span className="mono font-bold text-ink">{w.mission_id}</span> · Single active fleet topology
                </div>
              </div>
              <button
                className="text-[11px] font-semibold text-muted hover:text-ink px-2 py-0.5 rounded hover:bg-panel2 transition-colors"
                onClick={() => setDialogOpen(false)}
              >
                Cancel
              </button>
            </div>

            {/* Arm Options Selector */}
            <div className="space-y-1.5">
              <span className="text-[9.5px] font-bold uppercase tracking-wider text-muted">
                Select Target Topology:
              </span>
              <div className="grid grid-cols-3 gap-2">
                {(["HIERARCHICAL", "FUNCTIONAL_CELL", "DISTRIBUTED"] as const).map((tName) => {
                  const arm = w.arms.find((a) => a.topology === tName);
                  const isRec = recommendedTopology === tName;
                  const isTarget = pendingTopology === tName;
                  const isEligible = arm?.offered ?? true;

                  return (
                    <button
                      key={tName}
                      disabled={!isEligible}
                      className={`flex flex-col p-2.5 rounded-xl border text-left transition-all ${
                        isTarget
                          ? "border-accent bg-accent-bg text-ink shadow-xs"
                          : isEligible
                          ? "border-line bg-panel hover:bg-panel2"
                          : "border-line/60 bg-panel2/40 opacity-50 cursor-not-allowed"
                      }`}
                      onClick={() => setPendingTopology(tName)}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-[11px]">{topoLabel(tName)}</span>
                      </div>
                      {isRec && (
                        <span className="text-[8.5px] font-bold text-ok bg-ok-bg px-1.5 py-0.5 rounded mt-1 self-start">
                          RECOMMENDED
                        </span>
                      )}
                      <span className="text-[10px] text-muted mt-1">
                        {isEligible ? (learn ? `Score: ${(arm?.score ?? 0).toFixed(3)}` : "Eligible") : "Ineligible"}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Warning Box when selecting an alternative (non-recommended) topology */}
            {pendingTopology && pendingTopology !== recommendedTopology && (
              <div className="rounded-xl border border-warn/40 bg-warn-bg/70 p-3 text-[11.5px] space-y-1.5">
                <div className="font-bold text-warn text-[12px]">
                  Warning: Coordination Topology Override
                </div>
                <div className="text-ink leading-relaxed">
                  <b>{topoLabel(recommendedTopology)}</b> was system recommended. Would you like to change the topology to <b>{topoLabel(pendingTopology)}</b>?
                </div>
                <div className="text-[10px] text-muted leading-normal">
                  Mission {w.mission_id} autonomous bandit policy ({w.policy}) selected {topoLabel(recommendedTopology)} based on task dependency density and fleet capability diversity.
                </div>
              </div>
            )}

            {/* Notification when selecting the recommended topology */}
            {pendingTopology && pendingTopology === recommendedTopology && (
              <div className="rounded-xl border border-ok/30 bg-ok-bg/50 p-2.5 text-[11px] text-ink leading-relaxed">
                <b>{topoLabel(recommendedTopology)}</b> is the system recommended topology. Confirming will run the autonomous bandit policy.
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-line">
              <button className="btn text-[11px]" onClick={() => setDialogOpen(false)}>
                Cancel
              </button>
              <button
                disabled={!pendingTopology}
                className={`btn text-[11px] font-semibold ${
                  pendingTopology !== recommendedTopology
                    ? "!bg-warn !border-warn !text-white hover:opacity-90"
                    : "primary"
                }`}
                onClick={handleConfirmOverride}
              >
                {pendingTopology === recommendedTopology
                  ? `Apply System Recommendation (${topoLabel(recommendedTopology)})`
                  : `Confirm Force to ${topoLabel(pendingTopology)}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Graph and Arms Decision */}
      <div className="grid grid-cols-[190px_1fr] border-b border-line">
        <div className="flex items-center justify-center border-r border-line bg-panel2/40 p-2">
          <TopoGraph state={state} w={w} selRobot={selRobot} forcedTopology={overrideTopology} />
        </div>
        <div className="min-w-0 p-3">
          <div className="cap mb-1.5">{learn ? "LinUCB score = mean + bonus" : "Fixed baseline"}</div>
          <div className="space-y-1.5">
            {w.arms.map((a) => {
              const isOverriddenArm = overrideTopology === a.topology;
              const isSelectedArm = effectiveTopology === a.topology;
              const isRecArm = recommendedTopology === a.topology;
              const isClickable = a.offered && !isSelectedArm;

              return (
                <div
                  key={a.topology}
                  onClick={() => {
                    if (isClickable) {
                      openOverrideDialog(a.topology);
                    }
                  }}
                  className={`zh-arm ${isSelectedArm ? "sel" : ""} ${a.offered ? "" : "off"} ${
                    isOverriddenArm ? "!border-warn !bg-warn-bg/30" : ""
                  } ${isClickable ? "cursor-pointer hover:border-accent/70 hover:bg-panel2/60 transition-all" : ""}`}
                  title={isClickable ? `Click to force switch to ${topoLabel(a.topology)}` : undefined}
                >
                  <div className="h">
                    <span className="font-semibold flex items-center gap-1.5">
                      {isSelectedArm ? "◆ " : ""}
                      {topoLabel(a.topology)}
                      {isOverriddenArm && (
                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-warn-bg text-warn border border-warn/40">
                          OVERRIDE
                        </span>
                      )}
                      {isRecArm && !isOverriddenArm && (
                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-ok-bg text-ok border border-ok/40">
                          RECOMMENDED
                        </span>
                      )}
                    </span>
                    <span className="mono text-[11px] font-bold">
                      {!a.offered ? "not eligible" : learn ? (a.score ?? 0).toFixed(3) : a.selected ? "set by policy" : ""}
                    </span>
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
              );
            })}
          </div>
          <div className="mt-2 text-[10px] text-muted">
            {offered.length} of {w.arms.length} arms eligible
            {ineligible.length ? ` · excluded: ${ineligible.map((a) => topoLabel(a.topology)).join(", ")}` : ""}
          </div>
        </div>
      </div>

      {/* Decision Banner (Autonomous vs Operator Override) */}
      <div className={`flex items-center justify-between border-b border-line px-3.5 py-2 text-[11.5px] ${
        overrideTopology ? "bg-warn-bg/50 text-ink" : "bg-samg-bg text-ink"
      }`}>
        <div className="flex items-center gap-2">
          <Badge cls={overrideTopology ? "warn" : "samg"}>
            {overrideTopology ? "OPERATOR OVERRIDE" : w.policy.includes("LinUCB") || learn ? "ADAPTIVE DECISION" : "FIXED POLICY"}
          </Badge>
          <span className="min-w-0">
            {overrideTopology ? (
              <>
                Forced <b className="text-[12px]">{topoLabel(overrideTopology)}</b> (System recommendation: {topoLabel(recommendedTopology)})
              </>
            ) : (
              <>
                Selected <b className="text-[12px]">{topoLabel(w.topology ?? "none")}</b> by <span className="mono text-[11px]">{w.policy}</span>
                {w.warmup ? " · warm-up" : ""}
                {sela && learn ? (
                  <span className="mono text-ink2">
                    {" "}
                    ({(sela.score ?? 0).toFixed(3)} = {(sela.mean ?? 0).toFixed(3)} + {(sela.bonus ?? 0).toFixed(3)})
                  </span>
                ) : null}
              </>
            )}
          </span>
        </div>

        {overrideTopology && (
          <button
            className="text-[11px] font-semibold text-warn hover:underline"
            onClick={() => setOverrideTopology(null)}
          >
            Revert to Recommended
          </button>
        )}
      </div>

      {/* Context Vector ctx-v1 */}
      <div className="border-b border-line p-3">
        <div className="cap mb-2">Context Features for {w.mission_id} (ctx-v1)</div>
        <div className="grid grid-cols-2 gap-2">
          {w.context
            .filter((c) => c.name !== "intercept")
            .map((c) => (
              <div key={c.name} className="flex flex-col gap-1 p-2 rounded-xl bg-panel2/60 border border-line shadow-xs">
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
        </div>
        <div className="mt-2 text-[10px] text-muted">
          Features extracted per-mission. Contextual LinUCB evaluates arms from these metrics.
        </div>
      </div>

      {/* Wave History */}
      <div className="p-3">
        <div className="cap mb-2">Sequential Mission Wave History</div>
        <div className="space-y-1.5">
          {state.waves
            .filter((x) => x.t0 <= t)
            .map((x) => (
              <WaveRow key={x.number} x={x} t={t} active={x === w} onClick={() => select(x === w && picked ? null : { kind: "wave", id: String(x.number) })} />
            ))}
        </div>
      </div>
    </div>
  );

  if (bare) {
    return <div className={`flex flex-col h-full min-h-0 ${className ?? ""}`}>{content}</div>;
  }

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
      {content}
    </Card>
  );
}

function WaveRow({ x, t, active, onClick }: { x: Wave; t: number; active: boolean; onClick: () => void }) {
  const done = t >= x.t1 - 1e-6 && x.status !== "preview";
  const s = x.arms.find((a) => a.selected);
  return (
    <div
      className={`mb-1.5 cursor-pointer rounded-xl border p-2 text-[11px] transition-all shadow-xs ${
        active ? "border-accent bg-accent-bg/80" : "border-line bg-white hover:bg-panel2"
      }`}
      onClick={onClick}
    >
      <div className="flex items-center gap-2">
        <span className="mono font-bold">W{x.number}</span>
        <span className="mono text-muted">{x.mission_id}</span>
        {x.number > 1 && <Badge cls="warn">REPLANNED</Badge>}
        <b className="ml-auto">{topoLabel(x.topology)}</b>
        {s?.score != null && <span className="mono font-bold text-ink">{s.score.toFixed(3)}</span>}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-2 text-[10.5px] text-muted">
        <span className="mono">
          t {x.t0.toFixed(0)}–{done ? x.t1.toFixed(0) : "…"} s
        </span>
        <span>· {x.tasks.length} tasks</span>
        {done && x.reward && <span className="text-samg font-semibold">· reward {x.reward.value.toFixed(4)}</span>}
        {done && x.episode && <span>· {x.episode.status}</span>}
      </div>
    </div>
  );
}

/** Node positions are layout only; nodes, links and coordinators come from the wave's CoordinationGraph. */
function TopoGraph({
  state,
  w,
  selRobot,
  forcedTopology,
}: {
  state: TwinState;
  w: Wave;
  selRobot: string | null;
  forcedTopology?: Topology | null;
}) {
  const g = w.graph;
  const select = useStore((s) => s.select);
  if (!g) return <div className="zh-empty">No coordination graph.</div>;

  const currentTopology = forcedTopology ?? g.topology;
  const nodes = [...new Set([...g.links.flat(), ...g.coordinators])];
  for (const r of state.robots) if (!nodes.includes(r.id)) nodes.push(r.id);
  const pos: Record<string, [number, number]> = {};
  const hub = g.coordinators[0];
  const labels: { x: number; text: string }[] = [];
  const cells = Object.entries(g.cells).filter(([, v]) => !(v.length === 1 && v[0] === hub));

  if (currentTopology === "FUNCTIONAL_CELL" && cells.length) {
    if (hub) pos[hub] = [95, 20];
    cells.forEach(([c, members], i) => {
      const cx = 20 + i * (150 / Math.max(cells.length - 1, 1));
      members.forEach((m, j) => (pos[m] = [cx, 75 + j * 24]));
      labels.push({ x: cx, text: c.toUpperCase() });
    });
    const rest = nodes.filter((n) => !pos[n]);
    rest.forEach((n, i) => (pos[n] = [18 + i * 22, 165]));
  } else if (currentTopology === "HIERARCHICAL" && hub) {
    pos[hub] = [95, 22];
    const others = nodes.filter((n) => n !== hub);
    others.forEach((n, i) => {
      const row = i < 5 ? 0 : 1;
      const k = row ? i - 5 : i;
      const cnt = row ? others.length - 5 : Math.min(5, others.length);
      pos[n] = [20 + k * (150 / Math.max(cnt - 1, 1)), 88 + row * 48];
    });
  } else {
    nodes.forEach((n, i) => {
      const a = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
      pos[n] = [95 + 65 * Math.cos(a), 88 + 65 * Math.sin(a)];
    });
  }
  const coords = new Set([...g.coordinators, ...Object.values(g.cell_coordinators)]);
  return (
    <svg width="190" height="175" viewBox="0 0 190 180" className="block">
      {labels.map((l) => (
        <text key={l.text} x={l.x} y={62} fontSize={7} textAnchor="middle" fill="#7b8699" fontWeight={700}>
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
            {sel && <circle cx={pos[n][0]} cy={pos[n][1]} r={n === hub ? 16 : 13} fill="none" stroke="#2563eb" strokeWidth={2} />}
            <circle
              cx={pos[n][0]}
              cy={pos[n][1]}
              r={n === hub ? 12 : 9.5}
              fill={excl ? "#f1f5f9" : col}
              stroke={coords.has(n) ? "#f59e0b" : "#fff"}
              strokeWidth={coords.has(n) ? 2.2 : 1.4}
              opacity={excl ? 0.6 : 1}
            />
            <text x={pos[n][0]} y={pos[n][1] + 2.5} fontSize={n === hub ? 7.2 : 6.8} textAnchor="middle" fill={excl ? "#94a3b8" : "#fff"} fontWeight={800}>
              {n}
            </text>
            {excl && (
              <text x={pos[n][0] + 7} y={pos[n][1] - 6} fontSize={8.5} fill="#d92d2d" fontWeight={800}>
                ✕
              </text>
            )}
          </g>
        );
      })}
      <text x={95} y={174} fontSize={8} textAnchor="middle" fill="#0b1220" fontWeight={800} letterSpacing={0.8}>
        {topoLabel(currentTopology)} · {g.links.length} links
      </text>
    </svg>
  );
}

export default TopologyPanel;
