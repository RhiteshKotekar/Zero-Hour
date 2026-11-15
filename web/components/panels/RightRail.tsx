"use client";
// Right Rail: Tabbed inspector housing Missions & Orders, Coordination Topology, and Fleet Telemetry.
import { useState } from "react";
import { topoLabel, waveAt } from "@/lib/derive";
import { useTwin } from "@/components/shell/ui";
import { MissionPanel } from "./MissionPanel";
import { TopologyPanel } from "./TopologyPanel";
import { FleetList } from "./FleetList";

export type RightRailTab = "mission" | "topology" | "fleet";

export interface RightRailProps {
  className?: string;
}

export function RightRail({ className }: RightRailProps) {
  const [tab, setTab] = useState<RightRailTab>("mission");
  const { state, t } = useTwin();

  const w = state ? waveAt(state, t) : null;
  const orders = state?.orders.filter((o) => (o.arrival_s ?? 0) <= t) ?? [];
  const wavesCount = state?.waves.length ?? 0;
  const robots = state?.robots.filter((r) => r.physical) ?? [];
  const failedCount = robots.filter((r) => r.failed_at != null && r.failed_at <= t).length;

  return (
    <section className={`zh-card flex flex-col min-h-0 ${className ?? ""}`}>
      {/* Top Tab Bar */}
      <div className="flex flex-none items-center border-b border-line bg-panel px-2">
        <button
          className={`zh-tab ${tab === "mission" ? "on" : ""}`}
          onClick={() => setTab("mission")}
        >
          Missions & Orders
          <span className="n">{wavesCount} waves · {orders.length} orders</span>
        </button>

        <button
          className={`zh-tab ${tab === "topology" ? "on" : ""}`}
          onClick={() => setTab("topology")}
        >
          Topology
          <span className="n">{w ? topoLabel(w.topology) : "—"}</span>
        </button>

        <button
          className={`zh-tab ${tab === "fleet" ? "on" : ""}`}
          onClick={() => setTab("fleet")}
        >
          Fleet
          {failedCount > 0 ? (
            <span className="n bad">{failedCount} down</span>
          ) : (
            <span className="n">{robots.length}</span>
          )}
        </button>
      </div>

      {/* Tab Content Body with full vertical height */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === "mission" && <MissionPanel bare className="h-full" />}
        {tab === "topology" && <TopologyPanel bare className="h-full" />}
        {tab === "fleet" && (
          <div className="flex flex-col h-full min-h-0">
            <div className="flex flex-none items-center justify-between border-b border-line bg-panel2/60 px-3.5 py-1.5">
              <span className="text-[11px] font-semibold text-muted">
                {robots.length} physical AMRs in fleet · Click to select in 3D · Double click to follow
              </span>
            </div>
            <div className="flex-1 min-h-0">
              <FleetList className="p-2" />
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export default RightRail;
