"use client";

// Detailed Operational Dashboard
// Preserves the comprehensive multi-panel layout with all deep telemetry, pipelines, and tables.
import { Header } from "@/components/panels/Header";
import { ControlBar } from "@/components/panels/ControlBar";
import { KpiStrip } from "@/components/panels/KpiStrip";
import { RightRail } from "@/components/panels/RightRail";
import { Stage } from "@/components/shell/Stage";
import { BottomTabs } from "@/components/shell/BottomTabs";

export function DetailedDashboard() {
  return (
    <div className="flex flex-1 min-h-0 flex-col gap-2.5">
      <Header />
      <ControlBar />
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,67fr)_minmax(400px,33fr)] gap-2.5">
        <Stage />
        <RightRail />
      </div>
      <KpiStrip />
      <BottomTabs className="flex-none" />
    </div>
  );
}

export default DetailedDashboard;
