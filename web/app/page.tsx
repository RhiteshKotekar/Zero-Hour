"use client";
// Control center page shell (plan §6.4). Everything below is a function of (state, t) from the store.
// URL params: ?t=<s> seek · ?paused=1 · ?speed=<n> · ?replay=<url> (default /replays/judge_demo.json) ·
// ?live=1 enable the live connection (Phase 2-D `useLiveConnection`; it is also enabled whenever the store is in
// live mode, e.g. after SessionDrawer started a session).
import { useEffect, useState } from "react";
import { useClockDriver, useStore } from "@/lib/store";
import { useLiveConnection } from "@/lib/live";
import { Header } from "@/components/panels/Header";
import { ControlBar } from "@/components/panels/ControlBar";
import { PipelineStrip } from "@/components/panels/PipelineStrip";
import { KpiStrip } from "@/components/panels/KpiStrip";
import { MissionPanel } from "@/components/panels/MissionPanel";
import { TopologyPanel } from "@/components/panels/TopologyPanel";
import { Stage } from "@/components/shell/Stage";
import { BottomTabs } from "@/components/shell/BottomTabs";

export default function Home() {
  useClockDriver(10);
  const mode = useStore((s) => s.mode);
  // read once on the client (does not affect markup, so no hydration mismatch)
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
    <main className="flex h-screen min-h-[860px] flex-col gap-2 p-2.5">
      <Header />
      <ControlBar />
      <PipelineStrip />
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,68fr)_minmax(390px,32fr)] gap-2">
        <Stage />
        <div className="flex min-h-0 min-w-0 flex-col gap-2">
          <MissionPanel className="min-h-[150px] flex-[1]" />
          <TopologyPanel className="min-h-[200px] flex-[1.35]" />
        </div>
      </div>
      <KpiStrip />
      <BottomTabs className="h-[212px] flex-none" />
    </main>
  );
}
