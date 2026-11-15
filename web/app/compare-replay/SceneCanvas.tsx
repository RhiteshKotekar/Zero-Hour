"use client";
// One read-only 3D scene for the side-by-side replay page. Reuses the existing WarehouseScene unchanged;
// both scenes on the page read the same store clock, so they play in sync.
import { Canvas } from "@react-three/fiber";
import { WarehouseScene } from "@/components/warehouse3d/Scene";
import { isoView } from "@/components/warehouse3d/CameraRig";
import type { TwinState } from "@/lib/types";

export default function SceneCanvas({ state }: { state: TwinState }) {
  const iso = isoView(state);
  return (
    <Canvas
      shadows="percentage"
      dpr={[1, 2]}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      camera={{ position: iso.pos.toArray(), fov: 36, near: 0.3, far: 250 }}
    >
      <WarehouseScene state={state} />
    </Canvas>
  );
}
