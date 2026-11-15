"use client";
// R3F scene of the communication view (plan §6.7). Static nodes/edges are React; all traffic is updated per frame
// through refs from the shared clock (getLocalT) — no React re-render per frame.
import { createRef, useLayoutEffect, useMemo, useRef, type RefObject } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { ROLE_COLOR, failedRobotsAt, robotAt, STATUS_COLOR, waveAt } from "@/lib/derive";
import { getLocalT, useStore } from "@/lib/store";
import type { TwinState, Wave } from "@/lib/types";
import {
  ACP_POS,
  C,
  LEARNER_POS,
  PORT_Y,
  WITNESS_POS,
  arc,
  arcPoints,
  classifyLink,
  inFlight,
  layoutNodes,
  verdictColor,
  type NodeLayout,
} from "./model";

export const commsPortal = createRef<HTMLDivElement>() as RefObject<HTMLDivElement>;

/** ACP / learner meshes flashed by the traffic layer */
const fx = {
  acp: null as THREE.MeshStandardMaterial | null,
  acpShell: null as THREE.MeshBasicMaterial | null,
  learner: null as THREE.MeshStandardMaterial | null,
};

export default function CommsCanvas({ state }: { state: TwinState }) {
  const select = useStore((s) => s.select);
  return (
    <>
      <Canvas
        dpr={[1, 2]}
        gl={{ antialias: true }}
        camera={{ position: [0, 13.5, 17.5], fov: 38, near: 0.3, far: 200 }}
        onPointerMissed={() => select(null)}
      >
        <CommsScene state={state} />
      </Canvas>
      <div ref={commsPortal} className="pointer-events-none absolute inset-0 z-0 overflow-hidden" />
    </>
  );
}

function CommsScene({ state }: { state: TwinState }) {
  const layout = useMemo(() => layoutNodes(state), [state]);
  // re-render only when the wave changes (topology switch)
  const waveNo = useStore((s) => (s.state ? (waveAt(s.state, s.clock.t)?.number ?? 0) : 0));
  const wave = state.waves.find((w) => w.number === waveNo) ?? null;
  return (
    <>
      <color attach="background" args={[C.bg]} />
      <fog attach="fog" args={[C.bg, 30, 60]} />
      <ambientLight intensity={1.15} />
      <hemisphereLight args={["#ffffff", "#d8dee8", 0.6]} />
      <directionalLight position={[8, 16, 10]} intensity={1.4} />
      <OrbitControls makeDefault target={[0, 0.8, -1]} enableDamping dampingFactor={0.12} maxPolarAngle={Math.PI * 0.47} minDistance={8} maxDistance={45} />
      <Floor />
      <Hub layout={layout} />
      {layout.robots
        .filter((r) => r.id !== layout.hub)
        .map((r) => (
          <RobotNode key={r.id} state={state} id={r.id} role={r.role} pos={layout.pos.get(r.id)!} wave={wave} />
        ))}
      <Acp />
      <Witness />
      <Learner />
      <AssuranceLinks />
      {wave?.graph && <Edges key={`${wave.number}-${state.live?.session_id ?? ""}`} layout={layout} wave={wave} />}
      <Traffic state={state} layout={layout} />
    </>
  );
}

function Floor() {
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position-y={-0.01}>
        <circleGeometry args={[15, 96]} />
        <meshStandardMaterial color={C.floor} roughness={0.95} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position-y={0}>
        <ringGeometry args={[14.9, 15, 128]} />
        <meshBasicMaterial color={C.line2} />
      </mesh>
      <gridHelper args={[30, 30, "#d5dbe5", "#dde2ea"]} position-y={0.002} />
    </group>
  );
}

function Label({ y, children, tone }: { y: number; children: React.ReactNode; tone?: string }) {
  return (
    <Html portal={commsPortal} position={[0, y, 0]} center zIndexRange={[30, 10]} className="w3-label">
      <div className="w3-robot" style={tone ? { borderColor: tone } : undefined}>
        {children}
      </div>
    </Html>
  );
}

function Hub({ layout }: { layout: NodeLayout }) {
  const ring = useRef<THREE.Mesh>(null);
  useFrame((_, dt) => {
    if (ring.current) ring.current.rotation.z += dt * 0.4;
  });
  if (!layout.hub) return null;
  return (
    <group position={layout.pos.get(layout.hub)!} onClick={(e) => (e.stopPropagation(), useStore.getState().select({ kind: "robot", id: layout.hub! }))}>
      <mesh position-y={0.12}>
        <cylinderGeometry args={[1.5, 1.6, 0.24, 6]} />
        <meshStandardMaterial color="#f8fafc" roughness={0.7} />
      </mesh>
      <mesh position-y={1.2}>
        <cylinderGeometry args={[0.85, 1.05, 2.1, 6]} />
        <meshStandardMaterial color="#1e293b" roughness={0.45} metalness={0.25} />
      </mesh>
      <mesh ref={ring} position-y={2.35} rotation-x={Math.PI / 2}>
        <torusGeometry args={[1.0, 0.05, 8, 6]} />
        <meshBasicMaterial color={C.hub} />
      </mesh>
      <mesh position-y={2.32}>
        <cylinderGeometry args={[0.55, 0.55, 0.08, 6]} />
        <meshBasicMaterial color={C.hub} />
      </mesh>
      <Label y={3.1}>
        WMS hub <small className="text-muted">coordinator</small>
      </Label>
    </group>
  );
}

function RobotNode({ state, id, role, pos, wave }: { state: TwinState; id: string; role: string; pos: THREE.Vector3; wave: Wave | null }) {
  const body = useRef<THREE.MeshStandardMaterial>(null);
  const light = useRef<THREE.MeshBasicMaterial>(null);
  const ring = useRef<THREE.Mesh>(null);
  const ringMat = useRef<THREE.MeshBasicMaterial>(null);
  const color = ROLE_COLOR[role] ?? C.ink2;
  const g = wave?.graph;
  const coord = !!g && (g.coordinators.includes(id) || Object.values(g.cell_coordinators).includes(id));
  const excluded = !!wave?.excluded.includes(id);
  const tmp = useMemo(() => new THREE.Color(), []);
  useFrame(() => {
    const t = getLocalT();
    const failed = failedRobotsAt(state, t).includes(id) || excluded;
    if (body.current) body.current.color.set(failed ? C.failed : color);
    const st = failed ? "FAILED" : robotAt(state, id, t).status;
    if (light.current) light.current.color.set(tmp.set(STATUS_COLOR[st] ?? "#94a3b8"));
    if (ring.current && ringMat.current) {
      ring.current.visible = failed || coord;
      ringMat.current.color.set(failed ? C.bad : C.direct);
    }
  });
  return (
    <group position={pos} onClick={(e) => (e.stopPropagation(), useStore.getState().select({ kind: "robot", id }))}>
      <mesh position-y={0.1}>
        <cylinderGeometry args={[0.62, 0.68, 0.2, 32]} />
        <meshStandardMaterial color="#f8fafc" roughness={0.7} />
      </mesh>
      <mesh position-y={0.55}>
        <boxGeometry args={[0.95, 0.62, 0.95]} />
        <meshStandardMaterial ref={body} color={color} roughness={0.5} />
      </mesh>
      <mesh position-y={0.98}>
        <sphereGeometry args={[0.13, 16, 12]} />
        <meshBasicMaterial ref={light} color="#94a3b8" />
      </mesh>
      <mesh ref={ring} rotation-x={-Math.PI / 2} position-y={0.02} visible={false}>
        <ringGeometry args={[0.9, 1.02, 48]} />
        <meshBasicMaterial ref={ringMat} color={C.direct} side={THREE.DoubleSide} />
      </mesh>
      <Label y={1.55} tone={color}>
        <span className="inline-block h-[7px] w-[7px] rounded-full" style={{ background: color }} />
        {id}
        {coord && <small className="text-samg">coord</small>}
      </Label>
    </group>
  );
}

function Acp() {
  const core = useRef<THREE.Mesh>(null);
  const shell = useRef<THREE.Mesh>(null);
  useFrame((_, dt) => {
    if (core.current) core.current.rotation.y += dt * 0.6;
    if (shell.current) shell.current.rotation.y -= dt * 0.2;
  });
  return (
    <group position={ACP_POS}>
      <mesh position-y={0.9}>
        <cylinderGeometry args={[0.08, 0.32, 1.8, 12]} />
        <meshStandardMaterial color="#cbd2dd" />
      </mesh>
      <mesh ref={core} position-y={PORT_Y.acp}>
        <octahedronGeometry args={[0.75, 0]} />
        <meshStandardMaterial ref={(m) => void (fx.acp = m)} color={C.acp} emissive={C.acp} emissiveIntensity={0.15} flatShading roughness={0.35} />
      </mesh>
      <mesh ref={shell} position-y={PORT_Y.acp}>
        <icosahedronGeometry args={[1.25, 1]} />
        <meshBasicMaterial ref={(m) => void (fx.acpShell = m)} color={C.acp} wireframe transparent opacity={0.22} />
      </mesh>
      <Label y={4.2} tone={C.acp}>
        ACP <small className="text-muted">assurance · verdicts</small>
      </Label>
    </group>
  );
}

function Witness() {
  const iris = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    if (iris.current) iris.current.rotation.y = 0.6 + Math.sin(clock.elapsedTime * 0.5) * 0.5;
  });
  return (
    <group position={WITNESS_POS}>
      <mesh position-y={1.6}>
        <cylinderGeometry args={[0.07, 0.12, 3.2, 12]} />
        <meshStandardMaterial color="#cbd2dd" />
      </mesh>
      <group ref={iris} position-y={PORT_Y.witness}>
        <mesh>
          <sphereGeometry args={[0.55, 32, 20]} />
          <meshStandardMaterial color="#ffffff" roughness={0.3} />
        </mesh>
        <mesh position-z={0.42}>
          <sphereGeometry args={[0.24, 24, 16]} />
          <meshBasicMaterial color={C.witness} />
        </mesh>
        <mesh position-z={0.6}>
          <sphereGeometry args={[0.09, 12, 8]} />
          <meshBasicMaterial color={C.ink} />
        </mesh>
      </group>
      <Label y={4.75} tone={C.witness}>
        Witness <small className="text-muted">independent observer</small>
      </Label>
    </group>
  );
}

function Learner() {
  return (
    <group position={LEARNER_POS}>
      <mesh position-y={0.45}>
        <boxGeometry args={[1.5, 0.9, 1.1]} />
        <meshStandardMaterial ref={(m) => void (fx.learner = m)} color="#e6f4f7" emissive={C.learner} emissiveIntensity={0} roughness={0.5} />
      </mesh>
      {[0, 1, 2, 3].map((i) => (
        <mesh key={i} position={[-0.48 + i * 0.32, 0.95 + i * 0.09, 0]}>
          <boxGeometry args={[0.2, 0.2 + i * 0.18, 0.5]} />
          <meshStandardMaterial color={C.learner} />
        </mesh>
      ))}
      <Label y={2.3} tone={C.learner}>
        LinUCB learner <small className="text-muted">guarded update</small>
      </Label>
    </group>
  );
}

/** Static faint channels: witness → ACP → learner. */
function AssuranceLinks() {
  const geos = useMemo(() => {
    const w = arcPoints(new THREE.Vector3(WITNESS_POS.x, PORT_Y.witness, WITNESS_POS.z), new THREE.Vector3(ACP_POS.x, PORT_Y.acp, ACP_POS.z), 0.8);
    const l = arcPoints(new THREE.Vector3(ACP_POS.x, PORT_Y.acp, ACP_POS.z), new THREE.Vector3(LEARNER_POS.x, PORT_Y.learner, LEARNER_POS.z), 0.8);
    return [new THREE.TubeGeometry(w, 32, 0.025, 6), new THREE.TubeGeometry(l, 32, 0.025, 6)];
  }, []);
  return (
    <>
      <mesh geometry={geos[0]}>
        <meshBasicMaterial color={C.witness} transparent opacity={0.28} />
      </mesh>
      <mesh geometry={geos[1]}>
        <meshBasicMaterial color={C.learner} transparent opacity={0.28} />
      </mesh>
    </>
  );
}

/** Coordination graph of the current wave; tubes "draw in" on a topology switch. */
function Edges({ layout, wave }: { layout: NodeLayout; wave: Wave }) {
  const g = wave.graph!;
  const items = useMemo(
    () =>
      g.links
        .map(([a, b]) => {
          const c = arc(layout, a, b);
          if (!c) return null;
          const kind = classifyLink(g, a, b);
          const geo = new THREE.TubeGeometry(c, 40, kind === "hub" ? 0.045 : 0.035, 6);
          return { key: `${a}|${b}`, geo, kind };
        })
        .filter((x): x is NonNullable<typeof x> => !!x),
    [g, layout],
  );
  const start = useRef<number | null>(null);
  const done = useRef(false);
  useLayoutEffect(() => {
    for (const it of items) it.geo.setDrawRange(0, 0);
    return () => items.forEach((it) => it.geo.dispose());
  }, [items]);
  useFrame(({ clock }) => {
    if (done.current) return;
    start.current ??= clock.elapsedTime;
    const f = Math.min(1, (clock.elapsedTime - start.current) / 0.9);
    const e = 1 - Math.pow(1 - f, 3);
    for (const it of items) it.geo.setDrawRange(0, Math.ceil((it.geo.index?.count ?? 0) * e / 6) * 6);
    if (f >= 1) done.current = true;
  });
  return (
    <>
      {items.map((it) => (
        <mesh key={it.key} geometry={it.geo}>
          <meshBasicMaterial color={C[it.kind]} transparent opacity={it.kind === "hub" ? 0.5 : 0.6} />
        </mesh>
      ))}
    </>
  );
}

// ---------------------------------------------------------------- per-frame traffic

const N_HANDOFF = 24;
const UP = new THREE.Vector3(0, 1, 0);
const acpArcs = new WeakMap<NodeLayout, Map<string, THREE.QuadraticBezierCurve3>>();
function toAcpArc(layout: NodeLayout, id: string, acp: THREE.Vector3): THREE.QuadraticBezierCurve3 | null {
  let m = acpArcs.get(layout);
  if (!m) acpArcs.set(layout, (m = new Map()));
  let c = m.get(id);
  if (!c) {
    const p = layout.pos.get(id);
    if (!p) return null;
    c = arcPoints(new THREE.Vector3(p.x, PORT_Y.robot + 0.2, p.z), acp, 3.2);
    m.set(id, c);
  }
  return c;
}
const N_CLAIM = 48;
const N_WITNESS = 16;
const N_UPDATE = 4;

function Traffic({ state, layout }: { state: TwinState; layout: NodeLayout }) {
  const handoffs = useRef<(THREE.Mesh | null)[]>([]);
  const claims = useRef<(THREE.Mesh | null)[]>([]);
  const witness = useRef<(THREE.Mesh | null)[]>([]);
  const updates = useRef<(THREE.Mesh | null)[]>([]);
  const beams = useRef<(THREE.Mesh | null)[]>([]);
  const v = useMemo(() => new THREE.Vector3(), []);
  const v2 = useMemo(() => new THREE.Vector3(), []);
  const acpPort = useMemo(() => new THREE.Vector3(ACP_POS.x, PORT_Y.acp, ACP_POS.z), []);
  const eyePort = useMemo(() => new THREE.Vector3(WITNESS_POS.x, PORT_Y.witness, WITNESS_POS.z), []);
  const learnPort = useMemo(() => new THREE.Vector3(LEARNER_POS.x, PORT_Y.learner + 0.6, LEARNER_POS.z), []);
  const toAcp = (id: string) => toAcpArc(layout, id, acpPort);
  const eyeToAcp = useMemo(() => arcPoints(eyePort, acpPort, 0.8), [eyePort, acpPort]);
  const acpToLearner = useMemo(() => arcPoints(acpPort, learnPort, 0.8), [acpPort, learnPort]);
  const tmp = useMemo(() => new THREE.Color(), []);

  useFrame(() => {
    const t = getLocalT();
    const f = inFlight(state, t);

    // handoff packets hop by hop along the coordination path
    for (let i = 0; i < N_HANDOFF; i++) {
      const m = handoffs.current[i];
      if (!m) continue;
      const h = f.handoffs[i];
      if (!h || h.handoff.path.length < 2) {
        m.visible = false;
        continue;
      }
      const path = h.handoff.path;
      const hops = path.length - 1;
      const x = Math.min(h.progress, 0.9999) * hops;
      const seg = Math.floor(x);
      const c = arc(layout, path[seg], path[seg + 1]);
      if (!c) {
        m.visible = false;
        continue;
      }
      c.getPoint(x - seg, v);
      m.position.copy(v);
      m.visible = true;
    }

    // signed claims robot → ACP; verdict colour on arrival
    let verdict: string | null = null;
    for (let i = 0; i < N_CLAIM; i++) {
      const m = claims.current[i];
      if (!m) continue;
      const c = f.claims[i];
      const curve = c ? toAcp(c.claim.agent) : null;
      if (!c || !curve) {
        m.visible = false;
        continue;
      }
      const p = Math.min(c.progress / 0.75, 1);
      curve.getPoint(p, v);
      m.position.copy(v);
      m.rotation.y = p * 4;
      const arrived = c.progress >= 0.75;
      const col = arrived ? verdictColor(c.claim) : C.claim;
      (m.material as THREE.MeshBasicMaterial).color.set(col);
      m.scale.setScalar(arrived ? 1.25 : 1);
      if (arrived && (verdict == null || col === C.bad)) verdict = col;
      m.visible = true;
    }
    if (fx.acpShell) {
      fx.acpShell.color.set(verdict ?? C.acp);
      fx.acpShell.opacity = verdict ? 0.55 : 0.22;
    }
    if (fx.acp) fx.acp.emissiveIntensity = verdict ? 0.45 : 0.15;

    // witness observations: eye → robot (observe), packet eye → ACP
    for (let i = 0; i < N_WITNESS; i++) {
      const m = witness.current[i];
      const b = beams.current[i];
      const w = f.witness[i];
      if (!m || !b) continue;
      if (!w) {
        m.visible = false;
        b.visible = false;
        continue;
      }
      eyeToAcp.getPoint(w.progress, v);
      m.position.copy(v);
      m.visible = true;
      const rp = w.robot ? layout.pos.get(w.robot) : null;
      if (rp && w.progress < 0.6) {
        // thin cylinder eye → observed robot
        v2.set(rp.x, PORT_Y.robot, rp.z).sub(eyePort);
        const len = v2.length();
        b.position.copy(eyePort).addScaledVector(v2, 0.5);
        b.quaternion.setFromUnitVectors(UP, v2.normalize());
        b.scale.set(1, len, 1);
        (b.material as THREE.MeshBasicMaterial).opacity = 0.5 * (1 - w.progress / 0.6);
        b.visible = true;
      } else b.visible = false;
    }

    // guarded update ACP → learner after wave commit
    let learnFlash = 0;
    for (let i = 0; i < N_UPDATE; i++) {
      const m = updates.current[i];
      if (!m) continue;
      const u = f.updates[i];
      if (!u) {
        m.visible = false;
        continue;
      }
      const p = Math.min(u.progress / 0.7, 1);
      acpToLearner.getPoint(p, v);
      m.position.copy(v);
      const ok = !!u.wave.learning?.applied;
      (m.material as THREE.MeshBasicMaterial).color.set(tmp.set(ok ? C.ok : C.bad));
      m.visible = true;
      if (u.progress >= 0.7) learnFlash = ok ? 0.5 : 0.2;
    }
    if (fx.learner) fx.learner.emissiveIntensity = learnFlash;
  });

  return (
    <>
      {Array.from({ length: N_HANDOFF }, (_, i) => (
        <mesh key={`h${i}`} ref={(m) => void (handoffs.current[i] = m)} visible={false}>
          <sphereGeometry args={[0.2, 16, 12]} />
          <meshBasicMaterial color={C.handoff} />
        </mesh>
      ))}
      {Array.from({ length: N_CLAIM }, (_, i) => (
        <mesh key={`c${i}`} ref={(m) => void (claims.current[i] = m)} visible={false}>
          <boxGeometry args={[0.36, 0.24, 0.06]} />
          <meshBasicMaterial color={C.claim} />
        </mesh>
      ))}
      {Array.from({ length: N_WITNESS }, (_, i) => (
        <mesh key={`w${i}`} ref={(m) => void (witness.current[i] = m)} visible={false}>
          <octahedronGeometry args={[0.13, 0]} />
          <meshBasicMaterial color={C.witness} />
        </mesh>
      ))}
      {Array.from({ length: N_UPDATE }, (_, i) => (
        <mesh key={`u${i}`} ref={(m) => void (updates.current[i] = m)} visible={false}>
          <dodecahedronGeometry args={[0.24, 0]} />
          <meshBasicMaterial color={C.ok} />
        </mesh>
      ))}
      {Array.from({ length: N_WITNESS }, (_, i) => (
        <mesh key={`b${i}`} ref={(m) => void (beams.current[i] = m)} visible={false}>
          <cylinderGeometry args={[0.018, 0.018, 1, 6]} />
          <meshBasicMaterial color={C.witness} transparent opacity={0.5} />
        </mesh>
      ))}
    </>
  );
}
