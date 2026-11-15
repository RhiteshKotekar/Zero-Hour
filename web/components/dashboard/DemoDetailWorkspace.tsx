"use client";

// Demo Dashboard Collapsible Information Workspace
// Hosts the deep technical telemetry tabs (Task Allocation, Security Assurance, Event Stream, Pipeline, Provenance)
// in an expandable drawer so the 3D warehouse remains the primary visual focal point.
import { useState, useEffect, useCallback } from "react";
import { claimsAt, visibleEvents, waveAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { useTwin } from "@/components/shell/ui";
import { AllocationTable } from "@/components/panels/AllocationTable";
import { SecurityPipeline } from "@/components/panels/SecurityPipeline";
import { EventStream } from "@/components/panels/EventStream";
import { ProvenancePanel } from "@/components/panels/ProvenancePanel";
import { PipelineStrip } from "@/components/panels/PipelineStrip";

export type DetailTab = "alloc" | "sec" | "events" | "pipeline" | "prov";

export interface DemoDetailWorkspaceProps {
  className?: string;
  defaultTab?: DetailTab;
  tab?: DetailTab;
  onTabChange?: (tab: DetailTab) => void;
  isExpanded?: boolean;
  onToggleExpanded?: (expanded: boolean) => void;
}

export function DemoDetailWorkspace({
  className,
  defaultTab = "alloc",
  tab: controlledTab,
  onTabChange,
  isExpanded: controlledExpanded,
  onToggleExpanded,
}: DemoDetailWorkspaceProps) {
  const { state, t } = useTwin();
  const [internalTab, setInternalTab] = useState<DetailTab>(defaultTab);
  const [internalExpanded, setInternalExpanded] = useState(false);

  const tab = controlledTab ?? internalTab;
  const setTab = useCallback((nextTab: DetailTab) => {
    if (onTabChange) onTabChange(nextTab);
    else setInternalTab(nextTab);
  }, [onTabChange]);

  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded;
  const toggleExpanded = useCallback((val: boolean) => {
    if (onToggleExpanded) onToggleExpanded(val);
    else setInternalExpanded(val);
  }, [onToggleExpanded]);

  // If a security claim is selected anywhere in the app, switch to the Security tab and expand
  useEffect(() => {
    return useStore.subscribe((s, p) => {
      if (s.selection !== p.selection && s.selection?.kind === "claim") {
        setTab("sec");
        toggleExpanded(true);
      }
    });
  }, [setTab, toggleExpanded]);

  const disputed = state ? claimsAt(state, t).filter((c) => c.evidence === "DISPUTED").length : 0;
  const nEvents = state ? visibleEvents(state, t).length : 0;
  const w = state ? waveAt(state, t) : null;

  const tabs: [DetailTab, string, React.ReactNode][] = [
    ["alloc", "Task Allocation Matrix", w ? <span className="n">{w.tasks.length}</span> : null],
    ["sec", "Cryptographic Assurance & ACP", disputed ? <span className="n sec">{disputed}</span> : <span className="n ok">✓</span>],
    ["events", "Real-Time Event Stream", <span key="n" className="n">{nEvents}</span>],
    ["pipeline", "Mission Governance Pipeline", null],
    ["prov", "Provenance & Audit Trail", null],
  ];

  return (
    <section className={`flex flex-col rounded-2xl border border-line bg-panel shadow-sm overflow-hidden transition-all duration-300 ${className ?? ""}`}>
      {/* Header & Tab Selector Bar */}
      <div className="flex flex-wrap items-center justify-between border-b border-line bg-panel2/70 px-3 py-1.5 gap-2">
        {/* Left: Tab Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar">
          {tabs.map(([k, label, badge]) => (
            <button
              key={k}
              type="button"
              onClick={() => {
                setTab(k);
                if (!isExpanded) toggleExpanded(true);
              }}
              className={`zh-tab ${tab === k && isExpanded ? "on" : ""}`}
            >
              <span>{label}</span>
              {badge}
            </button>
          ))}
        </div>

        {/* Right: Expand/Collapse Toggle Button */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-medium text-muted hidden sm:inline">
            {tab === "sec"
              ? "Signed Claim → Signature Gate → Witness Corroboration → ACP"
              : tab === "alloc"
              ? "CP-SAT Constraint Solver & Route Plan"
              : tab === "events"
              ? "Chronological System & Robot Transitions"
              : "Decisions & Governance Log"}
          </span>

          <button
            type="button"
            onClick={() => toggleExpanded(!isExpanded)}
            className="flex items-center gap-1.5 rounded-full border border-line bg-white px-3 py-1 text-xs font-bold text-ink shadow-2xs hover:bg-panel2 transition-all"
            title={isExpanded ? "Collapse details to maximize 3D simulation area" : "Expand detailed operational and cryptographic logs"}
          >
            <span>{isExpanded ? "Hide Details" : "Show Details"}</span>
            <svg
              className={`h-3.5 w-3.5 transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        </div>
      </div>

      {/* Expandable Content Area */}
      {isExpanded && (
        <div className="h-[240px] overflow-hidden min-h-0 bg-white">
          {tab === "alloc" && <AllocationTable />}
          {tab === "sec" && <SecurityPipeline />}
          {tab === "events" && <EventStream />}
          {tab === "pipeline" && (
            <div className="p-3 overflow-auto h-full">
              <div className="text-xs font-bold text-muted uppercase tracking-wider mb-2">
                11-Stage Mission Governance Lifecycle
              </div>
              <PipelineStrip />
              <div className="mt-3 text-[11.5px] text-muted leading-relaxed">
                SAMG enforces end-to-end mission verification: Customer order ingestion → Feature extraction → Adaptive LinUCB topology decision → CP-SAT task allocation → Autonomous execution → Physical witness corroboration → Cryptographic ACP verification → Guarded policy update.
              </div>
            </div>
          )}
          {tab === "prov" && <ProvenancePanel />}
        </div>
      )}
    </section>
  );
}

export default DemoDetailWorkspace;
