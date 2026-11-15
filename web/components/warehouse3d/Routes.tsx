"use client";
// Routes: remaining path of the current move (dashed), later legs of the same task (faint), destination marker.
// Geometry is refreshed ~12×/s from refs; no React re-render.
import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import * as THREE from "three";
import type { Line2, LineSegments2 } from "three-stdlib";
import type { Robot, TwinState } from "@/lib/types";
import { ROLE_COLOR, robotAt, robotRoute } from "@/lib/derive";
import { getLocalT, useStore } from "@/lib/store";

const Y = 0.05;
const EMPTY: [number, number, number][] = [
  [0, -10, 0],
  [0, -10, 0.01],
];

function setLine(line: Line2 | LineSegments2 | null, pts: [number, number][]) {
  if (!line) return;
  if (pts.length < 2) {
    line.visible = false;
    return;
  }
  const flat = new Float32Array(pts.length * 3);
  pts.forEach((p, i) => {
    flat[i * 3] = p[0];
    flat[i * 3 + 1] = Y;
    flat[i * 3 + 2] = p[1];
  });
  // LineGeometry.setPositions rebuilds the instance buffers
  (line.geometry as unknown as { setPositions: (a: Float32Array) => void }).setPositions(flat);
  line.computeLineDistances();
  line.visible = true;
}

function RobotRoute({ state, robot }: { state: TwinState; robot: Robot }) {
  const remaining = useRef<Line2>(null);
  const future = useRef<Line2>(null);
  const dest = useRef<THREE.Group>(null);
  const acc = useRef(1);
  const key = useRef("");
  const col = ROLE_COLOR[robot.role] ?? "#334155";

  useFrame(({ clock }, dt) => {
    acc.current += dt;
    if (dest.current?.visible) dest.current.children[1].scale.setScalar(1 + 0.15 * Math.sin(clock.elapsedTime * 4));
    if (acc.current < 1 / 12) return;
    acc.current = 0;
    const t = getLocalT();
    const pose = robotAt(state, robot.id, t);
    const r = robotRoute(state, robot.id, t, pose);
    setLine(remaining.current, r.remaining);
    const k = `${pose.idx}`;
    if (k !== key.current) {
      key.current = k;
      setLine(future.current, r.future.flat());
    }
    if (dest.current) {
      dest.current.visible = !!r.dest;
      if (r.dest) dest.current.position.set(r.dest[0], 0, r.dest[1]);
    }
  });

  return (
    <group>
      <Line ref={remaining} points={EMPTY} color={col} lineWidth={2.4} dashed dashSize={0.28} gapSize={0.18} transparent opacity={0.95} />
      <Line ref={future} points={EMPTY} color={col} lineWidth={1.4} dashed dashSize={0.1} gapSize={0.2} transparent opacity={0.4} />
      <group ref={dest} visible={false}>
        <mesh rotation-x={-Math.PI / 2} position-y={0.02}>
          <ringGeometry args={[0.2, 0.3, 32]} />
          <meshBasicMaterial color={col} transparent opacity={0.9} depthWrite={false} />
        </mesh>
        <mesh position-y={0.55} rotation-x={Math.PI}>
          <coneGeometry args={[0.1, 0.24, 4]} />
          <meshStandardMaterial color={col} emissive={col} emissiveIntensity={0.3} />
        </mesh>
      </group>
    </group>
  );
}

export function Routes({ state }: { state: TwinState }) {
  const on = useStore((s) => s.toggles.routes);
  if (!on) return null;
  return (
    <group>
      {state.robots
        .filter((r) => r.physical && r.mobile)
        .map((r) => (
          <RobotRoute key={r.id} state={state} robot={r} />
        ))}
    </group>
  );
}
