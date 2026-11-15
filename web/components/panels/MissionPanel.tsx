"use client";
// Mission status: Shows sequential SAMG Mission Waves (each with its own LinUCB topology),
// and Customer Demand Orders with per-task progress and lineage.
import { useState } from "react";
import { TASK_STATUS_LABEL, assignmentAt, claimsAt, indexOf, orderStatusAt, taskStateAt, topoLabel, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import type { Order, TwinState, Wave } from "@/lib/types";
import { AgentChip, Badge, Card, Pri, TONE_VAR, useSel, useTwin } from "@/components/shell/ui";

export interface MissionPanelProps {
  className?: string;
  bare?: boolean;
}

const KIND_ICON: Record<string, string> = { PICK: "⬚", TRANSPORT: "⇢", PACK: "▣", DISPATCH: "⇥" };

export function MissionPanel({ className, bare }: MissionPanelProps) {
  const { state, t } = useTwin();
  const { is, selRobot } = useSel();
  const [allLineage, setAllLineage] = useState(false);
  const select = useStore((s) => s.select);

  if (!state) {
    if (bare) return <div className="zh-empty">Loading mission status…</div>;
    return (
      <Card title="Mission status" className={className}>
        <div className="zh-empty">Loading…</div>
      </Card>
    );
  }

  const activeWave = waveAt(state, t);
  const orders = state.orders.filter((o) => (o.arrival_s ?? 0) <= t);
  const tasks = state.tasks.filter((x) => orders.some((o) => o.id === x.order));
  const states = tasks.map((x) => taskStateAt(state, x.id, t)?.state ?? "OPEN");
  const active = states.filter((s) => s === "EXECUTING" || s === "ASSIGNED").length;
  const verified = states.filter((s) => s === "VERIFIED_COMPLETE").length;
  const failed = tasks.reduce((n, x) => n + x.states.filter((s) => s.state === "FAILED" && s.from === "EXECUTING" && s.t <= t).length, 0);
  const delayed =
    orders.filter((o) => !o.hold && t > o.deadline_s && !(o.dispatched_at != null && o.dispatched_at <= t)).length +
    states.filter((s) => s === "BLOCKED" || s === "REPLANNED").length;
  const viol = claimsAt(state, t).filter((c) => c.evidence === "DISPUTED").length;
  const pending = state.live?.pending_orders ?? [];

  const content = (
    <div className="flex h-full flex-col min-h-0 zh-scroll">
      {/* Overview Sub-bar */}
      <div className="flex flex-none items-center justify-between border-b border-line bg-panel2/60 px-3.5 py-1.5">
        <span className="text-[11px] font-semibold text-muted">
          {state.waves.length} SAMG Missions (Sequential Waves) · {orders.length} Customer Orders
        </span>
        <button
          className={`zh-chip ${allLineage ? "on" : ""}`}
          onClick={() => setAllLineage((v) => !v)}
          title="Toggle order → task → robot lineage"
        >
          Lineage
        </button>
      </div>

      {/* Counters */}
      <div className="zh-counters">
        <Counter label="Missions" v={state.waves.length} />
        <Counter label="Orders" v={orders.length} />
        <Counter label="Active Tasks" v={active} />
        <Counter label="Verified" v={`${verified}/${tasks.length}`} />
        <Counter label="Delayed" v={delayed} color={delayed ? "var(--warn)" : undefined} />
        <Counter label="Security" v={viol ? `${viol} ALERT` : "SECURE"} color={viol ? "var(--sec)" : "var(--ok)"} small />
      </div>

      {/* SAMG Missions (Sequential Waves) Section */}
      <div className="border-b border-line p-3 bg-panel">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10.5px] font-bold uppercase tracking-wider text-muted">
            SAMG Missions ({state.waves.length} Planning Waves)
          </span>
          <span className="text-[10px] font-medium text-muted">
            Single-topology execution
          </span>
        </div>

        <div className="space-y-1.5">
          {state.waves.map((w) => {
            const isWaveActive = activeWave?.number === w.number;
            const isDone = t >= w.t1 - 1e-6 && w.status !== "preview";
            const isUpcoming = t < w.t0;

            return (
              <div
                key={w.number}
                className={`rounded-xl border p-2.5 transition-all cursor-pointer ${
                  isWaveActive
                    ? "border-accent bg-accent-bg/40 shadow-xs"
                    : isDone
                    ? "border-line bg-panel2/40 opacity-80"
                    : "border-line bg-panel hover:bg-panel2"
                }`}
                onClick={() => select({ kind: "wave", id: String(w.number) })}
                title="Click to view this mission's topology decision"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="mono text-[12px] font-bold text-ink">
                      {w.mission_id}
                    </span>
                    <span className="text-[10.5px] font-semibold text-muted">
                      (Wave {w.number})
                    </span>
                    <Badge cls={isWaveActive ? "ok" : isDone ? "ink" : "warn"}>
                      {isWaveActive ? "ACTIVE" : isDone ? "COMPLETED" : "PLANNED"}
                    </Badge>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] uppercase font-bold text-muted">Topology:</span>
                    <span className="mono text-[11px] font-bold text-accent">
                      {topoLabel(w.topology)}
                    </span>
                  </div>
                </div>

                <div className="mt-1.5 flex items-center justify-between text-[10.5px] text-muted">
                  <span className="mono">
                    Window: t={w.t0.toFixed(0)}s → {w.t1.toFixed(0)}s
                  </span>
                  <span>{w.tasks.length} tasks scheduled</span>
                  {w.reward && (
                    <span className="text-samg font-semibold">
                      ACP Reward: {w.reward.value.toFixed(3)}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-2 text-[10px] text-muted">
          Sequential execution: the fleet coordinates under one active topology per wave.
        </div>
      </div>

      {/* Customer Orders Section */}
      <div className="p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10.5px] font-bold uppercase tracking-wider text-muted">
            Customer Demand Orders ({orders.length} Orders)
          </span>
          <span className="text-[10px] font-medium text-muted">
            Click an order to inspect tasks & lineage
          </span>
        </div>

        <div className="grid gap-2">
          {orders.map((o) => (
            <OrderRow
              key={o.id}
              state={state}
              o={o}
              t={t}
              open={allLineage || is("order", o.id) || o.tasks.some((id) => is("task", id))}
              is={is}
              selRobot={selRobot}
            />
          ))}
          {!orders.length && <div className="zh-empty">No orders have arrived yet.</div>}
        </div>
      </div>
    </div>
  );

  if (bare) {
    return <div className={`flex flex-col h-full min-h-0 ${className ?? ""}`}>{content}</div>;
  }

  return (
    <Card
      title="Missions & Orders"
      sub={`${state.waves.length} missions · ${orders.length} orders`}
      className={className}
      right={
        <button className={`zh-chip ${allLineage ? "on" : ""}`} onClick={() => setAllLineage((v) => !v)} title="order → task → robot">
          Lineage
        </button>
      }
    >
      {content}
    </Card>
  );
}

function Counter({ label, v, color, small }: { label: string; v: React.ReactNode; color?: string; small?: boolean }) {
  return (
    <div>
      <b style={{ color, fontSize: small ? 12 : undefined, lineHeight: small ? "22px" : undefined }}>{v}</b>
      <label>{label}</label>
    </div>
  );
}

function OrderRow({
  state,
  o,
  t,
  open,
  is,
  selRobot,
}: {
  state: TwinState;
  o: Order;
  t: number;
  open: boolean;
  is: (k: "order" | "task" | "robot", id: string | null | undefined) => boolean;
  selRobot: string | null;
}) {
  const select = useStore((s) => s.select);
  const st = orderStatusAt(state, o.id, t);
  const ix = indexOf(state);
  return (
    <div className={`zh-order ${is("order", o.id) ? "sel" : ""}`} onClick={() => select(is("order", o.id) ? null : { kind: "order", id: o.id })}>
      <div className="row">
        <div>
          <div className="mono text-[12px] font-bold">{o.id}</div>
          <Pri p={o.priority} />
        </div>
        <div className="min-w-0">
          <div className="zh-steps">
            {o.tasks.map((id) => (
              <i key={id} className={`${taskStateAt(state, id, t)?.state ?? ""} ${is("task", id) ? "sel" : ""}`} title={id} />
            ))}
          </div>
          <div className="mt-[3px] truncate text-[10.5px] text-muted">
            {o.items.join(" · ")} → {o.consolidation ?? "-"} → {o.dock ?? "-"}
          </div>
        </div>
        <div className="zh-ost" style={{ color: TONE_VAR[st.tone] }}>
          {st.label}
          <small>{st.sub}</small>
        </div>
      </div>
      {open && (
        <div className="zh-lineage" onClick={(e) => e.stopPropagation()}>
          {o.tasks.map((id) => {
            const task = ix.task.get(id);
            const s = taskStateAt(state, id, t);
            const a = assignmentAt(state, id, t);
            const label = s ? TASK_STATUS_LABEL[s.state] ?? s.state : "PENDING";
            return (
              <div
                key={id}
                className={`ln ${is("task", id) ? "sel" : ""}`}
                onClick={() => useStore.getState().select({ kind: "task", id })}
                title={id}
              >
                <span className="text-center text-muted">{KIND_ICON[task?.kind ?? ""] ?? "·"}</span>
                <span className="truncate">
                  <span className="font-semibold">{task?.label ?? id}</span>
                  {task?.zone && <span className="text-muted"> · {task.zone}</span>}
                </span>
                <Badge cls={label}>{label}</Badge>
                <span className="flex items-center gap-1">
                  {a ? (
                    <>
                      {a.reassigned_from && <span className="text-[10px] text-warn">↺ {a.reassigned_from} →</span>}
                      <AgentChip
                        state={state}
                        id={a.agent}
                        selected={selRobot === a.agent && is("robot", a.agent)}
                        onClick={() => useStore.getState().select({ kind: "robot", id: a.agent })}
                      />
                    </>
                  ) : (
                    <span className="text-faint">—</span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default MissionPanel;
