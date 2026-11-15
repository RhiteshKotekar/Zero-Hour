"use client";
// Pipeline strip (plan §6.4): Warehouse → Orders → Mission → Topology → Allocation → Execution → Disruption →
// Witness → ACP → Reward → Learning. A stage is "done" once an event of that stage is visible; the active stage is
// the stage of the latest non-move event.
import { STAGES, indexOf, visibleEvents } from "@/lib/derive";
import type { TwinEvent } from "@/lib/types";
import { useTwin } from "@/components/shell/ui";

export interface PipelineStripProps {
  className?: string;
}

export function PipelineStrip({ className }: PipelineStripProps) {
  const { state, t } = useTwin();
  const vis = state ? visibleEvents(state, t) : [];
  const stages = state ? indexOf(state).stages : [];
  const seen = new Set<string>(["wh"]);
  const lastOf: Record<string, TwinEvent> = {};
  let active = "wh";
  vis.forEach((e, i) => {
    const st = stages[i];
    seen.add(st);
    lastOf[st] = e;
    if (e.level !== "move") active = st;
  });
  const robots = state ? state.robots.filter((r) => r.physical).length : 0;
  return (
    <div className={`flex gap-1 overflow-hidden rounded-[10px] border border-line bg-panel px-2 py-1.5 ${className ?? ""}`}>
      {STAGES.map(([k, label, cls]) => (
        <div key={k} className={`zh-st ${cls} ${seen.has(k) ? "done" : ""} ${k === active ? "active" : ""}`} title={lastOf[k]?.detail ?? ""}>
          <label>{label}</label>
          <b>{k === "wh" ? (state ? `${state.layout.width}×${state.layout.height} m · ${robots} robots` : "—") : lastOf[k]?.title ?? "—"}</b>
        </div>
      ))}
    </div>
  );
}

export default PipelineStrip;
