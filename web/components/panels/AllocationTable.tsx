"use client";
// Task allocation (plan §6.6): the current wave's CP-SAT plan with live status, ETA, zone and the
// ↺ reassigned-from highlight. Rows of the selected task / robot / order are highlighted; click selects.
import { TASK_STATUS_LABEL, assignmentAt, clockAt, fmtS, indexOf, robotAt, taskStateAt, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { AgentChip, Badge, Pri, useSel, useTwin } from "@/components/shell/ui";

export interface AllocationTableProps {
  className?: string;
}

const ORDER: Record<string, number> = {
  EXECUTING: 0, MOVING: 0, PICKING: 0, TRANSPORTING: 0, PACKING: 0, WAITING: 0,
  ASSIGNED: 1, PENDING: 1, REPORTED: 2, BLOCKED: 2, FAILED: 2, REPLANNED: 2, VERIFIED: 3,
};

export function AllocationTable({ className }: AllocationTableProps) {
  const { state, t } = useTwin();
  const { sel, selRobot, is } = useSel();
  const select = useStore((s) => s.select);
  if (!state) return <div className="zh-empty">Loading…</div>;
  const w = waveAt(state, t);
  if (!w) return <div className="zh-empty">No SAMG wave planned yet.</div>;
  const ix = indexOf(state);
  const rows = w.tasks
    .map((id) => {
      const x = ix.task.get(id)!;
      const a = assignmentAt(state, id, t);
      const s = taskStateAt(state, id, t);
      let label = s ? TASK_STATUS_LABEL[s.state] ?? s.state : "PENDING";
      if (s?.state === "EXECUTING" && a) {
        const rs = robotAt(state, a.agent, t);
        if (rs.task === id) label = String(rs.status);
      }
      // ETA: verified/actual window end once known (≤ t), otherwise the plan end
      const eta = x.window?.length && x.window[1] <= t ? clockAt(state, x.window[1]) : a ? clockAt(state, a.plan_end) : "—";
      return { x, a, label, eta, re: a?.reassigned_from, rank: ORDER[label] ?? 1 };
    })
    .filter((r) => r.x)
    .sort((p, q) => p.rank - q.rank || (p.a?.plan_start ?? 0) - (q.a?.plan_start ?? 0));

  return (
    <div className={`flex h-full min-h-0 flex-col ${className ?? ""}`}>
      <div className="flex flex-none items-center gap-2 border-b border-line px-3 py-1 text-[11px] text-muted">
        <span>
          {w.allocation ? `${w.allocation.solver} ${w.allocation.status}${w.allocation.fallback ? " (fallback)" : ""}` : "no plan"} · wave {w.number} ·{" "}
          {w.tasks.length} tasks
          {w.allocation ? ` · planned makespan ${fmtS(w.allocation.objective.makespan_s)} · handoff cost ${w.allocation.objective.handoff_cost}` : ""}
        </span>
        <span className="ml-auto">
          <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm align-[-1px]" style={{ background: "#fff8e6", boxShadow: "inset 3px 0 0 var(--warn)" }} />
          reassigned after replanning
        </span>
      </div>
      <div className="zh-scroll flex-1">
        <table className="zh-table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Order</th>
              <th>Agent</th>
              <th>Priority</th>
              <th>Status</th>
              <th>Plan</th>
              <th>ETA</th>
              <th>Zone</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ x, a, label, eta, re }) => {
              const selected = is("task", x.id);
              const related = !selected && ((sel?.kind === "order" && sel.id === x.order) || (!!selRobot && sel?.kind === "robot" && a?.agent === selRobot));
              return (
                <tr key={x.id} className={`${re ? "re" : ""} ${selected ? "sel" : related ? "rel" : ""}`} onClick={() => select(selected ? null : { kind: "task", id: x.id })}>
                  <td className="mono text-[11px]">{x.id}</td>
                  <td className="mono text-[11px] text-ink2">{x.order}</td>
                  <td>
                    {a ? (
                      <>
                        <AgentChip state={state} id={a.agent} selected={selRobot === a.agent} onClick={() => select({ kind: "robot", id: a.agent })} />
                        {re && <span className="ml-1 text-[10.5px] text-warn">↺ from {re}</span>}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    <Pri p={x.priority} />
                  </td>
                  <td>
                    <Badge cls={label}>{label}</Badge>
                  </td>
                  <td className="mono text-[11px] text-muted">{a ? `${a.plan_start.toFixed(0)}–${a.plan_end.toFixed(0)} s` : "—"}</td>
                  <td className="mono text-[11px]">{eta}</td>
                  <td className="text-ink2">{x.zone ?? ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default AllocationTable;
