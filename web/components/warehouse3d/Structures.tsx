"use client";
import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { labelPortal } from "./labelPortal";
import * as THREE from "three";
import type { Layout, Robot } from "@/lib/types";
import { C, hash01 } from "./palette";
import { InstancedBoxes, type BoxSpec } from "./InstancedBoxes";

const WALL_H = 0.9;
const WALL_T = 0.18;

/** Walls, docks, pack stations, chargers, WMS tower, consolidation carts and pallets (all static). */
export function Structures({ layout, robots }: { layout: Layout; robots: Robot[] }) {
  const { walls, dark, steel, wood, cargo, purple, green, orange, white } = useMemo(() => {
    const walls: BoxSpec[] = [];
    const dark: BoxSpec[] = [];
    const steel: BoxSpec[] = [];
    const wood: BoxSpec[] = [];
    const cargo: BoxSpec[] = [];
    const purple: BoxSpec[] = [];
    const green: BoxSpec[] = [];
    const orange: BoxSpec[] = [];
    const white: BoxSpec[] = [];
    const W = layout.width,
      H = layout.height;

    // interior walls (storage block)
    for (const [x0, y0, x1, y1] of layout.walls)
      walls.push({ p: [(x0 + x1 + 1) / 2, WALL_H / 2, (y0 + y1 + 1) / 2], s: [x1 - x0 + 0.7, WALL_H, y1 - y0 + 1] });

    // perimeter, with openings at dock doors
    const docks = layout.stations.filter((s) => s.kind === "dock");
    walls.push({ p: [W / 2, WALL_H / 2, -WALL_T / 2], s: [W + WALL_T * 2, WALL_H, WALL_T] });
    walls.push({ p: [-WALL_T / 2, WALL_H / 2, H / 2], s: [WALL_T, WALL_H, H] });
    walls.push({ p: [W + WALL_T / 2, WALL_H / 2, H / 2], s: [WALL_T, WALL_H, H] });
    const gaps = docks.map((d) => [d.rect[0] + 0.15, d.rect[2] + 0.85] as const).sort((a, b) => a[0] - b[0]);
    let cur = -WALL_T;
    for (const [a, b] of [...gaps, [W + WALL_T, W + WALL_T] as const]) {
      if (a > cur) walls.push({ p: [(cur + a) / 2, WALL_H / 2, H + WALL_T / 2], s: [a - cur, WALL_H, WALL_T] });
      cur = b;
    }

    // dock doors: frame, rolled shutter, bumpers, leveller
    for (const d of docks) {
      const [x0, , x1] = d.rect;
      const a = x0 + 0.15,
        b = x1 + 0.85,
        z = H + WALL_T / 2;
      for (const x of [a - 0.08, b + 0.08]) orange.push({ p: [x, 1.4, z], s: [0.16, 2.8, WALL_T + 0.04] });
      orange.push({ p: [(a + b) / 2, 2.75, z], s: [b - a + 0.32, 0.14, WALL_T + 0.04] });
      steel.push({ p: [(a + b) / 2, 2.45, z + 0.02], s: [b - a, 0.45, 0.16] });
      for (const x of [a + 0.35, b - 0.35]) dark.push({ p: [x, 0.35, H - 0.04], s: [0.22, 0.3, 0.1] });
      steel.push({ p: [(a + b) / 2, 0.02, H - 0.45], s: [b - a - 0.3, 0.04, 0.8] });
    }

    // pack stations: infeed table, pedestal for the arm, outbound roller conveyor
    for (const st of layout.stations.filter((s) => s.kind === "pack")) {
      const [x0, y0, x1, y1] = st.rect;
      const cz = (y0 + y1 + 1) / 2,
        cx = (x0 + x1 + 1) / 2;
      white.push({ p: [x0 + 0.65, 0.78, cz], s: [0.9, 0.06, 1.3] });
      for (const dx of [-0.38, 0.38]) for (const dz of [-0.58, 0.58]) steel.push({ p: [x0 + 0.65 + dx, 0.38, cz + dz], s: [0.05, 0.76, 0.05] });
      purple.push({ p: [cx, 0.3, cz], s: [0.7, 0.6, 0.7] });
      const cx0 = cx + 0.55,
        cx1 = (st.outbound ? st.outbound[0] : x1) + 0.95;
      dark.push({ p: [(cx0 + cx1) / 2, 0.62, cz], s: [cx1 - cx0, 0.08, 0.66] });
      for (let x = cx0 + 0.12; x < cx1 - 0.05; x += 0.22) steel.push({ p: [x, 0.68, cz], s: [0.06, 0.04, 0.6] });
      for (const x of [cx0 + 0.15, cx1 - 0.15]) for (const dz of [-0.28, 0.28]) steel.push({ p: [x, 0.3, cz + dz], s: [0.05, 0.6, 0.05] });
      // parcels waiting on the conveyor
      cargo.push({ p: [cx1 - 0.45, 0.8, cz], s: [0.38, 0.28, 0.34] });
    }

    // chargers: back posts + pads
    for (const st of layout.stations.filter((s) => s.kind === "charger")) {
      const [x0, y0, x1] = st.rect;
      for (let x = x0; x <= x1; x++) {
        white.push({ p: [x + 0.5, 0.45, y0 + 0.2], s: [0.4, 0.9, 0.22] });
        green.push({ p: [x + 0.5, 0.78, y0 + 0.32], s: [0.18, 0.08, 0.02] });
        steel.push({ p: [x + 0.5, 0.012, y0 + 0.9], s: [0.6, 0.024, 0.6] });
      }
    }

    // consolidation carts
    for (const c of layout.consolidation) {
      const [x, y] = c.cell;
      steel.push({ p: [x + 0.5, 0.42, y + 0.5], s: [0.62, 0.04, 0.62] });
      for (const dx of [-0.28, 0.28]) for (const dz of [-0.28, 0.28]) steel.push({ p: [x + 0.5 + dx, 0.45, y + 0.5 + dz], s: [0.035, 0.9, 0.035] });
      steel.push({ p: [x + 0.5, 0.88, y + 0.5], s: [0.62, 0.03, 0.62] });
    }

    // pallets (receiving, replenishment, outbound staging)
    const pallets = (zoneId: string, step: number, fill: number) => {
      const z = layout.zones.find((q) => q.id === zoneId);
      if (!z) return;
      const [x0, y0, x1, y1] = z.rect;
      for (let x = x0 + 0.5; x <= x1; x += step)
        for (let y = y0 + 0.6; y <= y1; y += step) {
          if (hash01(x, y, 3) > fill) continue;
          wood.push({ p: [x + 0.5, 0.07, y + 0.5], s: [1.0, 0.14, 0.8] });
          const n = 1 + Math.floor(hash01(y, x, 5) * 3);
          for (let k = 0; k < n; k++) cargo.push({ p: [x + 0.5, 0.14 + 0.2 + k * 0.38, y + 0.5], s: [0.92, 0.36, 0.72] });
        }
    };
    pallets("RECEIVING", 1.6, 0.6);
    pallets("REPLEN", 1.7, 0.45);
    pallets("STAGING", 1.8, 0.5);
    return { walls, dark, steel, wood, cargo, purple, green, orange, white };
  }, [layout]);

  const wms = robots.find((r) => r.lead);
  return (
    <group>
      <InstancedBoxes boxes={walls} color={C.wall} roughness={0.9} />
      <InstancedBoxes boxes={dark} color="#2b3444" roughness={0.6} />
      <InstancedBoxes boxes={steel} color="#aeb7c4" metalness={0.35} roughness={0.45} />
      <InstancedBoxes boxes={wood} color="#c9a46e" roughness={0.9} />
      <InstancedBoxes boxes={cargo} color="#d8bd8f" roughness={0.95} />
      <InstancedBoxes boxes={purple} color="#ddd3f7" roughness={0.6} />
      <InstancedBoxes boxes={orange} color="#f2a33a" roughness={0.6} />
      <InstancedBoxes boxes={white} color="#fbfcfd" roughness={0.5} />
      <InstancedBoxes boxes={green} color="#22c55e" emissive="#22c55e" emissiveIntensity={0.8} castShadow={false} />
      {wms && <WmsTower x={wms.home[0] + 0.5} z={wms.home[1] + 0.5} />}
    </group>
  );
}

/** WMS / SAMG hub: server cabinets + operator desk + pulsing link light. */
function WmsTower({ x, z }: { x: number; z: number }) {
  const light = useRef<THREE.MeshStandardMaterial>(null);
  useFrame(({ clock }) => {
    if (light.current) light.current.emissiveIntensity = 0.6 + 0.6 * (0.5 + 0.5 * Math.sin(clock.elapsedTime * 4));
  });
  return (
    <group position={[x, 0, z]}>
      {[-0.7, 0, 0.7].map((dx) => (
        <group key={dx} position={[dx, 0, -0.9]}>
          <mesh position={[0, 1.05, 0]} castShadow receiveShadow>
            <boxGeometry args={[0.62, 2.1, 0.7]} />
            <meshStandardMaterial color="#1e293b" roughness={0.5} metalness={0.2} />
          </mesh>
          {[0.5, 0.9, 1.3, 1.7].map((y) => (
            <mesh key={y} position={[0, y, 0.352]}>
              <planeGeometry args={[0.5, 0.06]} />
              <meshBasicMaterial color={y === 1.3 ? "#22c55e" : "#38bdf8"} toneMapped={false} />
            </mesh>
          ))}
        </group>
      ))}
      {/* operator desk + screens */}
      <mesh position={[0, 0.72, 0.5]} castShadow receiveShadow>
        <boxGeometry args={[2.0, 0.06, 0.7]} />
        <meshStandardMaterial color="#f8fafc" roughness={0.5} />
      </mesh>
      <mesh position={[0, 0.36, 0.5]} castShadow>
        <boxGeometry args={[1.9, 0.7, 0.05]} />
        <meshStandardMaterial color="#cbd5e1" />
      </mesh>
      {[-0.55, 0, 0.55].map((dx) => (
        <group key={dx} position={[dx, 1.0, 0.35]} rotation-x={-0.12}>
          <mesh castShadow>
            <boxGeometry args={[0.5, 0.32, 0.03]} />
            <meshStandardMaterial color="#0b1220" />
          </mesh>
          <mesh position={[0, 0, 0.017]}>
            <planeGeometry args={[0.46, 0.28]} />
            <meshBasicMaterial color={dx === 0 ? "#0e7490" : "#1d4ed8"} toneMapped={false} />
          </mesh>
        </group>
      ))}
      <mesh position={[0.7, 2.3, -0.9]}>
        <sphereGeometry args={[0.09, 16, 16]} />
        <meshStandardMaterial ref={light} color="#22c55e" emissive="#22c55e" emissiveIntensity={1} />
      </mesh>
      <Html portal={labelPortal} position={[0, 2.75, -0.9]} center zIndexRange={[10, 0]} className="w3-label">
        <div className="w3-badge" style={{ background: C.ink }}>
          WMS · SAMG HUB
        </div>
      </Html>
    </group>
  );
}
