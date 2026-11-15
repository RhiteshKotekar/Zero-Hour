"use client";
// Bottom tabs (plan §6.4): Allocation · Security · Events · Fleet · Provenance. Selecting a claim switches to
// Security; badges show time-revealed counts.
import { useEffect, useState } from "react";
import { claimsAt, failedRobotsAt, visibleEvents, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { AllocationTable } from "@/components/panels/AllocationTable";
import { SecurityPipeline } from "@/components/panels/SecurityPipeline";
import { EventStream } from "@/components/panels/EventStream";
import { FleetList } from "@/components/panels/FleetList";
import { ProvenancePanel } from "@/components/panels/ProvenancePanel";
import { useTwin } from "./ui";

type Tab = "alloc" | "sec" | "events" | "fleet" | "prov";

export function BottomTabs({ className }: { className?: string }) {
  const { state, t } = useTwin();
  const [tab, setTab] = useState<Tab>("alloc");

  // a claim selected anywhere (e.g. a toast) opens the Security tab
  useEffect(
    () =>
      useStore.subscribe((s, p) => {
        if (s.selection !== p.selection && s.selection?.kind === "claim") setTab("sec");
      }),
    [],
  );

  const disputed = state ? claimsAt(state, t).filter((c) => c.evidence === "DISPUTED").length : 0;
  const failed = state ? failedRobotsAt(state, t).length : 0;
  const nEvents = state ? visibleEvents(state, t).length : 0;
  const w = state ? waveAt(state, t) : null;
  const tabs: [Tab, string, React.ReactNode][] = [
    ["alloc", "Task allocation", w ? <span className="n">{w.tasks.length}</span> : null],
    ["sec", "Assurance · security", disputed ? <span className="n sec">{disputed}</span> : null],
    ["events", "Event stream", <span key="n" className="n">{nEvents}</span>],
    ["fleet", "Fleet", failed ? <span className="n bad">{failed} down</span> : null],
    ["prov", "Provenance", null],
  ];
  return (
    <section className={`zh-card ${className ?? ""}`}>
      <div className="flex flex-none items-center border-b border-line px-3 py-1 bg-panel2/70 gap-1.5 overflow-x-auto no-scrollbar">
        {tabs.map(([k, label, badge]) => (
          <button key={k} className={`zh-tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>
            {label}
            {badge}
          </button>
        ))}
        <span className="ml-auto pr-2 text-[11px] font-medium text-muted">
          {tab === "sec" ? "signed claim → signature → witness → ACP → learning" : tab === "fleet" ? "status · task · battery · odometer" : ""}
        </span>
      </div>
      <div className="min-h-0 flex-1">
        {tab === "alloc" && <AllocationTable />}
        {tab === "sec" && <SecurityPipeline />}
        {tab === "events" && <EventStream />}
        {tab === "fleet" && <FleetList />}
        {tab === "prov" && <ProvenancePanel />}
      </div>
    </section>
  );
}

export default BottomTabs;
