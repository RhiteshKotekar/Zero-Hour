"use client";

// Floating Bottom Control Island for Full-Screen 3D Demo Dashboard
import { useState, useRef, useEffect } from "react";
import { clockAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { useTwin } from "@/components/shell/ui";
import { openPopoutWindow } from "@/lib/popoutSync";
import { LiveDock, liveInject } from "@/components/live/LiveDock";

const TONE = {
  bad: { row: "hover:bg-bad-bg hover:text-bad", dot: "bg-bad" },
  sec: { row: "hover:bg-sec-bg hover:text-sec", dot: "bg-sec" },
  warn: { row: "hover:bg-warn-bg hover:text-warn", dot: "bg-warn" },
} as const;

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

  const handleInject = (req: Parameters<typeof liveInject>[0], label: string) => {
    setInjectOpen(false);
    void liveInject(req, label);
  };

  return (
    <div className="pointer-events-none absolute inset-x-4 bottom-5 z-30 flex items-center justify-center select-none text-ink">
      <div className="pointer-events-auto flex flex-col items-center gap-2.5 rounded-3xl border border-line bg-panel/95 p-3 shadow-2xl backdrop-blur-2xl transition-all max-w-[920px] w-full">
        {/* Upper Row: Controls, Scrubber, Time, Actions */}
        <div className="flex w-full items-center gap-3.5 px-2">
          {/* Play/Pause Button */}
          <button
            onClick={togglePlay}
            className={`flex h-11 w-11 flex-none items-center justify-center rounded-2xl text-white shadow-md transition-all hover:scale-105 active:scale-95 ${
              playing ? "bg-amber-600 hover:bg-amber-700 shadow-amber-600/25" : "bg-accent hover:bg-accent-hover shadow-accent/25"
            }`}
            title={playing ? "Pause Simulation (Space)" : "Run Simulation (Space)"}
          >
            {playing ? (
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="4" width="4" height="16" rx="1.5" />
                <rect x="14" y="4" width="4" height="16" rx="1.5" />
              </svg>
            ) : (
              <svg className="h-5 w-5 ml-0.5" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
            )}
          </button>

          {/* Step (+5s) Button */}
          <button
            onClick={() => step(5)}
            className="flex h-10 w-10 flex-none items-center justify-center rounded-2xl border border-line bg-panel2 text-ink hover:bg-panel hover:border-line2 transition-all active:scale-95 shadow-2xs"
            title="Step forward +5 seconds"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="5 4 15 12 5 20 5 4" fill="currentColor" fillOpacity="0.2" />
              <line x1="19" y1="5" x2="19" y2="19" />
            </svg>
          </button>

          {/* Reset Button */}
          <button
            onClick={reset}
            className="flex h-10 w-10 flex-none items-center justify-center rounded-2xl border border-line bg-panel2 text-ink hover:bg-panel hover:border-line2 transition-all active:scale-95 shadow-2xs"
            title="Reset to mission start"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="1 4 1 10 7 10" />
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
            </svg>
          </button>

          {/* Interactive Timeline Scrubber */}
          <div className="relative flex flex-1 items-center gap-3">
            <span className="mono text-sm font-black text-ink w-20 text-right">
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

            <span className="mono text-xs font-bold text-muted w-28">
              +{fmtSec(t)} / {fmtSec(end)}
            </span>
          </div>

          {/* Speed Multiplier Segment */}
          <div className="hidden sm:flex items-center rounded-2xl border border-line bg-panel2 p-0.5">
            {[0.5, 1, 2, 5, 10].map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`rounded-xl px-2.5 py-1 text-xs font-black transition-all ${
                  speed === s ? "bg-panel text-ink shadow-xs" : "text-muted hover:text-ink"
                }`}
              >
                {s}×
              </button>
            ))}
          </div>

          <div className="h-6 w-px bg-line mx-0.5" />

          {/* 3D Layers & Toggles Popover */}
          <div className="relative" ref={layersRef}>
            <button
              onClick={() => setLayersOpen(!layersOpen)}
              className={`flex items-center gap-1.5 rounded-2xl border px-3 py-2 text-xs font-bold transition-all ${
                layersOpen ? "border-accent bg-accent-bg text-accent" : "border-line bg-panel2 text-ink hover:bg-panel"
              }`}
              title="Toggle 3D visual layers"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="12 2 2 7 12 12 22 7 12 2" />
                <polyline points="2 17 12 22 22 17" />
                <polyline points="2 12 12 17 22 12" />
              </svg>
              <span>Layers</span>
            </button>

            {layersOpen && (
              <div className="absolute bottom-full right-0 mb-3 w-52 rounded-3xl border border-line bg-panel/95 p-3 shadow-2xl backdrop-blur-2xl z-50 text-ink">
                <div className="text-xs font-black uppercase tracking-wider text-muted px-2 py-1">
                  Simulation Overlays
                </div>
                <div className="flex flex-col gap-1 mt-1.5">
                  <label className="flex items-center justify-between rounded-xl px-2.5 py-2 hover:bg-panel2 cursor-pointer text-xs font-semibold text-ink">
                    <span>Robot Routes</span>
                    <input
                      type="checkbox"
                      checked={toggles.routes}
                      onChange={() => toggle("routes")}
                      className="accent-accent"
                    />
                  </label>
                  <label className="flex items-center justify-between rounded-xl px-2.5 py-2 hover:bg-panel2 cursor-pointer text-xs font-semibold text-ink">
                    <span>Labels & Pins</span>
                    <input
                      type="checkbox"
                      checked={toggles.labels}
                      onChange={() => toggle("labels")}
                      className="accent-accent"
                    />
                  </label>
                  <label className="flex items-center justify-between rounded-xl px-2.5 py-2 hover:bg-panel2 cursor-pointer text-xs font-semibold text-ink">
                    <span>Congestion Heatmap</span>
                    <input
                      type="checkbox"
                      checked={toggles.congestion}
                      onChange={() => toggle("congestion")}
                      className="accent-accent"
                    />
                  </label>
                  <label className="flex items-center justify-between rounded-xl px-2.5 py-2 hover:bg-panel2 cursor-pointer text-xs font-semibold text-ink">
                    <span>Coordination Graph</span>
                    <input
                      type="checkbox"
                      checked={toggles.coord}
                      onChange={() => toggle("coord")}
                      className="accent-accent"
                    />
                  </label>
                  <label className="flex items-center justify-between rounded-xl px-2.5 py-2 hover:bg-panel2 cursor-pointer text-xs font-semibold text-ink">
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
              className="flex items-center gap-1.5 rounded-2xl border border-warn/30 bg-warn-bg px-3 py-2 text-xs font-black text-warn hover:bg-warn-bg/80 transition-all active:scale-95"
            >
              <span>Inject</span>
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>

            {injectOpen && (
              <div className="absolute bottom-full right-0 mb-3 w-60 rounded-3xl border border-line bg-panel/95 p-3 shadow-2xl backdrop-blur-2xl z-50 text-ink">
                <div className="text-xs font-black uppercase tracking-wider text-muted px-2 py-1">
                  Inject Runtime Anomaly
                </div>
                <div className="flex flex-col gap-1 mt-1.5 text-xs font-bold">
                  {([
                    [{ kind: "robot_failure", robot: "auto:AISLE" }, "Robot fails inside an aisle", "bad", "blocks its aisle cell; robots behind it reroute"],
                    [{ kind: "robot_failure", robot: "auto:TRANSPORT" }, "Transport robot failure", "bad", "its work is re-planned at the wave end"],
                    [{ kind: "malicious_report", robot: "auto:PICK" }, "Malicious completion report", "sec", "signed false claims; witness + ACP reject them"],
                    [{ kind: "aisle_blockage", aisle: "AI-4" }, "Aisle AI-4 blocked", "warn", "affects waves planned after it"],
                    [{ kind: "comm_failure" }, "Communication failure", "warn", "lossy network for later waves"],
                  ] as const).map(([req, label, tone, hint]) => (
                    <button
                      key={label}
                      onClick={() => handleInject(req, label)}
                      className={`flex items-start gap-2.5 rounded-xl px-2.5 py-2 text-left text-ink transition-colors ${TONE[tone].row}`}
                    >
                      <span className={`mt-1 h-2 w-2 flex-none rounded-full ${TONE[tone].dot}`} />
                      <span>
                        {label}
                        <span className="block text-[10px] font-medium text-muted">{hint}</span>
                      </span>
                    </button>
                  ))}
                  <div className="px-2.5 pt-1 text-[10px] font-medium text-muted">Live sessions only — press L to go live.</div>
                </div>
              </div>
            )}
          </div>

          {/* Pop-Out 3D Window Button */}
          <button
            onClick={() => openPopoutWindow()}
            className="hidden lg:flex items-center gap-2 rounded-2xl border border-line bg-panel2 px-3 py-2 text-xs font-bold text-ink hover:bg-panel transition-all shadow-2xs"
            title="Pop out 3D simulation to external tab"
          >
            <svg className="h-4 w-4 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
            <span>Pop Out</span>
          </button>
        </div>

        {/* Lower Row: Camera Presets, Follow Status, and Ops/Comms Toggle */}
        <div className="flex w-full flex-wrap items-center justify-between gap-3 border-t border-line/60 pt-2 px-2 text-xs">
          <LiveDock />
          {/* Camera Controls */}
          <div className="flex items-center gap-2">
            <span className="text-muted font-medium">Camera:</span>
            <div className="flex rounded-lg border border-line bg-panel2 p-0.5">
              <button
                onClick={() => cameraCommand("iso")}
                className="rounded-md px-2.5 py-1 font-bold text-xs text-muted hover:text-ink hover:bg-white/70 transition-all"
                title="Perspective isometric view"
              >
                3D Iso
              </button>
              <button
                onClick={() => cameraCommand("top")}
                className="rounded-md px-2.5 py-1 font-bold text-xs text-muted hover:text-ink hover:bg-white/70 transition-all"
                title="Top-down orthographic view"
              >
                Top-Down
              </button>
              <button
                onClick={() => cameraCommand("reset")}
                className="rounded-md px-2.5 py-1 font-bold text-xs text-muted hover:text-ink hover:bg-white/70 transition-all"
                title="Reset camera zoom and angle"
              >
                Reset
              </button>
            </div>

            {follow && (
              <span className="flex items-center gap-1.5 rounded-md bg-accent-bg px-2.5 py-1 font-bold text-accent ml-1 text-xs">
                Tracking {follow}
                <button
                  onClick={() => setFollow(null)}
                  className="hover:text-ink ml-1 font-normal text-xs"
                  title="Stop tracking"
                >
                  ✕
                </button>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-muted font-medium">3D Scene:</span>
            <div className="flex rounded-lg border border-line bg-panel2 p-0.5">
              <button
                onClick={() => setView("ops")}
                className={`rounded-md px-3 py-1 font-bold text-xs transition-all ${
                  view === "ops" ? "bg-white text-accent shadow-2xs font-extrabold" : "text-muted hover:text-ink"
                }`}
              >
                Warehouse
              </button>
              <button
                onClick={() => setView("comms")}
                className={`rounded-md px-3 py-1 font-bold text-xs transition-all ${
                  view === "comms" ? "bg-white text-accent shadow-2xs font-extrabold" : "text-muted hover:text-ink"
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
