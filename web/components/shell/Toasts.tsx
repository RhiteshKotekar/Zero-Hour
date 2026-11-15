"use client";
// Toasts for congestion / failure / replanning / security / dispatch as the clock passes those events.
// Fires only on forward progress of ≤ 30 sim-s (not on seeks), so scrubbing doesn't flood the screen.
import { useEffect, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import type { Selection, TwinEvent, TwinState } from "@/lib/types";

interface Toast {
  key: string;
  level: "warn" | "bad" | "sec" | "ok" | "samg";
  head: string;
  body: string;
  target: Selection | null;
}

function toastOf(e: TwinEvent): Omit<Toast, "key"> | null {
  const robot: Selection | null = e.robot ? { kind: "robot", id: e.robot } : null;
  if (e.title.startsWith("Congestion"))
    return { level: "warn", head: "Congestion alert", body: `${e.title.replace("Congestion at ", "")} · ${e.detail ?? ""}`, target: e.aisle ? { kind: "aisle", id: e.aisle } : robot };
  if (/ FAILED$/.test(e.title) && e.robot) return { level: "bad", head: "Robot failure", body: `${e.title} · ${e.detail ?? ""}`, target: robot };
  if (/ failed$/.test(e.title) && !e.title.startsWith("Witness"))
    return { level: "bad", head: "Task failure", body: `${e.title} · ${e.detail ?? ""}`, target: e.task ? { kind: "task", id: e.task } : robot };
  if (e.title === "Replanning") return { level: "samg", head: "Replanning", body: e.detail ?? "", target: null };
  if (e.level === "sec") return { level: "sec", head: "Security violation", body: `${e.title.replace(/^SECURITY: /, "")} · ${e.detail ?? ""}`, target: robot };
  if (/^Order .* dispatched/.test(e.title)) return { level: "ok", head: "Order dispatched", body: `${e.title.replace(" dispatched", "")} · ${e.detail ?? ""}`, target: e.order ? { kind: "order", id: e.order } : null };
  return null;
}

function eventsBetween(state: TwinState, t0: number, t1: number): TwinEvent[] {
  return state.events.filter((e) => e.t > t0 && e.t <= t1);
}

export function Toasts({ className }: { className?: string }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    let prevT = useStore.getState().clock.t;
    const unsub = useStore.subscribe((s) => {
      const t = s.clock.t;
      if (t === prevT) return;
      const dt = t - prevT;
      const from = prevT;
      prevT = t;
      if (!s.state || dt <= 0 || dt > 30) return;
      const fresh = eventsBetween(s.state, from, t)
        .map((e) => {
          const x = toastOf(e);
          return x ? { ...x, key: `${e.seq}` } : null;
        })
        .filter((x): x is Toast => !!x);
      if (!fresh.length) return;
      setToasts((cur) => [...cur, ...fresh].slice(-4));
      for (const f of fresh) {
        timers.current.push(window.setTimeout(() => setToasts((cur) => cur.filter((x) => x.key !== f.key)), 5000));
      }
    });
    const pending = timers.current;
    return () => {
      unsub();
      pending.forEach((id) => window.clearTimeout(id));
    };
  }, []);

  return (
    <div className={`pointer-events-none flex flex-col items-start gap-1.5 ${className ?? ""}`}>
      {toasts.map((x) => (
        <div
          key={x.key}
          className={`zh-toast ${x.level}`}
          onClick={() => {
            const s = useStore.getState();
            if (x.target) {
              s.select(x.target);
              s.cameraCommand("focusSelection");
            }
            setToasts((cur) => cur.filter((y) => y.key !== x.key));
          }}
        >
          <b>{x.head}</b>
          {x.body}
        </div>
      ))}
    </div>
  );
}

export default Toasts;
