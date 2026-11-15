"use client";
// Camera controls: orbit/zoom/pan (OrbitControls) + store-driven commands (Top, 3D, Reset, Follow, Focus …).
import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { TwinState } from "@/lib/types";
import { congestionAt, failedRobotsAt, robotAt, selectionRobot } from "@/lib/derive";
import { getLocalT, useStore } from "@/lib/store";

export function isoView(state: TwinState): { pos: THREE.Vector3; target: THREE.Vector3 } {
  const { width: W, height: H } = state.layout;
  const target = new THREE.Vector3(W / 2 + 0.5, 0, H / 2 - 0.5);
  return { pos: target.clone().add(new THREE.Vector3(W * 0.36, W * 0.9, H * 1.32)), target };
}
function topView(state: TwinState) {
  const { width: W, height: H } = state.layout;
  const target = new THREE.Vector3(W / 2, 0, H / 2);
  return { pos: new THREE.Vector3(W / 2, W * 1.12, H / 2 + 0.01), target };
}
function focusAt(x: number, z: number, dist = 9) {
  const target = new THREE.Vector3(x, 0, z);
  return { pos: target.clone().add(new THREE.Vector3(dist * 0.55, dist * 0.8, dist * 0.75)), target };
}

export function CameraRig({ state }: { state: TwinState }) {
  const controls = useRef<OrbitControlsImpl>(null);
  const { camera } = useThree();
  const goal = useRef<{ pos: THREE.Vector3; target: THREE.Vector3 } | null>(null);
  const followPrev = useRef<THREE.Vector3 | null>(null);
  const cmd = useStore((s) => s.camera);
  const initialTarget = useMemo(() => isoView(state).target.toArray() as [number, number, number], [state.layout]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!cmd) return;
    const st = useStore.getState();
    const t = getLocalT();
    const L = state.layout;
    const robotGoal = (id: string) => {
      const p = robotAt(state, id, t);
      return focusAt(p.x, p.y, 7);
    };
    switch (cmd.kind) {
      case "top":
        st.setFollow(null);
        goal.current = topView(state);
        break;
      case "iso":
      case "reset":
        st.setFollow(null);
        goal.current = isoView(state);
        break;
      case "follow": {
        const sel = st.selection?.kind === "robot" ? st.selection.id : null;
        const id =
          sel ??
          state.robots.find((r) => r.mobile && ["MOVING", "TRANSPORTING"].includes(robotAt(state, r.id, t).status))?.id ??
          state.robots.find((r) => r.mobile)?.id ??
          null;
        if (id) {
          st.setFollow(id);
          if (!sel) st.select({ kind: "robot", id });
          followPrev.current = null;
          goal.current = robotGoal(id);
        }
        break;
      }
      case "focusSelection": {
        const s = st.selection;
        if (!s) break;
        const rid = selectionRobot(state, s, t);
        if (rid) goal.current = robotGoal(rid);
        else if (s.kind === "rack" || s.kind === "aisle") {
          const r = (s.kind === "rack" ? L.racks : L.aisles).find((x) => x.id === s.id)?.rect;
          if (r) goal.current = focusAt((r[0] + r[2] + 1) / 2, (r[1] + r[3] + 1) / 2, 11);
        }
        break;
      }
      case "focusCongestion": {
        const now = congestionAt(state, t)[0]?.entries[0];
        const past = [...state.congestion].reverse().find((c) => c.t0 <= t);
        const c = now ?? past;
        if (c) {
          const a = L.aisles.find((x) => x.id === c.aisle);
          if (a) {
            st.select({ kind: "aisle", id: a.id });
            goal.current = focusAt((a.rect[0] + a.rect[2] + 1) / 2, (a.rect[1] + a.rect[3] + 1) / 2, 11);
          }
        }
        break;
      }
      case "focusFailure": {
        const id = failedRobotsAt(state, t)[0];
        if (id) {
          st.select({ kind: "robot", id });
          goal.current = robotGoal(id);
        }
        break;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cmd]);

  useFrame((_, dt) => {
    const c = controls.current;
    if (!c) return;
    const follow = useStore.getState().follow;
    if (follow && !goal.current) {
      const p = robotAt(state, follow, getLocalT());
      const target = new THREE.Vector3(p.x, 0, p.y);
      const delta = target.clone().sub(c.target);
      const k = 1 - Math.exp(-dt * 6);
      delta.multiplyScalar(k);
      c.target.add(delta);
      camera.position.add(delta);
      c.update();
    }
    if (goal.current) {
      const k = 1 - Math.exp(-dt * 5);
      camera.position.lerp(goal.current.pos, k);
      c.target.lerp(goal.current.target, k);
      c.update();
      if (camera.position.distanceTo(goal.current.pos) < 0.05 && c.target.distanceTo(goal.current.target) < 0.05) goal.current = null;
    }
  });

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      target={initialTarget}
      enableDamping
      dampingFactor={0.12}
      maxPolarAngle={Math.PI / 2.15}
      minDistance={3}
      maxDistance={80}
      screenSpacePanning={false}
      onStart={() => {
        goal.current = null;
      }}
    />
  );
}
