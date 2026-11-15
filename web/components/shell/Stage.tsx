"use client";
// Centre stage: 3D operations view or 3D comms view (store `view`), plus overlay slots
// (DemoBanner from Phase 2-D at the top, toasts bottom-left). The 3D view keeps its own camera/legend overlay.
import dynamic from "next/dynamic";
import { useStore } from "@/lib/store";
import { DemoBanner } from "@/components/live/DemoBanner";
import { Toasts } from "./Toasts";

const WarehouseView = dynamic(() => import("@/components/warehouse3d/WarehouseView"), {
  ssr: false,
  loading: () => <div className="grid h-full w-full place-items-center bg-bg cap">Loading 3D…</div>,
});
const CommsView = dynamic(() => import("@/components/comms/CommsView"), {
  ssr: false,
  loading: () => <div className="grid h-full w-full place-items-center bg-bg cap">Loading comms view…</div>,
});

export function Stage({ className }: { className?: string }) {
  const view = useStore((s) => s.view);
  return (
    <section className={`relative min-h-0 min-w-0 overflow-hidden rounded-[10px] border border-line bg-panel ${className ?? ""}`}>
      <div className="absolute inset-0">{view === "comms" ? <CommsView /> : <WarehouseView />}</div>
      <div className="pointer-events-none absolute inset-x-0 top-14 z-20 flex justify-center px-3">
        <div className="pointer-events-auto w-full max-w-[760px]">
          <DemoBanner />
        </div>
      </div>
      <Toasts className="absolute bottom-2.5 left-2.5 z-20" />
    </section>
  );
}

export default Stage;
