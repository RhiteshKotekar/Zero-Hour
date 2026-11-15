"use client";

// Dedicated 3D Warehouse Simulation pop-out view.
// Provides an unobstructed full-screen 3D simulation experience synced with the main dashboard.
import { useEffect, useState, useRef } from "react";
import dynamic from "next/dynamic";
import { useClockDriver, useStore, useSimT } from "@/lib/store";
import { useLiveConnection } from "@/lib/live";
import { getPopoutChannel, broadcastClockSync, type PopoutMessage } from "@/lib/popoutSync";

const WarehouseView = dynamic(() => import("@/components/warehouse3d/WarehouseView"), {
  ssr: false,
  loading: () => (
    <div className="grid h-screen w-screen place-items-center bg-bg">
      <div className="flex flex-col items-center gap-3 text-muted">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-line2 border-t-accent" />
        <span className="cap">Loading 3D Simulation…</span>
      </div>
    </div>
  ),
});

const SPEEDS = [0.5, 1, 2, 5, 10];

export default function PopoutPage() {
  useClockDriver(10);
  const mode = useStore((s) => s.mode);
  const [liveParam] = useState(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("live") === "1");
  useLiveConnection(liveParam || mode === "live");

  const clock = useStore((s) => s.clock);
  const endT = useStore((s) => s.endT());
  const play = useStore((s) => s.play);
  const pause = useStore((s) => s.pause);
  const seek = useStore((s) => s.seek);
  const setSpeed = useStore((s) => s.setSpeed);
  const t = useSimT();

  const isScrubbingRef = useRef(false);

  // Initialize replay and popout communication
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const replayUrl = q.get("replay") ?? "/replays/judge_demo.json";

    if (q.get("live") !== "1") {
      useStore
        .getState()
        .loadReplay(replayUrl)
        .then(() => {
          const s = useStore.getState();
          if (q.get("speed")) s.setSpeed(Number(q.get("speed")));
          if (q.get("t")) s.seek(Number(q.get("t")));
          if (!q.get("paused")) s.play();
        })
        .catch((e) => console.error(e));
    }

    const channel = getPopoutChannel();
    channel?.postMessage({ type: "POPOUT_MOUNTED" });

    const handleMessage = (e: MessageEvent<PopoutMessage>) => {
      if (!e.data || !e.data.type) return;
      switch (e.data.type) {
        case "CLOSE_POPOUT":
          window.close();
          break;
        case "POPOUT_PING":
          channel?.postMessage({ type: "POPOUT_PONG" });
          break;
        case "CLOCK_SYNC": {
          if (isScrubbingRef.current) return;
          const s = useStore.getState();
          if (Math.abs(s.clock.t - e.data.t) > 1.5) {
            s.seek(e.data.t);
          }
          if (s.clock.playing !== e.data.playing) {
            if (e.data.playing) s.play();
            else s.pause();
          }
          if (s.clock.speed !== e.data.speed) {
            s.setSpeed(e.data.speed);
          }
          break;
        }
        case "SELECT_SYNC":
          useStore.getState().select(e.data.selection);
          break;
      }
    };

    channel?.addEventListener("message", handleMessage);

    const handleBeforeUnload = () => {
      channel?.postMessage({ type: "POPOUT_UNMOUNTED" });
      try {
        localStorage.setItem("zh_popout_status", JSON.stringify({ active: false, timestamp: Date.now() }));
      } catch {
        // ignore
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      handleBeforeUnload();
      channel?.removeEventListener("message", handleMessage);
      channel?.close();
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, []);

  const handlePlayToggle = () => {
    if (clock.playing) {
      pause();
      broadcastClockSync(clock.t, false, clock.speed);
    } else {
      play();
      broadcastClockSync(clock.t, true, clock.speed);
    }
  };

  const handleSpeedChange = (sp: number) => {
    setSpeed(sp);
    broadcastClockSync(clock.t, clock.playing, sp);
  };

  const handleSeek = (newT: number) => {
    seek(newT);
    broadcastClockSync(newT, clock.playing, clock.speed);
  };

  const handleCloseAndReturn = () => {
    const channel = getPopoutChannel();
    channel?.postMessage({ type: "POPOUT_UNMOUNTED" });
    try {
      localStorage.setItem("zh_popout_status", JSON.stringify({ active: false, timestamp: Date.now() }));
    } catch {
      // ignore
    }
    window.close();
  };

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-bg select-none">
      {/* 3D Scene */}
      <div className="absolute inset-0">
        <WarehouseView className="h-full w-full" hidePopout={true} />
      </div>

      {/* Floating Top Control Bar */}
      <div className="pointer-events-none absolute inset-x-0 top-3 z-30 flex justify-center px-4">
        <header className="pointer-events-auto flex items-center gap-3 rounded-2xl border border-line bg-panel/95 px-4 py-2 shadow-lg backdrop-blur-md">
          {/* Logo & Title */}
          <div className="flex items-center gap-2.5 pr-2 border-r border-line">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-ink text-white font-bold text-xs shadow-sm">
              Z
            </span>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-xs text-ink tracking-tight">Zero-Hour 3D</span>
                <span className="inline-flex items-center gap-1 rounded-full bg-samg-bg px-2 py-0.5 text-[9.5px] font-semibold text-samg">
                  <span className="h-1.5 w-1.5 rounded-full bg-samg" />
                  Standalone View
                </span>
              </div>
              <span className="text-[10px] text-muted">Synced with Control Dashboard</span>
            </div>
          </div>

          {/* Minimal Playback Controls */}
          <div className="flex items-center gap-2">
            <button
              onClick={handlePlayToggle}
              className={`btn ${clock.playing ? "primary" : ""} h-8 px-3 text-xs rounded-xl font-semibold flex items-center gap-1.5`}
            >
              {clock.playing ? (
                <>
                  <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
                    <rect x="6" y="4" width="4" height="16" rx="1" />
                    <rect x="14" y="4" width="4" height="16" rx="1" />
                  </svg>
                  <span>Pause</span>
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  <span>Play</span>
                </>
              )}
            </button>

            {/* Speeds */}
            <div className="seg">
              {SPEEDS.map((sp) => (
                <button
                  key={sp}
                  className={`text-[10.5px] py-1 px-2 ${clock.speed === sp ? "on" : ""}`}
                  onClick={() => handleSpeedChange(sp)}
                >
                  {sp}×
                </button>
              ))}
            </div>

            {/* Mini Timeline Scrubber */}
            <div className="flex items-center gap-2 px-2">
              <input
                type="range"
                min={0}
                max={endT || 100}
                step={0.5}
                value={t}
                onMouseDown={() => (isScrubbingRef.current = true)}
                onMouseUp={() => (isScrubbingRef.current = false)}
                onChange={(e) => handleSeek(Number(e.target.value))}
                className="w-32 h-1.5 bg-line rounded-lg appearance-none cursor-pointer accent-ink"
              />
              <span className="mono text-[11px] font-semibold text-ink w-16">
                t={Math.round(t)}s
              </span>
            </div>
          </div>

          {/* Close & Return to Dashboard Button */}
          <div className="pl-2 border-l border-line flex items-center gap-2">
            <button
              onClick={handleCloseAndReturn}
              className="btn flex items-center gap-1.5 h-8 px-3 text-xs rounded-xl font-semibold hover:bg-warn-bg hover:text-warn hover:border-warn/30 transition-all"
              title="Close this popout tab and reactivate simulation on the dashboard"
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="9 14 4 9 9 4" />
                <path d="M20 20v-7a4 4 0 0 0-4-4H4" />
              </svg>
              <span>Return to Dashboard</span>
            </button>
          </div>
        </header>
      </div>
    </div>
  );
}
