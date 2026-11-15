"use client";
// Small selection card over the 3D view. Values only; nothing is computed beyond (state, t) lookups.
import type { ReactNode } from "react";
import type { TwinState } from "@/lib/types";
import { ROLE_COLOR, STATUS_COLOR, assignmentAt, clockAt, congestionAt, robotAt, taskStateAt } from "@/lib/derive";
import { useSimT, useStore } from "@/lib/store";

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-[2px]">
      <span className="text-muted">{k}</span>
      <span className="mono text-right text-ink">{v}</span>
    </div>
  );
}

export function InfoCard({ state }: { state: TwinState }) {
  const sel = useStore((s) => s.selection);
  const select = useStore((s) => s.select);
  const follow = useStore((s) => s.follow);
  const setFollow = useStore((s) => s.setFollow);
  const cameraCommand = useStore((s) => s.cameraCommand);
  const t = useSimT();
  if (!sel || !["robot", "rack", "aisle"].includes(sel.kind)) return null;

  let title: ReactNode = sel.id;
  let sub = "";
  let body: ReactNode = null;

  if (sel.kind === "robot") {
    const r = state.robots.find((x) => x.id === sel.id);
    if (!r) return null;
    const p = robotAt(state, r.id, t);
    const task = p.task ? state.tasks.find((x) => x.id === p.task) : undefined;
    const ts = task ? taskStateAt(state, task.id, t) : null;
    const a = task ? assignmentAt(state, task.id, t) : null;
    title = (
      <span className="flex items-center gap-2">
        <i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: ROLE_COLOR[r.role] }} />
        {r.id}
      </span>
    );
    sub = r.label;
    body = (
      <>
        <Row k="Status" v={<b style={{ color: STATUS_COLOR[p.status] }}>{p.status}</b>} />
        <Row k="Task" v={task ? task.label : "—"} />
        {task && <Row k="Order" v={task.order} />}
        {ts && <Row k="Task state" v={ts.state.replace("_", " ")} />}
        {a && <Row k="Wave / plan" v={`W${a.wave} · ${a.plan_start.toFixed(0)}–${a.plan_end.toFixed(0)} s${a.reassigned_from ? ` · ↺ ${a.reassigned_from}` : ""}`} />}
        <Row k="Battery" v={`${Math.max(0, p.battery).toFixed(1)} %`} />
        <Row k="Odometer" v={`${Math.round(p.odo)} m`} />
        {r.failed_at != null && r.failed_at <= t && <Row k="Failed at" v={<b className="text-bad">{clockAt(state, r.failed_at)}</b>} />}
        <div className="mt-2 flex gap-1">
          <button className={`btn ${follow === r.id ? "on" : ""}`} onClick={() => (follow === r.id ? setFollow(null) : cameraCommand("follow"))}>
            {follow === r.id ? "Following" : "Follow"}
          </button>
          <button className="btn" onClick={() => cameraCommand("focusSelection")}>
            Focus
          </button>
        </div>
      </>
    );
  } else if (sel.kind === "rack") {
    const skus = state.inventory.filter((s) => s.rack === sel.id);
    title = `Rack ${sel.id}`;
    sub = `${skus.length} SKU locations`;
    body = (
      <div className="max-h-48 overflow-auto">
        {skus.map((s) => (
          <Row
            key={s.sku}
            k={`${s.sku} · ${s.name}`}
            v={<span className={s.stock === 0 ? "text-bad" : ""}>{s.stock === 0 ? "OUT" : `${s.stock}`} · {s.aisle}</span>}
          />
        ))}
      </div>
    );
  } else {
    const a = state.layout.aisles.find((x) => x.id === sel.id);
    if (!a) return null;
    const cong = congestionAt(state, t).find((c) => c.aisle === a.id);
    const [x0, y0, x1, y1] = a.rect;
    const inside = state.robots
      .filter((r) => r.mobile)
      .filter((r) => {
        const p = robotAt(state, r.id, t);
        return p.x >= x0 && p.x <= x1 + 1 && p.y >= y0 && p.y <= y1 + 1;
      })
      .map((r) => r.id);
    title = `Aisle ${a.id}`;
    sub = "Narrow aisle · single lane, exclusive lock";
    body = (
      <>
        <Row k="State" v={a.blocked ? <b className="text-bad">BLOCKED</b> : cong ? <b className="text-warn">CONGESTED</b> : "clear"} />
        <Row k="Inside" v={inside.join(", ") || "—"} />
        {cong && <Row k="Waiting" v={`${cong.entries.map((c) => `${c.robot}←${c.blockers.join("/")}`).join(", ")} · +${cong.remaining}s`} />}
        <Row k="Congestion events" v={state.congestion.filter((c) => c.aisle === a.id && c.t0 <= t).length} />
        <Row k="SKUs" v={state.inventory.filter((s) => s.aisle === a.id).map((s) => s.sku).join(", ") || "—"} />
      </>
    );
  }

  return (
    <div className="pointer-events-auto w-[280px] rounded-[10px] border border-line bg-panel/95 p-3 text-[12px] shadow-sm backdrop-blur">
      <div className="flex items-start justify-between">
        <div>
          <div className="cap">{sel.kind}</div>
          <div className="text-[14px] font-bold">{title}</div>
          {sub && <div className="text-[11px] text-muted">{sub}</div>}
        </div>
        <button className="text-muted hover:text-ink" onClick={() => select(null)} aria-label="Close">
          ✕
        </button>
      </div>
      <div className="mt-2 border-t border-line pt-2">{body}</div>
    </div>
  );
}
