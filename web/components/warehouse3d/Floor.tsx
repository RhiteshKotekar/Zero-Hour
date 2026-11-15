"use client";
import { useEffect, useMemo } from "react";
import type { Layout, Robot } from "@/lib/types";
import { FLOOR_MARGIN, makeFloorTexture } from "./floorTexture";

export function Floor({ layout, robots }: { layout: Layout; robots: Robot[] }) {
  const tex = useMemo(() => makeFloorTexture(layout, robots), [layout, robots]);
  useEffect(() => () => tex.dispose(), [tex]);
  const w = layout.width + FLOOR_MARGIN * 2;
  const h = layout.height + FLOOR_MARGIN * 2;
  return (
    <mesh rotation-x={-Math.PI / 2} position={[layout.width / 2, 0, layout.height / 2]} receiveShadow>
      <planeGeometry args={[w, h]} />
      <meshStandardMaterial map={tex} roughness={0.92} metalness={0} />
    </mesh>
  );
}
