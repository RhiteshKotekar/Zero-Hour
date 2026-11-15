"use client";
// Zero-Hour Mission Control Center Page Shell
// Streamlined layout with proper whitespace, tabbed inspection, and no visual clutter.
import { useEffect, useState } from "react";
import { useClockDriver, useStore } from "@/lib/store";
import { useLiveConnection } from "@/lib/live";
import { useDashboardPopoutTracker } from "@/lib/popoutSync";
import { DemoDashboard } from "@/components/dashboard/DemoDashboard";
import { DetailedDashboard } from "@/components/dashboard/DetailedDashboard";

export default function Home() {
  useClockDriver(10);
  useDashboardPopoutTracker();
  const mode = useStore((s) => s.mode);
  const dashboardMode = useStore((s) => s.dashboardMode);
  const [liveParam] = useState(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("live") === "1");
  useLiveConnection(liveParam || mode === "live");

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("live") === "1") return;
    useStore
      .getState()
      .loadReplay(q.get("replay") ?? "/replays/judge_demo.json")
      .then(() => {
        const s = useStore.getState();
        if (q.get("speed")) s.setSpeed(Number(q.get("speed")));
        if (q.get("t")) s.seek(Number(q.get("t")));
        if (!q.get("paused")) s.play();
      })
      .catch((e) => console.error(e));
  }, []);

  return (
    <main className="h-screen w-screen overflow-hidden bg-bg">
      {dashboardMode === "detailed" ? (
        <div className="flex h-full w-full min-h-[820px] flex-col p-3">
          <DetailedDashboard />
        </div>
      ) : (
        <DemoDashboard />
      )}
    </main>
  );
}
