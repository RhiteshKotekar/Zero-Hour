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

export interface WarehouseViewProps {
  className?: string;
  /** hide the built-in overlay (camera buttons, toggles, legend, card) */
  bare?: boolean;
}

export function WarehouseView({ className, bare }: WarehouseViewProps) {
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
      {!bare && <Overlay />}
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

function Overlay() {
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
        <div className="pointer-events-auto flex flex-wrap items-center gap-1.5 rounded-[9px] border border-line bg-panel/90 p-1 shadow-sm backdrop-blur">
          <div className="seg">
            {CAM.map(([k, l]) => (
              <button key={k} className={k === "follow" && follow ? "on" : ""} onClick={() => cameraCommand(k)}>
                {k === "follow" && follow ? `Follow ${follow}` : l}
              </button>
            ))}
          </div>
          <span className="cap px-1">Focus</span>
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
        <div className="pointer-events-auto flex flex-wrap justify-end gap-1 rounded-[9px] border border-line bg-panel/90 p-1 shadow-sm backdrop-blur">
          {TOGGLES.map(([k, l]) => (
            <button key={k} className={`btn ${toggles[k] ? "on" : ""}`} onClick={() => toggle(k)}>
              {l}
            </button>
          ))}
        </div>
      </div>
      <div className="absolute right-2.5 top-14">
        <InfoCard state={state} />
      </div>
      <div className="pointer-events-auto absolute bottom-2.5 right-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[9px] border border-line bg-panel/90 px-2.5 py-1.5 text-[11px] shadow-sm backdrop-blur">
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
