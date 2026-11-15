"use client";
// TEMPORARY (Phase 2-D screenshot route) — delete after checking.
import { useEffect } from "react";
import { CommsView } from "@/components/comms/CommsView";
import { DemoBanner, AutoDemoButton } from "@/components/live/DemoBanner";
import { SessionDrawer } from "@/components/live/SessionDrawer";
import { InjectMenu } from "@/components/live/InjectMenu";
import { LiveStatus } from "@/components/live/LiveStatus";
import { useLiveConnection, useDemo } from "@/lib/live";
import { useClockDriver, useStore } from "@/lib/store";

export default function Preview() {
  useClockDriver(10);
  useLiveConnection(true);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("replay")) {
      useStore.getState().loadReplay("/replays/judge_demo.json").then(() => {
        const s = useStore.getState();
        s.seek(Number(q.get("t") ?? 0));
        if (q.get("demo")) void useDemo.getState().start("replay");
      });
    }
  }, []);
  return (
    <main className="flex h-screen flex-col gap-2 p-2">
      <div className="flex items-center gap-2"><SessionDrawer /><AutoDemoButton /><LiveStatus /><InjectMenu /></div>
      <div className="relative flex-1">
        <CommsView />
        <div className="absolute left-1/2 top-24 z-20 -translate-x-1/2"><DemoBanner /></div>
      </div>
    </main>
  );
}
