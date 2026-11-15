"use client";
import { useEffect, useMemo, useRef } from "react";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import type { TwinState } from "@/lib/types";
import { taskStateAt } from "@/lib/derive";
import { useSimT } from "@/lib/store";
import { C } from "./palette";
import { Floor } from "./Floor";
import { Racks } from "./Racks";
import { Structures } from "./Structures";
import { Robots } from "./Robots";
import { Routes } from "./Routes";
import { Aisles, CoordOverlay, Effects, SelectionOutline } from "./Overlays";
import { CameraRig } from "./CameraRig";

/** SKUs that a revealed, not-yet-dispatched order still needs picked at time t. */
function useNeededSkus(state: TwinState): string[] {
  const t = useSimT();
  const firstSeen = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of state.events) if (e.order && !m.has(e.order)) m.set(e.order, e.t);
    return m;
  }, [state]);
  return useMemo(() => {
    const out = new Set<string>();
    const picks = new Map(state.tasks.filter((x) => x.kind === "PICK").map((x) => [x.id, x]));
    for (const o of state.orders) {
      if (o.hold || (firstSeen.get(o.id) ?? 0) > t) continue;
      for (const id of o.tasks) {
        const task = picks.get(id);
        if (!task?.sku) continue;
        if (taskStateAt(state, id, t)?.state !== "VERIFIED_COMPLETE") out.add(task.sku);
      }
    }
    return [...out].sort();
    // recompute only when the set can change (cheap anyway)
  }, [state, t, firstSeen]);
}

function Lights({ state }: { state: TwinState }) {
  const sun = useRef<THREE.DirectionalLight>(null);
  const scene = useThree((s) => s.scene);
  const { width: W, height: H } = state.layout;
  useEffect(() => {
    const l = sun.current;
    if (!l) return;
    l.target.position.set(W / 2, 0, H / 2);
    scene.add(l.target);
    return () => void scene.remove(l.target);
  }, [scene, W, H]);
  const ext = Math.max(W, H) * 0.75;
  return (
    <>
      <hemisphereLight args={["#ffffff", "#d5dbe3", 1.25]} />
      <ambientLight intensity={0.25} />
      <directionalLight
        ref={sun}
        position={[W / 2 + 12, 30, H / 2 + 16]}
        intensity={1.9}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0004}
        shadow-normalBias={0.02}
        shadow-camera-left={-ext}
        shadow-camera-right={ext}
        shadow-camera-top={ext}
        shadow-camera-bottom={-ext}
        shadow-camera-near={1}
        shadow-camera-far={90}
      />
    </>
  );
}

export function WarehouseScene({ state }: { state: TwinState }) {
  const needed = useNeededSkus(state);
  return (
    <>
      <color attach="background" args={[C.bg]} />
      <fog attach="fog" args={[C.bg, 70, 140]} />
      <Lights state={state} />
      <Floor layout={state.layout} robots={state.robots} />
      <Structures layout={state.layout} robots={state.robots} />
      <Racks layout={state.layout} inventory={state.inventory} neededSkus={needed} />
      <Aisles state={state} />
      <SelectionOutline layout={state.layout} />
      <Routes state={state} />
      <Robots state={state} />
      <CoordOverlay state={state} />
      <Effects state={state} />
      <CameraRig state={state} />
    </>
  );
}
