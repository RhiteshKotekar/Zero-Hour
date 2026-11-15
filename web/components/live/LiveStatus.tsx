"use client";
// Connection indicator: LIVE (attached, WS open) · REPLAY · backend offline. Data from lib/live `useLive`.
import { useLive } from "@/lib/live";
import { useStore } from "@/lib/store";

export function LiveStatus({ className }: { className?: string }) {
  const status = useLive((s) => s.status);
  const backend = useLive((s) => s.backend);
  const attached = useLive((s) => s.attached);
  const mode = useStore((s) => s.mode);
  const planning = useStore((s) => s.state?.live?.planning);
  const live = mode === "live" && attached;
  const [dot, text, cls] = live
    ? status === "open"
      ? ["bg-bad pulse", `LIVE${planning === "running" ? " · wave running" : ""}`, "text-ink"]
      : ["bg-warn", "LIVE · reconnecting…", "text-warn"]
    : backend === "offline"
      ? ["bg-faint", "REPLAY · backend offline", "text-muted"]
      : ["bg-samg", backend === "online" ? "REPLAY · backend online" : "REPLAY", "text-ink"];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-[7px] border border-line bg-panel2 px-2.5 py-1 text-[11px] font-bold ${cls} ${className ?? ""}`}>
      <span className={`inline-block h-[7px] w-[7px] rounded-full ${dot}`} />
      {text}
    </span>
  );
}

export default LiveStatus;
