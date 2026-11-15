"use client";

// Floating Bottom Control Island for Full-Screen 3D Demo Dashboard
import { useState, useRef, useEffect } from "react";
import { clockAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { useTwin } from "@/components/shell/ui";
import { openPopoutWindow } from "@/lib/popoutSync";

function fmtSec(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

export function DemoFloatingControls() {
  const { state, t } = useTwin();
  const playing = useStore((s) => s.clock.playing);
  const speed = useStore((s) => s.clock.speed);
  const togglePlay = useStore((s) => s.togglePlay);
  const step = useStore((s) => s.step);
  const reset = useStore((s) => s.reset);
  const seek = useStore((s) => s.seek);
  const setSpeed = useStore((s) => s.setSpeed);
  const toggles = useStore((s) => s.toggles);
  const toggle = useStore((s) => s.toggle);
  const view = useStore((s) => s.view);
  const setView = useStore((s) => s.setView);
  const follow = useStore((s) => s.follow);
  const setFollow = useStore((s) => s.setFollow);
  const cameraCommand = useStore((s) => s.cameraCommand);

  const [injectOpen, setInjectOpen] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const injectRef = useRef<HTMLDivElement>(null);
  const layersRef = useRef<HTMLDivElement>(null);

  const end = Math.max(state?.end_s ?? 0, 1);
  const progress = Math.min(Math.max(t / end, 0), 1);

  // Close menus on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (injectRef.current && !injectRef.current.contains(e.target as Node)) {
        setInjectOpen(false);
      }
      if (layersRef.current && !layersRef.current.contains(e.target as Node)) {
        setLayersOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    seek(val);
  };

  const handleInject = (kind: string) => {
    setInjectOpen(false);
    useStore.getState().pushToast("warn", `Injected simulated event: ${kind}`);
    // Jump forward slightly to see reaction if running
    if (!playing) step(5);
  };

  return (
    <div className="pointer-events-none absolute inset-x-4 bottom-5 z-30 flex items-center justify-center select-none">
      <div className="pointer-events-auto flex flex-col items-center gap-2 rounded-2xl border border-line/80 bg-white/92 p-2 shadow-2xl backdrop-blur-xl transition-all max-w-[880px] w-full">
        {/* Upper Row: Controls, Scrubber, Time, Actions */}
        <div className="flex w-full items-center gap-3 px-2">
          {/* Play/Pause Button */}
          <button
            onClick={togglePlay}
            className={`flex h-10 w-10 flex-none items-center justify-center rounded-xl text-white shadow-md transition-all hover:scale-105 active:scale-95 ${
              playing ? "bg-amber-600 hover:bg-amber-700 shadow-amber-600/20" : "bg-accent hover:bg-accent-hover shadow-accent/25"
            }`}
            title={playing ? "Pause Simulation (Space)" : "Run Simulation (Space)"}
          >
            {playing ? (
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="4" width="4" height="16" rx="1.5" />
                <rect x="14" y="4" width="4" height="16" rx="1.5" />
              </svg>
            ) : (
              <svg className="h-4 w-4 ml-0.5" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
            )}
          </button>

          {/* Step (+5s) Button */}
          <button
            onClick={() => step(5)}
            className="flex h-9 w-9 flex-none items-center justify-center rounded-xl border border-line bg-panel2 text-ink hover:bg-panel hover:border-line2 transition-all active:scale-95"
            title="Step forward +5 seconds"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="5 4 15 12 5 20 5 4" fill="currentColor" fillOpacity="0.2" />
              <line x1="19" y1="5" x2="19" y2="19" />
            </svg>
          </button>

          {/* Reset Button */}
          <button
            onClick={reset}
            className="flex h-9 w-9 flex-none items-center justify-center rounded-xl border border-line bg-panel2 text-ink hover:bg-panel hover:border-line2 transition-all active:scale-95"
            title="Reset to mission start"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="1 4 1 10 7 10" />
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
            </svg>
          </button>

          {/* Interactive Timeline Scrubber */}
          <div className="relative flex flex-1 items-center gap-3">
            <span className="mono text-[11px] font-bold text-muted w-16 text-right">
              {state ? clockAt(state, t) : "--:--:--"}
            </span>

            <div className="relative flex-1 group py-2">
              <input
                type="range"
                min={0}
                max={end}
                step={0.1}
                value={Math.min(t, end)}
                onChange={handleSeek}
                className="w-full accent-accent cursor-pointer h-2 bg-line rounded-lg appearance-none focus:outline-none"
              />
              <div
                className="pointer-events-none absolute top-1/2 -translate-y-1/2 left-0 h-2 bg-accent rounded-lg"
                style={{ width: `${progress * 100}%` }}
              />
            </div>

            <span className="mono text-[11px] font-semibold text-muted w-20">
              +{fmtSec(t)} / {fmtSec(end)}
            </span>
          </div>

          {/* Speed Multiplier Segment */}
          <div className="hidden sm:flex items-center rounded-xl border border-line bg-panel2 p-0.5">
            {[0.5, 1, 2, 5, 10].map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`rounded-lg px-2 py-1 text-[11px] font-bold transition-all ${
                  speed === s ? "bg-white text-ink shadow-xs" : "text-muted hover:text-ink"
                }`}
              >
                {s}×
              </button>
            ))}
          </div>

          <div className="h-5 w-px bg-line/80 mx-0.5" />

          {/* 3D Layers & Toggles Popover */}
          <div className="relative" ref={layersRef}>
            <button
              onClick={() => setLayersOpen(!layersOpen)}
              className={`flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-xs font-semibold transition-all ${
                layersOpen ? "border-accent bg-accent-bg text-accent" : "border-line bg-panel2 text-ink hover:bg-panel"
              }`}
              title="Toggle 3D visual layers"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="12 2 2 7 12 12 22 7 12 2" />
                <polyline points="2 17 12 22 22 17" />
                <polyline points="2 12 12 17 22 12" />
              </svg>
              <span>Layers</span>
            </button>

            {layersOpen && (
              <div className="absolute bottom-full right-0 mb-2 w-48 rounded-2xl border border-line bg-white/95 p-2 shadow-xl backdrop-blur-md z-50">
                <div className="text-[10px] font-bold uppercase tracking-wider text-muted px-2 py-1">
                  Simulation Overlays
                </div>
                <div className="flex flex-col gap-1 mt-1">
                  <label className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-panel2 cursor-pointer text-xs font-medium text-ink">
                    <span>Robot Routes</span>
                    <input
                      type="checkbox"
                      checked={toggles.routes}
                      onChange={() => toggle("routes")}
                      className="accent-accent"
                    />
                  </label>
                  <label className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-panel2 cursor-pointer text-xs font-medium text-ink">
                    <span>Labels & Pins</span>
                    <input
                      type="checkbox"
                      checked={toggles.labels}
                      onChange={() => toggle("labels")}
                      className="accent-accent"
                    />
                  </label>
                  <label className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-panel2 cursor-pointer text-xs font-medium text-ink">
                    <span>Congestion Heatmap</span>
                    <input
                      type="checkbox"
                      checked={toggles.congestion}
                      onChange={() => toggle("congestion")}
                      className="accent-accent"
                    />
                  </label>
                  <label className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-panel2 cursor-pointer text-xs font-medium text-ink">
                    <span>Coordination Graph</span>
                    <input
                      type="checkbox"
                      checked={toggles.coord}
                      onChange={() => toggle("coord")}
                      className="accent-accent"
                    />
                  </label>
                  <label className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-panel2 cursor-pointer text-xs font-medium text-ink">
                    <span>Visual Effects</span>
                    <input
                      type="checkbox"
                      checked={toggles.effects}
                      onChange={() => toggle("effects")}
                      className="accent-accent"
                    />
                  </label>
                </div>
              </div>
            )}
          </div>

          {/* Disruption Inject Menu */}
          <div className="relative" ref={injectRef}>
            <button
              onClick={() => setInjectOpen(!injectOpen)}
              className="flex items-center gap-1 rounded-xl border border-warn/30 bg-warn-bg px-2.5 py-1.5 text-xs font-bold text-warn hover:bg-warn-bg/80 transition-all active:scale-95"
            >
              <span>Inject</span>
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>

            {injectOpen && (
              <div className="absolute bottom-full right-0 mb-2 w-56 rounded-2xl border border-line bg-white/95 p-2 shadow-xl backdrop-blur-md z-50">
                <div className="text-[10px] font-bold uppercase tracking-wider text-muted px-2 py-1">
                  Inject Runtime Anomaly
                </div>
                <div className="flex flex-col gap-1 mt-1 text-xs font-medium">
                  <button
                    onClick={() => handleInject("Aisle 4 Congestion")}
                    className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-warn-bg text-ink hover:text-warn transition-colors"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-warn" />
                    Aisle 4 Obstacle
                  </button>
                  <button
                    onClick={() => handleInject("Robot R04 Motor Fault")}
                    className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-sec-bg text-ink hover:text-sec transition-colors"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-sec" />
                    Robot R04 Motor Failure
                  </button>
                  <button
                    onClick={() => handleInject("Byzantine Disputed Claim")}
                    className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-sec-bg text-ink hover:text-sec transition-colors"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-sec" />
                    ACP Byzantine Tampering
                  </button>
                  <button
                    onClick={() => handleInject("Urgent Priority Rush Order")}
                    className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-accent-bg text-ink hover:text-accent transition-colors"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                    Priority Rush Order
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Pop-Out 3D Window Button */}
          <button
            onClick={() => openPopoutWindow()}
            className="hidden lg:flex items-center gap-1.5 rounded-xl border border-line bg-panel2 px-2.5 py-1.5 text-xs font-semibold text-ink hover:bg-panel transition-all"
            title="Pop out 3D simulation to external tab"
          >
            <svg className="h-3.5 w-3.5 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
            <span>Pop Out</span>
          </button>
        </div>

        {/* Lower Row: Camera Presets, Follow Status, and Ops/Comms Toggle */}
        <div className="flex w-full flex-wrap items-center justify-between gap-2 border-t border-line/60 pt-1.5 px-2 text-[11px]">
          {/* Camera Controls */}
          <div className="flex items-center gap-1.5">
            <span className="text-muted">Camera:</span>
            <div className="flex rounded-lg border border-line bg-panel2 p-0.5">
              <button
                onClick={() => cameraCommand("iso")}
                className="rounded-md px-2 py-0.5 font-bold text-[10.5px] text-muted hover:text-ink hover:bg-white/60 transition-all"
                title="Perspective isometric view"
              >
                3D Iso
              </button>
              <button
                onClick={() => cameraCommand("top")}
                className="rounded-md px-2 py-0.5 font-bold text-[10.5px] text-muted hover:text-ink hover:bg-white/60 transition-all"
                title="Top-down orthographic view"
              >
                Top-Down
              </button>
              <button
                onClick={() => cameraCommand("reset")}
                className="rounded-md px-2 py-0.5 font-bold text-[10.5px] text-muted hover:text-ink hover:bg-white/60 transition-all"
                title="Reset camera zoom and angle"
              >
                Reset
              </button>
            </div>

            {follow && (
              <span className="flex items-center gap-1.5 rounded-md bg-accent-bg px-2 py-0.5 font-bold text-accent ml-1">
                Tracking {follow}
                <button
                  onClick={() => setFollow(null)}
                  className="hover:text-ink ml-0.5 font-normal text-xs"
                  title="Stop tracking"
                >
                  ✕
                </button>
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-muted mr-1">3D Mode:</span>
            <div className="flex rounded-lg border border-line bg-panel2 p-0.5">
              <button
                onClick={() => setView("ops")}
                className={`rounded-md px-2 py-0.5 font-bold text-[10.5px] transition-all ${
                  view === "ops" ? "bg-white text-accent shadow-2xs" : "text-muted hover:text-ink"
                }`}
              >
                Warehouse
              </button>
              <button
                onClick={() => setView("comms")}
                className={`rounded-md px-2 py-0.5 font-bold text-[10.5px] transition-all ${
                  view === "comms" ? "bg-white text-accent shadow-2xs" : "text-muted hover:text-ink"
                }`}
              >
                Comms Mesh
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default DemoFloatingControls;
