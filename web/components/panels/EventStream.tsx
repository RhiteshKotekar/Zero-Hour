"use client";
// Live event stream (plan §6.6) with filter chips; only events with t ≤ now. Click an event to select what it
// refers to (claim › robot › task › order); a security event also flies the camera to the robot.
import { useState } from "react";
import { LEVEL_COLOR, clockAt, visibleEvents } from "@/lib/derive";
import { useStore } from "@/lib/store";
import type { Selection, TwinEvent } from "@/lib/types";
import { useSel, useTwin } from "@/components/shell/ui";

export interface EventStreamProps {
  className?: string;
}

const FILTERS: [key: string, label: string][] = [
  ["key", "Key"],
  ["samg", "SAMG"],
  ["robots", "Robots"],
  ["alerts", "Alerts"],
  ["security", "Security"],
  ["all", "All"],
];

const passes = (f: string, e: TwinEvent) =>
  f === "all"
    ? true
    : f === "key"
      ? e.level !== "move" && !/ started /.test(e.title) && !/^Witness verified/.test(e.title)
      : f === "samg"
        ? e.level === "samg"
        : f === "robots"
          ? (e.level === "move" || / started /.test(e.title) || !!e.robot) && e.level !== "sec"
          : f === "alerts"
            ? e.level === "warn" || e.level === "bad"
            : e.level === "sec" || /^ACP|^Secure|update/.test(e.title);

function targetOf(e: TwinEvent): Selection | null {
  if (e.level === "sec" && e.robot) return { kind: "robot", id: e.robot };
  if (e.claim) return { kind: "claim", id: e.claim };
  if (e.robot) return { kind: "robot", id: e.robot };
  if (e.task) return { kind: "task", id: e.task };
  if (e.order) return { kind: "order", id: e.order };
  if (e.aisle) return { kind: "aisle", id: e.aisle };
  return null;
}

export function EventStream({ className }: EventStreamProps) {
  const { state, t } = useTwin();
  const { sel } = useSel();
  const [filter, setFilter] = useState("key");
  const [picked, setPicked] = useState<number | null>(null);
  if (!state) return <div className="zh-empty">Loading…</div>;
  const vis = visibleEvents(state, t);
  const shown = vis.filter((e) => passes(filter, e)).slice(-150).reverse();
  const related = (e: TwinEvent) =>
    !!sel &&
    ((sel.kind === "robot" && e.robot === sel.id) ||
      (sel.kind === "task" && e.task === sel.id) ||
      (sel.kind === "order" && e.order === sel.id) ||
      (sel.kind === "claim" && e.claim === sel.id));

  const onClick = (e: TwinEvent) => {
    const s = useStore.getState();
    setPicked(e.seq);
    const target = targetOf(e);
    s.select(target);
    if (e.level === "sec" && target) s.cameraCommand("focusSelection");
  };

  return (
    <div className={`flex h-full min-h-0 flex-col ${className ?? ""}`}>
      <div className="flex flex-none items-center gap-2 border-b border-line px-3 py-1">
        <span className="text-[11px] text-muted">
          {vis.length} events · {clockAt(state, t)}
        </span>
        <div className="ml-auto flex gap-1">
          {FILTERS.map(([k, l]) => (
            <span key={k} className={`zh-chip ${k === filter ? "on" : ""}`} onClick={() => setFilter(k)}>
              {l}
            </span>
          ))}
        </div>
      </div>
      <div className="zh-scroll flex-1">
        {shown.map((e) => (
          <div
            key={e.seq}
            className={`zh-ev ${e.level} ${picked === e.seq && related(e) ? "sel" : related(e) ? "!bg-[#f4f8ff]" : ""}`}
            onClick={() => onClick(e)}
          >
            <span className="t">{clockAt(state, e.t)}</span>
            <i style={{ background: LEVEL_COLOR[e.level] }} />
            <div className="min-w-0">
              <b>{e.title}</b>
              {e.detail && <span className="d"> · {e.detail}</span>}
            </div>
          </div>
        ))}
        {!shown.length && <div className="zh-empty">No events yet — press Start.</div>}
      </div>
    </div>
  );
}

export default EventStream;
