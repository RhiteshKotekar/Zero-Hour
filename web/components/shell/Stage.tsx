"use client";
// Centre stage: 3D operations view or 3D comms view (store `view`), plus overlay slots
// (DemoBanner from Phase 2-D at the top, toasts bottom-left). The 3D view keeps its own camera/legend overlay.
import dynamic from "next/dynamic";
import { useStore } from "@/lib/store";
import { DemoBanner } from "@/components/live/DemoBanner";
import { Toasts } from "./Toasts";
import { closePopoutWindow } from "@/lib/popoutSync";

const WarehouseView = dynamic(() => import("@/components/warehouse3d/WarehouseView"), {
  ssr: false,
  loading: () => <div className="grid h-full w-full place-items-center bg-bg cap">Loading 3D…</div>,
});
const CommsView = dynamic(() => import("@/components/comms/CommsView"), {
  ssr: false,
  loading: () => <div className="grid h-full w-full place-items-center bg-bg cap">Loading comms view…</div>,
});

export interface StageProps {
  className?: string;
  bare?: boolean;
}

export function Stage({ className, bare }: StageProps) {
  const view = useStore((s) => s.view);
  const isPopoutActive = useStore((s) => s.isPopoutActive);

  return (
    <section className={`relative min-h-0 min-w-0 overflow-hidden rounded-2xl border border-line bg-panel shadow-sm ${className ?? ""}`}>
      <div className="absolute inset-0">
        {isPopoutActive ? (
          <div className="flex h-full w-full flex-col items-center justify-center p-8 text-center bg-panel2/80 backdrop-blur-sm select-none">
            <div className="relative mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-bg border border-accent/25 text-accent shadow-sm">
              <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                <line x1="12" y1="22.08" x2="12" y2="12" />
              </svg>
              <span className="absolute -top-1 -right-1 flex h-4 w-4">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-ok opacity-75"></span>
                <span className="relative inline-flex rounded-full h-4 w-4 bg-ok border-2 border-white"></span>
              </span>
            </div>

            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-ok-bg text-ok text-[11.5px] font-semibold mb-2.5 border border-ok/25">
              <span className="w-2 h-2 rounded-full bg-ok pulse"></span>
              Simulation Active in Pop-out Tab
            </div>

            <h3 className="text-base font-bold text-ink mb-1.5">3D Map View Popped Out</h3>
            <p className="text-muted text-xs max-w-md mb-6 leading-relaxed">
              The 3D warehouse digital twin is running in an external tab. Simulation rendering on this dashboard is deactivated to save resources. Close the pop-out tab or click below to restore.
            </p>

            <button
              onClick={() => closePopoutWindow()}
              className="btn primary flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold shadow-sm hover:scale-[1.02] active:scale-[0.98] transition-all"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="9 14 4 9 9 4" />
                <path d="M20 20v-7a4 4 0 0 0-4-4H4" />
              </svg>
              Restore 3D Simulation Here
            </button>
          </div>
        ) : view === "comms" ? (
          <CommsView />
        ) : (
          <WarehouseView bare={bare} />
        )}
      </div>

      {!isPopoutActive && (
        <div className="pointer-events-none absolute inset-x-0 top-14 z-20 flex justify-center px-3">
          <div className="pointer-events-auto w-full max-w-[760px]">
            <DemoBanner />
          </div>
        </div>
      )}

      <Toasts className="absolute bottom-2.5 left-2.5 z-20" />
    </section>
  );
}

export default Stage;
