"use client";
// Robots are moved every frame from `robots[].segments` via refs (no React re-render per frame).
import { useCallback, useMemo, useRef } from "react";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import { Html, RoundedBox } from "@react-three/drei";
import { labelPortal } from "./labelPortal";
import * as THREE from "three";
import type { Robot, TwinState } from "@/lib/types";
import { ROLE_COLOR, STATUS_COLOR, robotAt, selectionRobot } from "@/lib/derive";
import { getLocalT, useStore } from "@/lib/store";
import { C } from "./palette";

const PROGRESS_SEG = 48;

function useRobotPointer(id: string) {
  const select = useStore((s) => s.select);
  const setHover = useStore((s) => s.setHover);
  return {
    onClick: (e: ThreeEvent<MouseEvent>) => {
      e.stopPropagation();
      select({ kind: "robot", id });
    },
    onPointerOver: (e: ThreeEvent<PointerEvent>) => {
      e.stopPropagation();
      setHover({ kind: "robot", id });
      document.body.style.cursor = "pointer";
    },
    onPointerOut: () => {
      setHover(null);
      document.body.style.cursor = "";
    },
  };
}

/** Shared per-robot visual state written from useFrame. */
interface Refs {
  ringMat: THREE.MeshBasicMaterial | null;
  progress: THREE.Mesh | null;
  halo: THREE.Mesh | null;
  fail: THREE.Group | null;
  beaconMat: THREE.MeshStandardMaterial | null;
  lightMat: THREE.MeshStandardMaterial | null;
  sel: THREE.Mesh | null;
  status: HTMLSpanElement | null;
  label: HTMLDivElement | null;
}

type Bind = <K extends keyof Refs>(k: K) => (v: Refs[K]) => void;
function useBind(refs: React.MutableRefObject<Refs>): Bind {
  return useCallback(
    (k) => (v) => {
      refs.current[k] = v;
    },
    [refs],
  ) as Bind;
}

function updateCommon(r: Refs, id: string, status: string, f: number | undefined, working: boolean, time: number, last: { status: string }) {
  const col = STATUS_COLOR[status] ?? "#64748b";
  if (last.status !== status) {
    last.status = status;
    r.ringMat?.color.set(col);
    r.lightMat?.color.set(col);
    r.lightMat?.emissive.set(col);
    if (r.status) {
      r.status.textContent = status;
      r.status.style.color = col;
    }
    if (r.label) r.label.style.borderColor = status === "FAILED" ? C.bad : "";
  }
  if (r.progress) {
    r.progress.visible = working && f != null;
    if (working && f != null) r.progress.geometry.setDrawRange(0, Math.max(1, Math.round(f * PROGRESS_SEG)) * 6);
  }
  if (r.halo) {
    const waiting = status === "WAITING";
    r.halo.visible = waiting;
    if (waiting) {
      const s = 1 + 0.12 * Math.sin(time * 6);
      r.halo.scale.set(s, s, s);
    }
  }
  const failed = status === "FAILED";
  if (r.fail) r.fail.visible = failed;
  if (failed && r.beaconMat) r.beaconMat.emissiveIntensity = 0.5 + 1.5 * (0.5 + 0.5 * Math.sin(time * 7));
  const st = useStore.getState();
  if (r.sel) r.sel.visible = selectionRobot(st.state, st.selection, st.clock.t) === id;
}

function FloorRings({ bind, radius, roleColor }: { bind: Bind; radius: number; roleColor: string }) {
  const progressGeo = useMemo(() => new THREE.RingGeometry(radius + 0.1, radius + 0.18, PROGRESS_SEG, 1, Math.PI / 2, Math.PI * 2), [radius]);
  return (
    <group rotation-x={-Math.PI / 2} position-y={0.015}>
      <mesh>
        <ringGeometry args={[radius, radius + 0.06, 48]} />
        <meshBasicMaterial ref={bind("ringMat")} color={roleColor} transparent opacity={0.95} depthWrite={false} />
      </mesh>
      <mesh ref={bind("progress")} geometry={progressGeo} visible={false}>
        <meshBasicMaterial color={roleColor} transparent opacity={0.9} depthWrite={false} />
      </mesh>
      <mesh ref={bind("halo")} visible={false}>
        <ringGeometry args={[radius + 0.22, radius + 0.32, 48]} />
        <meshBasicMaterial color="#d97706" transparent opacity={0.85} depthWrite={false} />
      </mesh>
      <mesh ref={bind("sel")} visible={false}>
        <ringGeometry args={[radius + 0.36, radius + 0.44, 48]} />
        <meshBasicMaterial color={C.accent} transparent opacity={0.9} depthWrite={false} />
      </mesh>
    </group>
  );
}

function FailMarker({ bind, y }: { bind: Bind; y: number }) {
  return (
    <group ref={bind("fail")} visible={false}>
      <mesh position={[0, y + 0.12, 0]}>
        <cylinderGeometry args={[0.07, 0.09, 0.22, 16]} />
        <meshStandardMaterial ref={bind("beaconMat")} color={C.bad} emissive={C.bad} emissiveIntensity={1} />
      </mesh>
      <group position={[0, y + 0.6, 0]}>
        {[Math.PI / 4, -Math.PI / 4].map((r) => (
          <mesh key={r} rotation-z={r}>
            <boxGeometry args={[0.5, 0.08, 0.08]} />
            <meshBasicMaterial color={C.bad} toneMapped={false} />
          </mesh>
        ))}
      </group>
      <mesh rotation-x={-Math.PI / 2} position-y={0.02}>
        <ringGeometry args={[0.85, 0.95, 40]} />
        <meshBasicMaterial color={C.bad} transparent opacity={0.8} depthWrite={false} />
      </mesh>
    </group>
  );
}

function RobotLabel({ bind, robot, y, roleColor }: { bind: Bind; robot: Robot; y: number; roleColor: string }) {
  return (
    <Html portal={labelPortal} position={[0, y, 0]} center zIndexRange={[40, 20]} className="w3-label">
      <div className="w3-robot" ref={bind("label")}>
        <i style={{ width: 7, height: 7, borderRadius: 2, background: roleColor, display: "inline-block" }} />
        {robot.id}
        <small ref={bind("status")} style={{ color: STATUS_COLOR.IDLE }}>
          IDLE
        </small>
      </div>
    </Html>
  );
}

/** Low AMR: body, role band, lidar puck, status light, tote when carrying, floor status/progress ring, label. */
export function MobileRobot({ state, robot }: { state: TwinState; robot: Robot }) {
  const root = useRef<THREE.Group>(null);
  const chassis = useRef<THREE.Group>(null);
  const tote = useRef<THREE.Group>(null);
  const refs = useRef<Refs>({ ringMat: null, progress: null, halo: null, fail: null, beaconMat: null, lightMat: null, sel: null, status: null, label: null });
  const heading = useRef<number | null>(null);
  const last = useRef({ status: "" });
  const roleColor = ROLE_COLOR[robot.role] ?? "#334155";
  const pointer = useRobotPointer(robot.id);
  const bind = useBind(refs);

  useFrame(({ clock }, dt) => {
    const p = robotAt(state, robot.id, getLocalT());
    root.current?.position.set(p.x, 0, p.y);
    if (p.dx || p.dy) {
      const target = Math.atan2(-(p.dy ?? 0), p.dx ?? 0);
      if (heading.current == null) heading.current = target;
      let d = target - heading.current;
      d = Math.atan2(Math.sin(d), Math.cos(d));
      heading.current += d * (1 - Math.exp(-dt * 14));
    }
    if (chassis.current && heading.current != null) chassis.current.rotation.y = heading.current;
    if (tote.current) tote.current.visible = p.status === "TRANSPORTING";
    updateCommon(refs.current, robot.id, p.status, p.f, p.seg?.kind === "work", clock.elapsedTime, last.current);
  });

  return (
    <group ref={root}>
      <group ref={chassis} {...pointer}>
        <RoundedBox args={[0.78, 0.22, 0.56]} radius={0.06} smoothness={3} position={[0, 0.17, 0]} castShadow receiveShadow>
          <meshStandardMaterial color={C.robotBody} roughness={0.45} metalness={0.05} />
        </RoundedBox>
        <mesh position={[0, 0.13, 0]}>
          <boxGeometry args={[0.8, 0.05, 0.58]} />
          <meshStandardMaterial color={roleColor} roughness={0.5} />
        </mesh>
        <mesh position={[-0.04, 0.29, 0]} castShadow>
          <boxGeometry args={[0.6, 0.02, 0.46]} />
          <meshStandardMaterial color={C.robotDeck} roughness={0.7} />
        </mesh>
        {/* lidar puck */}
        <mesh position={[0.27, 0.33, 0]} castShadow>
          <cylinderGeometry args={[0.065, 0.065, 0.07, 20]} />
          <meshStandardMaterial color="#111827" roughness={0.3} metalness={0.4} />
        </mesh>
        <mesh position={[0.27, 0.372, 0]}>
          <cylinderGeometry args={[0.07, 0.07, 0.015, 20]} />
          <meshStandardMaterial color={roleColor} />
        </mesh>
        {/* status light (rear) */}
        <mesh position={[-0.33, 0.31, 0]}>
          <sphereGeometry args={[0.045, 12, 12]} />
          <meshStandardMaterial ref={(m) => void (refs.current.lightMat = m)} color={STATUS_COLOR.IDLE} emissive={STATUS_COLOR.IDLE} emissiveIntensity={1.4} />
        </mesh>
        {/* tote */}
        <group ref={tote} visible={false} position={[-0.04, 0.42, 0]}>
          <mesh castShadow>
            <boxGeometry args={[0.48, 0.22, 0.38]} />
            <meshStandardMaterial color={C.tote} roughness={0.6} />
          </mesh>
          <mesh position={[0, 0.115, 0]}>
            <boxGeometry args={[0.5, 0.02, 0.4]} />
            <meshStandardMaterial color="#c47f17" />
          </mesh>
        </group>
      </group>
      <FloorRings bind={bind} radius={0.5} roleColor={roleColor} />
      <FailMarker bind={bind} y={0.45} />
      <RobotLabel bind={bind} robot={robot} y={1.05} roleColor={roleColor} />
    </group>
  );
}

/** Stationary packing robot: articulated arm on the pack-station pedestal; animates while PACKING. */
export function PackArm({ state, robot }: { state: TwinState; robot: Robot }) {
  const root = useRef<THREE.Group>(null);
  const turret = useRef<THREE.Group>(null);
  const shoulder = useRef<THREE.Group>(null);
  const elbow = useRef<THREE.Group>(null);
  const refs = useRef<Refs>({ ringMat: null, progress: null, halo: null, fail: null, beaconMat: null, lightMat: null, sel: null, status: null, label: null });
  const last = useRef({ status: "" });
  const roleColor = ROLE_COLOR[robot.role] ?? "#7c3aed";
  const pointer = useRobotPointer(robot.id);
  const bind = useBind(refs);
  const phase = useRef(0);

  useFrame(({ clock }, dt) => {
    const p = robotAt(state, robot.id, getLocalT());
    root.current?.position.set(p.x, 0, p.y);
    const active = p.status === "PACKING";
    if (active) phase.current += dt * 1.8 * Math.max(0.5, Math.min(useStore.getState().clock.speed, 4));
    const ph = phase.current;
    if (turret.current) turret.current.rotation.y = active ? Math.sin(ph) * 1.3 + Math.PI : THREE.MathUtils.lerp(turret.current.rotation.y, Math.PI, 0.05);
    if (shoulder.current) shoulder.current.rotation.z = active ? 0.55 + Math.sin(ph * 2) * 0.25 : 0.35;
    if (elbow.current) elbow.current.rotation.z = active ? -1.2 + Math.cos(ph * 2) * 0.3 : -1.5;
    updateCommon(refs.current, robot.id, p.status, p.f, p.seg?.kind === "work", clock.elapsedTime, last.current);
  });

  return (
    <group ref={root}>
      <group position-y={0.6} {...pointer}>
        <mesh position={[0, 0.06, 0]} castShadow>
          <cylinderGeometry args={[0.2, 0.24, 0.12, 24]} />
          <meshStandardMaterial color="#e5e7eb" metalness={0.3} roughness={0.4} />
        </mesh>
        <mesh position={[0.2, 0.08, 0.2]}>
          <sphereGeometry args={[0.04, 12, 12]} />
          <meshStandardMaterial ref={(m) => void (refs.current.lightMat = m)} color={STATUS_COLOR.IDLE} emissive={STATUS_COLOR.IDLE} emissiveIntensity={1.4} />
        </mesh>
        <group ref={turret} position-y={0.14}>
          <mesh position={[0, 0.08, 0]} castShadow>
            <cylinderGeometry args={[0.13, 0.15, 0.16, 20]} />
            <meshStandardMaterial color={roleColor} roughness={0.45} />
          </mesh>
          <group ref={shoulder} position-y={0.16}>
            <mesh position={[0, 0.3, 0]} castShadow>
              <boxGeometry args={[0.1, 0.6, 0.1]} />
              <meshStandardMaterial color="#f1f5f9" roughness={0.4} />
            </mesh>
            <group ref={elbow} position-y={0.6}>
              <mesh>
                <sphereGeometry args={[0.07, 16, 16]} />
                <meshStandardMaterial color={roleColor} />
              </mesh>
              <mesh position={[0, 0.25, 0]} castShadow>
                <boxGeometry args={[0.08, 0.5, 0.08]} />
                <meshStandardMaterial color="#f1f5f9" roughness={0.4} />
              </mesh>
              <mesh position={[0, 0.52, 0]} castShadow>
                <boxGeometry args={[0.16, 0.06, 0.12]} />
                <meshStandardMaterial color="#334155" />
              </mesh>
            </group>
          </group>
        </group>
      </group>
      <FloorRings bind={bind} radius={0.62} roleColor={roleColor} />
      <FailMarker bind={bind} y={1.6} />
      <RobotLabel bind={bind} robot={robot} y={2.0} roleColor={roleColor} />
    </group>
  );
}

export function Robots({ state }: { state: TwinState }) {
  return (
    <group>
      {state.robots
        .filter((r) => r.physical)
        .map((r) => (r.mobile ? <MobileRobot key={r.id} state={state} robot={r} /> : <PackArm key={r.id} state={state} robot={r} />))}
    </group>
  );
}
