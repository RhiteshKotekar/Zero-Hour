"use client";
// Control bar (plan §6.4): Session ▾ │ ▶ ❚❚ ⏭ ↻ │ speeds │ timeline (waves, markers) │ clock │ Inject ▾ │ OPS | COMMS.
// Replay: the browser owns the clock (store). Live: actions go to the backend (lib/api `control`, Phase 2-D).
import { useRef } from "react";
import { clockAt, visibleEvents } from "@/lib/derive";
import { control, type ControlAction } from "@/lib/api";
import { useStore } from "@/lib/store";
import { useTwin } from "@/components/shell/ui";
import { SessionDrawer } from "@/components/live/SessionDrawer";
import { InjectMenu } from "@/components/live/InjectMenu";

export interface ControlBarProps {
  className?: string;
}

const SPEEDS = [0.5, 1, 2, 5, 10];

function liveControl(action: ControlAction, value?: number) {
  control(action, value)
    .then((r) => r?.clock && useStore.getState().applyServerClock(r.clock))
    .catch((e) => console.warn(`control ${action}:`, e));
}

export function ControlBar({ className }: ControlBarProps) {
  const { state, t } = useTwin();
  const mode = useStore((s) => s.mode);
  const playing = useStore((s) => s.clock.playing);
  const speed = useStore((s) => s.clock.speed);
  const view = useStore((s) => s.view);
  const live = mode === "live";
  const end = state ? (live ? Math.max(state.end_s, t, 1) : Math.max(state.end_s, 1)) : 1;
  const atEnd = !live && state != null && t >= end - 1e-3;

  const s = () => useStore.getState();
  const onPlay = () => (live ? liveControl(playing ? "pause" : "play") : s().togglePlay());
  const onStep = () => {
    if (live) return liveControl("step", 5);
    s().pause();
    s().seek(s().clock.t + 5);
  };
  const onReset = () => {
    if (live) return liveControl("reset");
    s().pause();
    s().seek(0);
    s().select(null);
  };
  const onSpeed = (v: number) => (live ? liveControl("speed", v) : s().setSpeed(v));

  return (
    <div className={`flex items-center gap-2 rounded-[10px] border border-line bg-panel px-3 py-1.5 ${className ?? ""}`}>
      <SessionDrawer />
      <button className="btn primary w-[92px] justify-center" onClick={onPlay} disabled={!state}>
        {playing ? "❚❚ Pause" : atEnd ? "↻ Replay" : t > 0 ? "▶ Resume" : "▶ Start"}
      </button>
      <button className="btn" onClick={onStep} disabled={!state} title="advance 5 simulated seconds">
        ⏭ Step
      </button>
      <button className="btn" onClick={onReset} disabled={!state} title={live ? "new session with the same parameters" : "back to t = 0"}>
        ↻ Reset
      </button>
      <div className="seg">
        {SPEEDS.map((v) => (
          <button key={v} className={v === speed ? "on" : ""} onClick={() => onSpeed(v)}>
            {v}×
          </button>
        ))}
      </div>
      <Timeline end={end} t={t} seekable={!live} />
      <span className="mono min-w-[150px] text-right text-[12.5px] font-semibold">
        {state ? clockAt(state, t) : "--:--:--"} <span className="text-muted">· t={t.toFixed(0)}s</span>
      </span>
      <InjectMenu />
      <div className="seg">
        <button className={view === "ops" ? "on" : ""} onClick={() => s().setView("ops")} style={{ fontFamily: "var(--font-sans)" }}>
          OPS
        </button>
        <button className={view === "comms" ? "on" : ""} onClick={() => s().setView("comms")} style={{ fontFamily: "var(--font-sans)" }}>
          COMMS
        </button>
      </div>
    </div>
  );
}

/** Wave bands + marker ticks, revealed by time (only waves/events with t ≤ now). Drag to seek (replay). */
function Timeline({ end, t, seekable }: { end: number; t: number; seekable: boolean }) {
  const state = useStore((s) => s.state);
  const ref = useRef<HTMLDivElement>(null);
  const seekAt = (x: number) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r || !seekable) return;
    useStore.getState().seek(((x - r.left) / r.width) * end);
  };
  const pc = (v: number) => `${Math.max(0, Math.min(100, (v / end) * 100))}%`;
  const waves = state ? state.waves.filter((w) => w.t0 <= t) : [];
  const marks = state
    ? visibleEvents(state, t).filter((e) => e.level === "bad" || e.level === "sec" || e.title.startsWith("Congestion") || e.title === "Replanning")
    : [];
  return (
    <div
      ref={ref}
      className="zh-tl"
      style={{ cursor: seekable ? "pointer" : "default" }}
      onPointerDown={(e) => {
        if (!seekable) return;
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
        seekAt(e.clientX);
      }}
      onPointerMove={(e) => e.buttons === 1 && seekAt(e.clientX)}
      title={seekable ? "click or drag to seek" : "live: the server owns the clock"}
    >
      <div className="track" />
      <div className="fill" style={{ width: pc(t) }} />
      {waves.map((w) => (
        <div
          key={w.number}
          className={`band ${w.status === "preview" ? "preview" : ""}`}
          style={{ left: pc(w.t0), width: `max(calc(${pc(w.t1 - w.t0)} - 2px), 1%)` }}
        >
          {w.number === 1 ? "MISSION" : "REPLAN"} {w.mission_id}
          {w.status === "preview" ? " · preview" : ""}
        </div>
      ))}
      {marks.map((e) => (
        <div
          key={e.seq}
          className="mk"
          title={`${e.title} · t=${e.t.toFixed(0)}s`}
          style={{
            left: pc(e.t),
            background: e.level === "sec" ? "var(--sec)" : e.title.startsWith("Congestion") ? "var(--warn)" : "var(--bad)",
          }}
        />
      ))}
      <div className="head" style={{ left: pc(t) }} />
    </div>
  );
}

export default ControlBar;
