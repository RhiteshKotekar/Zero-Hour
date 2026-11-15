"use client";
// 3D operations view (plan §6.5): canvas + overlay (camera buttons, layer toggles, legend, selection card).
// Import with next/dynamic({ ssr: false }) — WebGL/canvas are client-only.
import { Canvas } from "@react-three/fiber";
import { ROLE_COLOR, STATUS_COLOR, congestionAt, failedRobotsAt } from "@/lib/derive";
import { useSimT, useStore, type CameraCommandKind, type Toggles } from "@/lib/store";
import { WarehouseScene } from "./Scene";
import { InfoCard } from "./InfoCard";
import { isoView } from "./CameraRig";
import { labelPortal } from "./labelPortal";
import { openPopoutWindow } from "@/lib/popoutSync";

export interface WarehouseViewProps {
  className?: string;
  /** hide the built-in overlay (camera buttons, toggles, legend, card) */
  bare?: boolean;
  /** hide the popout button (e.g. when already inside the popout window) */
  hidePopout?: boolean;
}

export function WarehouseView({ className, bare, hidePopout }: WarehouseViewProps) {
  const state = useStore((s) => s.state);
  const select = useStore((s) => s.select);
  const labels = useStore((s) => s.toggles.labels);
  if (!state) {
    return (
      <div className={`grid h-full w-full place-items-center bg-bg ${className ?? ""}`}>
        <span className="cap">Loading warehouse…</span>
      </div>
    );
  }
  const iso = isoView(state);
  return (
    <div className={`relative h-full w-full overflow-hidden bg-bg ${labels ? "" : "labels-off"} ${className ?? ""}`}>
      <Canvas
        shadows="percentage"
        dpr={[1, 2]}
        gl={{ antialias: true, powerPreference: "high-performance" }}
        camera={{ position: iso.pos.toArray(), fov: 36, near: 0.3, far: 250 }}
        onPointerMissed={() => select(null)}
      >
        <WarehouseScene state={state} />
      </Canvas>
      <div ref={labelPortal} className="pointer-events-none absolute inset-0 z-0 overflow-hidden" />
      {!bare && <Overlay hidePopout={hidePopout} />}
    </div>
  );
}

const CAM: [CameraCommandKind, string][] = [
  ["top", "Top"],
  ["iso", "3D"],
  ["follow", "Follow"],
  ["reset", "Reset"],
];
const TOGGLES: [keyof Toggles, string][] = [
  ["routes", "Routes"],
  ["labels", "Labels"],
  ["coord", "Coord graph"],
  ["effects", "Effects"],
  ["congestion", "Congestion"],
];

function Overlay({ hidePopout }: { hidePopout?: boolean }) {
  const state = useStore((s) => s.state)!;
  const cameraCommand = useStore((s) => s.cameraCommand);
  const follow = useStore((s) => s.follow);
  const toggles = useStore((s) => s.toggles);
  const toggle = useStore((s) => s.toggle);
  const selection = useStore((s) => s.selection);
  const t = useSimT();
  const congested = congestionAt(state, t).length > 0 || state.congestion.some((c) => c.t0 <= t);
  const failed = failedRobotsAt(state, t).length > 0;
  return (
    <div className="pointer-events-none absolute inset-0 z-10 p-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="pointer-events-auto flex flex-wrap items-center gap-1.5 rounded-full border border-line bg-panel/90 p-1 shadow-sm backdrop-blur-md">
          <div className="seg">
            {CAM.map(([k, l]) => (
              <button key={k} className={k === "follow" && follow ? "on" : ""} onClick={() => cameraCommand(k)}>
                {k === "follow" && follow ? `Follow ${follow}` : l}
              </button>
            ))}
          </div>
          <span className="cap px-1.5">Focus</span>
          <button className="btn" disabled={!selection} style={{ opacity: selection ? 1 : 0.45 }} onClick={() => cameraCommand("focusSelection")}>
            Selection
          </button>
          <button className="btn" disabled={!congested} style={{ opacity: congested ? 1 : 0.45 }} onClick={() => cameraCommand("focusCongestion")}>
            Congestion
          </button>
          <button className="btn" disabled={!failed} style={{ opacity: failed ? 1 : 0.45, color: failed ? "var(--bad)" : undefined }} onClick={() => cameraCommand("focusFailure")}>
            Failure
          </button>
        </div>
        <div className="flex items-center gap-2">
          <div className="pointer-events-auto flex flex-wrap justify-end gap-1 rounded-full border border-line bg-panel/90 p-1 shadow-sm backdrop-blur-md">
            {TOGGLES.map(([k, l]) => (
              <button key={k} className={`btn ${toggles[k] ? "on" : ""}`} onClick={() => toggle(k)}>
                {l}
              </button>
            ))}
          </div>
          {!hidePopout && (
            <button
              className="pointer-events-auto btn primary flex items-center gap-1.5 rounded-full py-1.5 px-3.5 text-[11.5px] font-semibold shadow-sm hover:brightness-110 active:scale-95 transition-all"
              title="Pop out 3D simulation to a separate tab"
              onClick={() => openPopoutWindow()}
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
              <span>Pop Out</span>
            </button>
          )}
        </div>
      </div>
      <div className="absolute right-2.5 top-14">
        <InfoCard state={state} />
      </div>
      <div className="pointer-events-auto absolute bottom-2.5 right-2.5 flex flex-wrap items-center gap-x-3.5 gap-y-1 rounded-full border border-line bg-panel/90 px-3.5 py-1.5 text-[11px] shadow-sm backdrop-blur-md">
        {(["picking", "transport", "packing", "dispatch"] as const).map((r) => (
          <span key={r} className="flex items-center gap-1.5">
            <i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: ROLE_COLOR[r] }} />
            <span className="capitalize text-ink2">{r}</span>
          </span>
        ))}
        <span className="h-3 w-px bg-line2" />
        {(["MOVING", "PICKING", "WAITING", "FAILED", "IDLE"] as const).map((s) => (
          <span key={s} className="flex items-center gap-1.5">
            <i className="inline-block h-2.5 w-2.5 rounded-full border-2" style={{ borderColor: STATUS_COLOR[s] }} />
            <span className="mono text-[10px] text-muted">{s}</span>
          </span>
        ))}
        <span className="h-3 w-px bg-line2" />
        <span className="flex items-center gap-1.5">
          <i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "#f59e0b" }} />
          <span className="text-ink2">SKU needed</span>
        </span>
      </div>
    </div>
  );
}

export default WarehouseView;
