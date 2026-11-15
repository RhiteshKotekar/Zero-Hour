"use client";
// Pipeline strip & lifecycle viewer: Shows the end-to-end mission stages from Warehouse setup to Bandit Learning.
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
    <div className={`zh-scroll flex h-full flex-col p-3.5 ${className ?? ""}`}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-semibold text-muted">
          SAMG End-to-End Orchestration Pipeline · 11 Stages from Scenario to Guarded Learning
        </span>
        <span className="text-[10.5px] font-mono text-muted">
          Active: <b className="text-ink">{active.toUpperCase()}</b>
        </span>
      </div>

      <div className="grid grid-cols-11 gap-2 min-h-0 flex-1">
        {STAGES.map(([k, label, cls], idx) => {
          const isDone = seen.has(k);
          const isActive = k === active;
          const ev = lastOf[k];
          const stepNum = String(idx + 1).padStart(2, "0");

          return (
            <div
              key={k}
              className={`flex flex-col justify-between rounded-xl border p-2.5 transition-all text-left ${
                isActive
                  ? "border-accent bg-accent-bg/60 shadow-xs"
                  : isDone
                  ? "border-line bg-panel hover:bg-panel2"
                  : "border-line/60 bg-panel2/40 opacity-60"
              }`}
              title={ev?.detail ?? label}
            >
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="mono text-[9px] font-bold text-muted">#{stepNum}</span>
                  <span
                    className={`h-2 w-2 rounded-full ${
                      isActive ? "bg-accent pulse" : isDone ? "bg-ok" : "bg-line2"
                    }`}
                  />
                </div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-muted line-clamp-1">
                  {label}
                </div>
              </div>

              <div className="mt-2 min-w-0">
                <div className="text-[11px] font-bold text-ink truncate">
                  {k === "wh"
                    ? state
                      ? `${state.layout.width}×${state.layout.height}m`
                      : "—"
                    : ev?.title ?? "Pending"}
                </div>
                <div className="mt-0.5 text-[10px] text-muted line-clamp-2 leading-tight">
                  {k === "wh"
                    ? `${robots} physical robots`
                    : ev?.detail ? ev.detail.slice(0, 60) : "Awaiting stage trigger"}
                </div>
              </div>

              <div className="mt-2 pt-1.5 border-t border-line/60 flex items-center justify-between text-[9.5px]">
                <span className={`font-semibold ${isActive ? "text-accent" : isDone ? "text-ok" : "text-muted"}`}>
                  {isActive ? "ACTIVE" : isDone ? "DONE" : "WAITING"}
                </span>
                {ev && <span className="mono text-muted">t={ev.t.toFixed(0)}s</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default PipelineStrip;
