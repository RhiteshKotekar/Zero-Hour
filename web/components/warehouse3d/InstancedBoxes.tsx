"use client";
import { forwardRef, useImperativeHandle, useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

export interface BoxSpec {
  /** centre */
  p: [number, number, number];
  /** size */
  s: [number, number, number];
  c?: string;
  /** rotation about Y (rad) */
  ry?: number;
}

export interface InstancedBoxesHandle {
  mesh: THREE.InstancedMesh | null;
  setColor: (i: number, color: string) => void;
  commitColors: () => void;
}

const UNIT = new THREE.BoxGeometry(1, 1, 1);

/** Static boxes as one InstancedMesh (one draw call). Matrices are written once per `boxes` change. */
export const InstancedBoxes = forwardRef<
  InstancedBoxesHandle,
  {
    boxes: BoxSpec[];
    color?: string;
    roughness?: number;
    metalness?: number;
    castShadow?: boolean;
    receiveShadow?: boolean;
    emissive?: string;
    emissiveIntensity?: number;
  }
>(function InstancedBoxes(
  { boxes, color = "#ffffff", roughness = 0.7, metalness = 0.05, castShadow = true, receiveShadow = true, emissive, emissiveIntensity },
  ref,
) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const tmp = useMemo(() => ({ o: new THREE.Object3D(), c: new THREE.Color() }), []);
  const perInstanceColor = boxes.some((b) => b.c);

  useLayoutEffect(() => {
    const m = mesh.current;
    if (!m) return;
    boxes.forEach((b, i) => {
      tmp.o.position.set(...b.p);
      tmp.o.scale.set(...b.s);
      tmp.o.rotation.set(0, b.ry ?? 0, 0);
      tmp.o.updateMatrix();
      m.setMatrixAt(i, tmp.o.matrix);
      if (perInstanceColor) m.setColorAt(i, tmp.c.set(b.c ?? color));
    });
    m.count = boxes.length;
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
    m.computeBoundingSphere();
  }, [boxes, color, perInstanceColor, tmp]);

  useImperativeHandle(
    ref,
    () => ({
      get mesh() {
        return mesh.current;
      },
      setColor: (i, c) => mesh.current?.setColorAt(i, tmp.c.set(c)),
      commitColors: () => {
        if (mesh.current?.instanceColor) mesh.current.instanceColor.needsUpdate = true;
      },
    }),
    [tmp],
  );

  return (
    <instancedMesh
      ref={mesh}
      args={[UNIT, undefined, Math.max(boxes.length, 1)]}
      castShadow={castShadow}
      receiveShadow={receiveShadow}
      frustumCulled={false}
    >
      <meshStandardMaterial
        color={perInstanceColor ? "#ffffff" : color}
        roughness={roughness}
        metalness={metalness}
        emissive={emissive ?? "#000000"}
        emissiveIntensity={emissiveIntensity ?? 0}
      />
    </instancedMesh>
  );
});
