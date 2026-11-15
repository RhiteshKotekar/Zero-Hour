"use client";
// Time-revealed overlays driven by the committed clock (≈10 Hz): aisle hitboxes, congestion, selection
// outline, witness / claim-rejected / failure effects, coordination-graph overlay.
import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { labelPortal } from "./labelPortal";
import * as THREE from "three";
import type { Layout, TwinState } from "@/lib/types";
import { congestionAt, effectsAt, indexOf, robotAt, waveAt, type Effect } from "@/lib/derive";
import { getLocalT, useSimT, useStore } from "@/lib/store";
import { C, RACK_H } from "./palette";

const rectBox = (r: number[]) => ({
  cx: (r[0] + r[2] + 1) / 2,
  cz: (r[1] + r[3] + 1) / 2,
  w: r[2] - r[0] + 1,
  d: r[3] - r[1] + 1,
});

/** Clickable aisles + congestion highlight and label. */
export function Aisles({ state }: { state: TwinState }) {
  const t = useSimT();
  const select = useStore((s) => s.select);
  const setHover = useStore((s) => s.setHover);
  const showCong = useStore((s) => s.toggles.congestion);
  const cong = useMemo(() => (showCong ? congestionAt(state, t) : []), [state, t, showCong]);
  const pulse = useMemo(() => new THREE.MeshBasicMaterial({ color: C.amber, transparent: true, opacity: 0.35, depthWrite: false }), []);
  useFrame(({ clock }) => {
    // eslint-disable-next-line react-hooks/immutability -- three.js material animated in useFrame
    pulse.opacity = 0.28 + 0.16 * Math.sin(clock.elapsedTime * 5);
  });
  return (
    <group>
      {state.layout.aisles.map((a) => {
        const b = rectBox(a.rect);
        return (
          <mesh
            key={a.id}
            position={[b.cx, 0.05, b.cz]}
            onClick={(e) => {
              e.stopPropagation();
              select({ kind: "aisle", id: a.id });
            }}
            onPointerOver={(e) => {
              e.stopPropagation();
              setHover({ kind: "aisle", id: a.id });
            }}
            onPointerOut={() => setHover(null)}
          >
            <boxGeometry args={[b.w, 0.1, b.d]} />
            <meshBasicMaterial transparent opacity={0} depthWrite={false} />
          </mesh>
        );
      })}
      {state.layout.aisles.map((a) => {
        const c = cong.find((x) => x.aisle === a.id);
        const b = rectBox(a.rect);
        return (
          <group key={a.id}>
            {c && (
              <>
                <mesh position={[b.cx, 0.03, b.cz]} rotation-x={-Math.PI / 2} material={pulse}>
                  <planeGeometry args={[b.w + 0.1, b.d + 0.1]} />
                </mesh>
                <mesh position={[b.cx, 0.6, b.cz]}>
                  <boxGeometry args={[b.w + 0.1, 1.2, b.d + 0.1]} />
                  <meshBasicMaterial color={C.amber} transparent opacity={0.1} depthWrite={false} side={THREE.DoubleSide} />
                </mesh>
                {c.entries.map((e) => (
                  <mesh key={e.robot} position={[e.cell[0] + 0.5, 0.025, e.cell[1] + 0.5]} rotation-x={-Math.PI / 2}>
                    <circleGeometry args={[0.55, 32]} />
                    <meshBasicMaterial color={C.warn} transparent opacity={0.22} depthWrite={false} />
                  </mesh>
                ))}
              </>
            )}
            {/* kept mounted (drei Html roots are costly to unmount); hidden when clear */}
            <Html portal={labelPortal} position={[b.cx, 1.6, a.rect[3] + 1.2]} center zIndexRange={[60, 40]} className="w3-label w3-keep">
              <div className="w3-badge mono" style={{ background: C.warn, display: c ? "block" : "none" }}>
                {c?.label}
              </div>
            </Html>
          </group>
        );
      })}
    </group>
  );
}

/** Accent outline around the selected / hovered rack or aisle. */
export function SelectionOutline({ layout }: { layout: Layout }) {
  const sel = useStore((s) => s.selection);
  const hover = useStore((s) => s.hover);
  const box = (kind: string | undefined, id: string | undefined, h: number) => {
    if (kind === "rack") {
      const r = layout.racks.find((x) => x.id === id);
      return r ? { ...rectBox(r.rect), h: RACK_H + 0.1 } : null;
    }
    if (kind === "aisle") {
      const a = layout.aisles.find((x) => x.id === id);
      return a ? { ...rectBox(a.rect), h } : null;
    }
    return null;
  };
  const s = box(sel?.kind, sel?.id, 0.5);
  const hv = hover && (hover.kind !== sel?.kind || hover.id !== sel?.id) ? box(hover.kind, hover.id, 0.3) : null;
  return (
    <group>
      {s && <Outline b={s} color={C.accent} opacity={1} />}
      {hv && <Outline b={hv} color={C.accent} opacity={0.4} />}
    </group>
  );
}
function Outline({ b, color, opacity }: { b: { cx: number; cz: number; w: number; d: number; h: number }; color: string; opacity: number }) {
  const geo = useMemo(() => new THREE.EdgesGeometry(new THREE.BoxGeometry(b.w + 0.12, b.h, b.d + 0.12)), [b.w, b.h, b.d]);
  return (
    <group position={[b.cx, b.h / 2, b.cz]}>
      <lineSegments geometry={geo}>
        <lineBasicMaterial color={color} transparent opacity={opacity} />
      </lineSegments>
      <mesh position-y={-b.h / 2 + 0.035} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[b.w + 0.12, b.d + 0.12]} />
        <meshBasicMaterial color={color} transparent opacity={0.1 * opacity} depthWrite={false} />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------- effects
const FX_SLOTS = 8;
const FX_MAX_AGE = 6;
/** One always-mounted effect slot (rings + badge), driven by whichever effect is assigned to it. */
function EffectSlot({ state, fx }: { state: TwinState; fx: Effect | null }) {
  const g = useRef<THREE.Group>(null);
  const rings = useRef<(THREE.Mesh | null)[]>([]);
  const badge = useRef<HTMLDivElement>(null);
  const color = !fx ? C.ok : fx.kind === "witness" ? C.ok : fx.kind === "rejected" ? C.sec : C.bad;
  useFrame(() => {
    if (!g.current) return;
    g.current.visible = !!fx;
    if (!fx) return;
    const t = getLocalT();
    const age = Math.max(0, t - fx.t);
    const p = robotAt(state, fx.robot, t);
    g.current.position.set(p.x, 0, p.y);
    const o = Math.max(0, 1 - age / FX_MAX_AGE);
    rings.current.forEach((m, i) => {
      if (!m) return;
      const n = fx.kind === "witness" ? 1 : 3;
      m.visible = i < n;
      const a = (age * (fx.kind === "witness" ? 0.35 : 0.6) + i * 0.33) % 1.6;
      const s = 1 + a * (fx.kind === "witness" ? 0.8 : 1.6);
      m.scale.set(s, s, s);
      (m.material as THREE.MeshBasicMaterial).opacity = o * (1 - a / 1.6);
    });
    if (badge.current) badge.current.style.opacity = String(Math.min(1, o * 1.5));
  });
  return (
    <group ref={g} visible={false}>
      {[0, 1, 2].map((i) => (
        <mesh key={i} ref={(m) => void (rings.current[i] = m)} rotation-x={-Math.PI / 2} position-y={0.04 + i * 0.002}>
          <ringGeometry args={[0.72, 0.82, 48]} />
          <meshBasicMaterial color={color} transparent opacity={1} depthWrite={false} />
        </mesh>
      ))}
      <Html portal={labelPortal} position={[0, fx?.kind === "witness" ? 1.5 : 1.9, 0]} center zIndexRange={[80, 60]} className="w3-label w3-keep">
        <div ref={badge} className="w3-badge" style={{ background: color, display: fx ? "block" : "none" }}>
          {!fx ? "" : fx.kind === "witness" ? "✓ WITNESS VERIFIED" : fx.kind === "rejected" ? "CLAIM REJECTED" : `${fx.robot} FAILED`}
        </div>
      </Html>
    </group>
  );
}

/** Witness ✓ rings, CLAIM REJECTED bursts and failure rings for events of the last few seconds. */
export function Effects({ state }: { state: TwinState }) {
  const t = useSimT();
  const on = useStore((s) => s.toggles.effects);
  const fx = useMemo(() => {
    if (!on) return [];
    const all = effectsAt(state, t, FX_MAX_AGE);
    // security + failure first, then most recent witness ticks
    const rank = (e: Effect) => (e.kind === "witness" ? 1 : 0);
    return [...all].sort((a, b) => rank(a) - rank(b) || b.t - a.t).slice(0, FX_SLOTS);
  }, [state, t, on]);
  return (
    <group>
      {Array.from({ length: FX_SLOTS }, (_, i) => (
        <EffectSlot key={i} state={state} fx={fx[i] ?? null} />
      ))}
    </group>
  );
}

// ---------------------------------------------------------------- coordination graph overlay
const MAX_LINKS = 128;
/** SAMG coordination links of the active wave drawn between live robot positions (and the WMS hub). */
export function CoordOverlay({ state }: { state: TwinState }) {
  const on = useStore((s) => s.toggles.coord);
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(MAX_LINKS * 6), 3));
    g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(MAX_LINKS * 6), 3));
    return g;
  }, []);
  const hub = useMemo(() => new THREE.Color(C.ink), []);
  const peer = useMemo(() => new THREE.Color("#6366f1"), []);
  useFrame(() => {
    if (!on) return;
    const t = getLocalT();
    const w = waveAt(state, t);
    const ix = indexOf(state);
    const pos = geo.getAttribute("position") as THREE.BufferAttribute;
    const col = geo.getAttribute("color") as THREE.BufferAttribute;
    let n = 0;
    const at = (id: string): [number, number, number] | null => {
      if (ix.wms && id === ix.wms.id) return [ix.wmsPos[0], 2.3, ix.wmsPos[1] - 0.9];
      const r = ix.robot.get(id);
      if (!r || !r.physical) return null;
      const p = robotAt(state, id, t);
      return [p.x, r.mobile ? 0.7 : 1.6, p.y];
    };
    for (const [a, b] of w?.graph?.links ?? []) {
      if (n >= MAX_LINKS) break;
      const pa = at(a),
        pb = at(b);
      if (!pa || !pb) continue;
      const c = w?.graph?.coordinators.includes(a) || w?.graph?.coordinators.includes(b) ? hub : peer;
      pos.setXYZ(n * 2, ...pa);
      pos.setXYZ(n * 2 + 1, ...pb);
      col.setXYZ(n * 2, c.r, c.g, c.b);
      col.setXYZ(n * 2 + 1, c.r, c.g, c.b);
      n++;
    }
    geo.setDrawRange(0, n * 2);
    pos.needsUpdate = true;
    col.needsUpdate = true;
  });
  if (!on) return null;
  return (
    <lineSegments geometry={geo} frustumCulled={false}>
      <lineBasicMaterial vertexColors transparent opacity={0.45} depthWrite={false} />
    </lineSegments>
  );
}
