"use client";

// Zero-Hour / SAMG — Completely Revamped Full-Screen Demo Dashboard
// Features edge-to-edge 3D warehouse digital twin with floating glass HUD controls
// and an on-demand collapsible telemetry & mission analytics drawer.
import { useState, useEffect } from "react";
import { Stage } from "@/components/shell/Stage";
import { DemoFloatingHeader } from "./DemoFloatingHeader";
import { DemoFloatingControls } from "./DemoFloatingControls";
import { DemoCollapsibleSidebar, SidebarSection } from "./DemoCollapsibleSidebar";
import { useStore } from "@/lib/store";

export function DemoDashboard() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeSection, setActiveSection] = useState<SidebarSection>("overview");

  // Automatically open the sidebar when a user selects a specific item in the 3D scene
  useEffect(() => {
    return useStore.subscribe((s, p) => {
      if (s.selection !== p.selection && s.selection) {
        if (s.selection.kind === "robot") {
          setActiveSection("fleet");
          setSidebarOpen(true);
        } else if (s.selection.kind === "order" || s.selection.kind === "task") {
          setActiveSection("orders");
          setSidebarOpen(true);
        } else if (s.selection.kind === "claim") {
          setActiveSection("security");
          setSidebarOpen(true);
        }
      }
    });
  }, []);

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-bg select-none">
      {/* Full-Screen 3D Warehouse Simulation Stage */}
      <Stage className="h-full w-full rounded-none border-0 shadow-none" bare={true} />

      {/* Floating Top Glass HUD */}
      <DemoFloatingHeader
        onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
        isSidebarOpen={sidebarOpen}
        activeSection={activeSection}
      />

      {/* Floating Bottom Island Simulation Controls */}
      <DemoFloatingControls />

      {/* Collapsible Telemetry & Analytics Slide-Over Sidebar */}
      <DemoCollapsibleSidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        activeSection={activeSection}
        onSelectSection={setActiveSection}
      />
    </div>
  );
}

export default DemoDashboard;
