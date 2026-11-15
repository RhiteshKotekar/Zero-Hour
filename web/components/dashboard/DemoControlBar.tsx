"use client";

// Demo Simulation Control Bar
// Streamlined toolbar with prominent playback controls, timeline scrubber, and disruption triggers.
import { useRef } from "react";
import { clockAt, visibleEvents } from "@/lib/derive";
import { control, type ControlAction } from "@/lib/api";
import { useStore } from "@/lib/store";
import { useTwin } from "@/components/shell/ui";
import { SessionDrawer } from "@/components/live/SessionDrawer";
import { InjectMenu } from "@/components/live/InjectMenu";
import { openPopoutWindow } from "@/lib/popoutSync";

const SPEEDS = [0.5, 1, 2, 5, 10];

function liveControl(action: ControlAction, value?: number) {
  control(action, value)
    .then((r) => r?.clock && useStore.getState().applyServerClock(r.clock))
    .catch((e) => console.warn(`control ${action}:`, e));
}

export function DemoControlBar({ className }: { className?: string }) {
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
    <div
      className={`flex flex-wrap items-center gap-2.5 rounded-2xl border border-line bg-panel px-3.5 py-2 shadow-sm ${
        className ?? ""
      }`}
    >
      {/* Session Manager Drawer */}
      <SessionDrawer />

      {/* Primary Play/Pause Button */}
      <button
        type="button"
        className={`btn primary flex items-center justify-center gap-2 px-4 py-1.5 font-bold shadow-xs transition-all ${
          playing ? "!bg-amber-600 hover:!bg-amber-700 !border-amber-600" : ""
        }`}
        onClick={onPlay}
        disabled={!state}
        title={playing ? "Pause simulation" : "Start or resume simulation"}
      >
        {playing ? (
          <>
            <svg className="h-3.5 w-3.5 fill-current" viewBox="0 0 24 24">
              <rect x="6" y="4" width="4" height="16" rx="1" />
              <rect x="14" y="4" width="4" height="16" rx="1" />
            </svg>
            <span>Pause</span>
          </>
        ) : atEnd ? (
          <>
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
            </svg>
            <span>Replay</span>
          </>
        ) : (
          <>
            <svg className="h-3.5 w-3.5 fill-current" viewBox="0 0 24 24">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            <span>{t > 0 ? "Resume" : "Start"}</span>
          </>
        )}
      </button>

      {/* Step +5s */}
      <button
        type="button"
        className="btn"
        onClick={onStep}
        disabled={!state}
        title="Advance 5 simulated seconds"
      >
        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="5 4 15 12 5 20 5 4" />
          <line x1="19" y1="5" x2="19" y2="19" />
        </svg>
        <span>+5s</span>
      </button>

      {/* Reset */}
      <button
        type="button"
        className="btn"
        onClick={onReset}
        disabled={!state}
        title={live ? "Restart live session with initial parameters" : "Reset simulation to t = 0"}
      >
        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
          <path d="M3 3v5h5" />
        </svg>
        <span>Reset</span>
      </button>

      {/* Speed Multipliers */}
      <div className="seg">
        {SPEEDS.map((v) => (
          <button
            key={v}
            type="button"
            className={v === speed ? "on" : ""}
            onClick={() => onSpeed(v)}
            title={`Run simulation at ${v}x speed`}
          >
            {v}×
          </button>
        ))}
      </div>

      {/* Interactive Timeline Scrubber */}
      <div className="flex-1 min-w-[200px]">
        <Timeline end={end} t={t} seekable={!live} />
      </div>

      {/* Digital Clock & Elapsed Time */}
      <div className="flex items-center gap-1.5 rounded-xl border border-line bg-panel2/60 px-3 py-1 text-ink shadow-2xs">
        <svg className="h-3.5 w-3.5 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <polyline points="12 6 12 12 16 14" />
        </svg>
        <span className="mono text-[12px] font-bold">
          {state ? clockAt(state, t) : "--:--:--"}
        </span>
        <span className="text-muted text-[10.5px]">
          ({t.toFixed(0)}s)
        </span>
      </div>

      {/* Inject Disruption Menu */}
      <InjectMenu />

      {/* View Switcher: OPS (Warehouse) / COMMS (Network) */}
      <div className="seg">
        <button
          type="button"
          className={view === "ops" ? "on" : ""}
          onClick={() => s().setView("ops")}
          title="Physical Warehouse 3D Digital Twin"
        >
          Warehouse 3D
        </button>
        <button
          type="button"
          className={view === "comms" ? "on" : ""}
          onClick={() => s().setView("comms")}
          title="Agent Communication & Witness Network Graph"
        >
          Network Graph
        </button>
      </div>

      {/* Pop Out 3D Map Button */}
      <button
        type="button"
        className="btn flex items-center gap-1.5 text-accent hover:border-accent/40 hover:bg-accent-bg"
        onClick={() => openPopoutWindow()}
        title="Open 3D map in a standalone pop-out tab"
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
          <polyline points="15 3 21 3 21 9" />
          <line x1="10" y1="14" x2="21" y2="3" />
        </svg>
        <span>Pop Out</span>
      </button>
    </div>
  );
}

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
    ? visibleEvents(state, t).filter(
        (e) =>
          e.level === "bad" ||
          e.level === "sec" ||
          e.title.startsWith("Congestion") ||
          e.title === "Replanning"
      )
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
      title={seekable ? "Drag or click to seek simulation time" : "Live mode: Server controls clock"}
    >
      <div className="track" />
      <div className="fill" style={{ width: pc(t) }} />
      {waves.map((w) => (
        <div
          key={w.number}
          className={`band ${w.status === "preview" ? "preview" : ""}`}
          style={{ left: pc(w.t0), width: `max(calc(${pc(w.t1 - w.t0)} - 2px), 1.5%)` }}
        >
          {w.number === 1 ? "WAVE 1" : "REPLAN W2"} · {w.mission_id}
        </div>
      ))}
      {marks.map((e) => (
        <div
          key={e.seq}
          className="mk"
          title={`${e.title} at ${e.t.toFixed(0)}s`}
          style={{
            left: pc(e.t),
            background:
              e.level === "sec"
                ? "var(--sec)"
                : e.title.startsWith("Congestion")
                ? "var(--warn)"
                : "var(--bad)",
          }}
        />
      ))}
      <div className="head" style={{ left: pc(t) }} />
    </div>
  );
}

export default DemoControlBar;
