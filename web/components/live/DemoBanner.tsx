"use client";
// Auto demo (plan §6.8): live = start the scripted `judge_demo` session and play; replay = play the recorded run.
// Phase banners come from derive.buildPhases (anchored to real events); each phase holds the clock briefly.
// <DemoBanner/> goes in the 3D overlay (it also runs the demo driver); <AutoDemoButton/> goes in the control bar.
import { clockAt } from "@/lib/derive";
import { useDemo, useDemoDriver, useLive } from "@/lib/live";
import { useStore } from "@/lib/store";

export interface DemoBannerProps {
  className?: string;
}

export function DemoBanner({ className }: DemoBannerProps) {
  useDemoDriver();
  const banner = useDemo((s) => s.banner);
  const total = useDemo((s) => s.total);
  const active = useDemo((s) => s.active);
  const holding = useDemo((s) => s.holdingUntil != null);
  const kind = useDemo((s) => s.kind);
  const state = useStore((s) => s.state);
  if (!banner || !state) return null;
  return (
    <div
      className={`pointer-events-auto w-[min(560px,calc(100%-24px))] rounded-[10px] border border-line bg-panel/95 px-4 py-3 shadow-[0_6px_24px_rgba(11,18,32,0.14)] backdrop-blur ${className ?? ""}`}
    >
      <div className="flex items-center gap-2">
        <span className="rounded-[5px] bg-ink px-1.5 py-0.5 text-[10px] font-bold text-white mono">
          {banner.n}/{total}
        </span>
        <span className="cap !text-samg">{banner.k}</span>
        <span className="ml-auto text-[10.5px] text-muted mono">
          {clockAt(state, banner.t)} · t={banner.t.toFixed(0)}s{kind ? ` · ${kind === "live" ? "LIVE" : "REPLAY"}` : ""}
        </span>
        <button className="ml-1 text-[13px] leading-none text-faint hover:text-ink" onClick={() => useDemo.getState().dismiss()} aria-label="Dismiss">
          ×
        </button>
      </div>
      <div className="mt-1 text-[14.5px] font-bold leading-snug">{banner.h}</div>
      {banner.p && <div className="mt-0.5 text-[12px] leading-snug text-ink2">{banner.p}</div>}
      {active && (
        <div className="mt-1.5 h-[3px] overflow-hidden rounded bg-line">
          <div className={`h-full bg-samg ${holding ? "pulse" : ""}`} style={{ width: `${(banner.n / Math.max(total, 1)) * 100}%` }} />
        </div>
      )}
    </div>
  );
}

export interface AutoDemoButtonProps {
  className?: string;
}

/** ◉ Auto demo toggle. Prefers live (backend online), falls back to the recorded run. */
export function AutoDemoButton({ className }: AutoDemoButtonProps) {
  const active = useDemo((s) => s.active);
  const backend = useLive((s) => s.backend);
  const starting = useLive((s) => s.starting);
  return (
    <button
      className={`btn ${active ? "on" : ""} ${className ?? ""}`}
      disabled={!!starting}
      title={backend === "offline" ? "Backend offline: plays the recorded run" : "Starts the scripted judge_demo live session"}
      onClick={() => (active ? useDemo.getState().stop() : void useDemo.getState().start())}
    >
      <span className={`inline-block h-[8px] w-[8px] rounded-full border-2 ${active ? "border-accent bg-accent pulse" : "border-ink2"}`} />
      {starting ? "Starting demo…" : active ? "Stop demo" : "Auto demo"}
    </button>
  );
}

export default DemoBanner;
