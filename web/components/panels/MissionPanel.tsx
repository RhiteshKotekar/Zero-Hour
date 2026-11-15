"use client";
// Mission status (plan §6.4/§6.6): counters, orders with per-task step bars, order → task → robot lineage
// (lineage retained from the teammate's Streamlit twin). Click an order / task / robot to select it.
import { useState } from "react";
import { TASK_STATUS_LABEL, assignmentAt, claimsAt, indexOf, orderStatusAt, taskStateAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import type { Order, TwinState } from "@/lib/types";
import { AgentChip, Badge, Card, Pri, TONE_VAR, useSel, useTwin } from "@/components/shell/ui";

export interface MissionPanelProps {
  className?: string;
}

const KIND_ICON: Record<string, string> = { PICK: "⬚", TRANSPORT: "⇢", PACK: "▣", DISPATCH: "⇥" };

export function MissionPanel({ className }: MissionPanelProps) {
  const { state, t } = useTwin();
  const { is, selRobot } = useSel();
  const [allLineage, setAllLineage] = useState(false);
  if (!state)
    return (
      <Card title="Mission status" className={className}>
        <div className="zh-empty">Loading…</div>
      </Card>
    );

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

  return (
    <Card
      title="Mission status"
      sub={`${orders.length} orders · ${tasks.length} SAMG tasks${pending.length ? ` · ${pending.length} waiting for next wave` : ""}`}
      className={className}
      right={
        <button className={`zh-chip ${allLineage ? "on" : ""}`} onClick={() => setAllLineage((v) => !v)} title="order → task → robot">
          Lineage
        </button>
      }
    >
      <div className="zh-counters">
        <Counter label="Orders" v={orders.length} />
        <Counter label="Active tasks" v={active} />
        <Counter label="Verified" v={`${verified}/${tasks.length}`} />
        <Counter label="Delayed" v={delayed} color={delayed ? "var(--warn)" : undefined} />
        <Counter label="Failed" v={failed} color={failed ? "var(--bad)" : undefined} />
        <Counter label="Security" v={viol ? `${viol} ALERT` : "SECURE"} color={viol ? "var(--sec)" : "var(--ok)"} small />
      </div>
      <div className="grid gap-1.5 p-2">
        {orders.map((o) => (
          <OrderRow key={o.id} state={state} o={o} t={t} open={allLineage || is("order", o.id) || o.tasks.some((id) => is("task", id))} is={is} selRobot={selRobot} />
        ))}
        {!orders.length && <div className="zh-empty">No orders have arrived yet.</div>}
      </div>
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
