"use client";
// Bottom tabs: Assurance · Security, Task Allocation, Event Stream, Pipeline Lifecycle, and Provenance.
// Supports collapsing to maximize 3D stage and right rail vertical space.
import { useEffect, useState } from "react";
import { claimsAt, visibleEvents, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { AllocationTable } from "@/components/panels/AllocationTable";
import { SecurityPipeline } from "@/components/panels/SecurityPipeline";
import { EventStream } from "@/components/panels/EventStream";
import { PipelineStrip } from "@/components/panels/PipelineStrip";
import { ProvenancePanel } from "@/components/panels/ProvenancePanel";
import { useTwin } from "./ui";

export type BottomTab = "sec" | "alloc" | "events" | "pipeline" | "prov";

export function BottomTabs({ className }: { className?: string }) {
  const { state, t } = useTwin();
  const [tab, setTab] = useState<BottomTab>("sec");
  const [collapsed, setCollapsed] = useState(false);

  // a claim selected anywhere (e.g. a toast) opens the Security tab and expands
  useEffect(
    () =>
      useStore.subscribe((s, p) => {
        if (s.selection !== p.selection && s.selection?.kind === "claim") {
          setTab("sec");
          setCollapsed(false);
        }
      }),
    [],
  );

  const disputed = state ? claimsAt(state, t).filter((c) => c.evidence === "DISPUTED").length : 0;
  const nEvents = state ? visibleEvents(state, t).length : 0;
  const w = state ? waveAt(state, t) : null;

  const tabs: [BottomTab, string, React.ReactNode][] = [
    ["sec", "Assurance · Security", disputed ? <span className="n sec">{disputed} disputed</span> : null],
    ["alloc", "Task Allocation", w ? <span className="n">{w.tasks.length}</span> : null],
    ["events", "Event Stream", <span key="n" className="n">{nEvents}</span>],
    ["pipeline", "Mission Pipeline", null],
    ["prov", "Provenance", null],
  ];

  return (
    <section className={`zh-card transition-all duration-200 ${collapsed ? "h-[42px]" : "h-[224px]"} ${className ?? ""}`}>
      {/* Tab Header Bar */}
      <div className="flex flex-none items-center border-b border-line px-2 bg-panel">
        <div className="flex items-center">
          {tabs.map(([k, label, badge]) => (
            <button
              key={k}
              className={`zh-tab ${tab === k ? "on" : ""}`}
              onClick={() => {
                setTab(k);
                if (collapsed) setCollapsed(false);
              }}
            >
              {label}
              {badge}
            </button>
          ))}
        </div>

        {/* Subtitle helper / Status */}
        <span className="ml-auto pr-3 text-[11px] text-muted hidden sm:inline">
          {tab === "sec"
            ? "signed claim → signature → witness → ACP → learning"
            : tab === "pipeline"
            ? "11-stage vertical execution lifecycle"
            : ""}
        </span>

        {/* Collapse / Expand Toggle */}
        <button
          className="zh-chip my-1 flex items-center gap-1 font-semibold"
          onClick={() => setCollapsed(!collapsed)}
          title={collapsed ? "Expand detailed telemetry drawer" : "Collapse drawer to maximize 3D floor view"}
        >
          {collapsed ? "▲ Expand" : "▼ Collapse"}
        </button>
      </div>

      {/* Tab Panel Body (hidden when collapsed) */}
      {!collapsed && (
        <div className="min-h-0 flex-1 overflow-hidden">
          {tab === "sec" && <SecurityPipeline />}
          {tab === "alloc" && <AllocationTable />}
          {tab === "events" && <EventStream />}
          {tab === "pipeline" && <PipelineStrip />}
          {tab === "prov" && <ProvenancePanel />}
        </div>
      )}
    </section>
  );
}

export default BottomTabs;
