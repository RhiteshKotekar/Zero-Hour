// Comms view model (plan §6.7): node layout, link classification and message-in-flight derivation.
// Pure functions of (state, t) — nothing here decides anything; it reveals the recorded/live SAMG traffic.
import * as THREE from "three";
import { assignmentAt, claimsInFlight, handoffsInFlight } from "@/lib/derive";
import type { Claim, CoordGraph, TwinState, Wave, WitnessEvent } from "@/lib/types";

export const C = {
  bg: "#eef1f5",
  floor: "#e6eaf0",
  ink: "#0b1220",
  ink2: "#3d4a5f",
  muted: "#7b8699",
  line2: "#cfd6e2",
  hub: "#2563eb",
  cell: "#7c3aed",
  bridge: "#c2700a",
  direct: "#0e7490",
  handoff: "#2563eb",
  claim: "#7c3aed",
  ok: "#059669",
  bad: "#d92d2d",
  witness: "#0e7490",
  acp: "#7c3aed",
  learner: "#0e7490",
  failed: "#94a3b8",
} as const;

export type LinkKind = "hub" | "cell" | "bridge" | "direct";
export const LINK_LABEL: Record<LinkKind, string> = {
  hub: "Hub link (coordinator)",
  cell: "Cell link (within a functional cell)",
  bridge: "Bridge (cell coordinator ↔ cell coordinator)",
  direct: "Direct peer link",
};

/** display windows (sim seconds) for instantaneous messages */
export const CLAIM_WINDOW = 2;
export const WITNESS_WINDOW = 1.4;
export const UPDATE_WINDOW = 2.5;

export const ACP_POS = new THREE.Vector3(0, 0, -7.6);
export const WITNESS_POS = new THREE.Vector3(-5.6, 0, -6.8);
export const LEARNER_POS = new THREE.Vector3(5.6, 0, -6.8);
/** heights where links attach */
export const PORT_Y = { robot: 1.0, hub: 2.1, acp: 2.6, witness: 3.7, learner: 1.3 };

const ROLE_ORDER = ["picking", "transport", "packing", "dispatch"];

export interface NodeLayout {
  /** robot id (incl. WMS) → ground position */
  pos: Map<string, THREE.Vector3>;
  hub: string | null;
  robots: TwinState["robots"];
}

/** WMS at the centre; robots on a front arc grouped by role; assurance row (witness, ACP, learner) behind. */
export function layoutNodes(state: TwinState): NodeLayout {
  const pos = new Map<string, THREE.Vector3>();
  const hubR = state.robots.find((r) => r.role === "control") ?? null;
  if (hubR) pos.set(hubR.id, new THREE.Vector3(0, 0, 0));
  const robots = state.robots
    .filter((r) => r.role !== "control")
    .sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) || a.id.localeCompare(b.id));
  // slots with a gap between role groups
  const slots: number[] = [];
  let k = 0;
  robots.forEach((r, i) => {
    if (i > 0 && robots[i - 1].role !== r.role) k += 0.7;
    slots.push(k);
    k += 1;
  });
  const span = Math.max(k - 1, 1);
  const a0 = Math.PI + 0.32;
  const a1 = -0.32;
  const R = 8.6;
  robots.forEach((r, i) => {
    const a = a0 + ((a1 - a0) * slots[i]) / span;
    pos.set(r.id, new THREE.Vector3(Math.cos(a) * R, 0, Math.sin(a) * R * 0.82 + 0.6));
  });
  return { pos, hub: hubR?.id ?? null, robots: state.robots };
}

export function classifyLink(g: CoordGraph, a: string, b: string): LinkKind {
  if (g.coordinators.includes(a) || g.coordinators.includes(b)) return "hub";
  const cellOf = new Map<string, string>();
  for (const [cell, members] of Object.entries(g.cells)) for (const m of members) cellOf.set(m, cell);
  const cc = new Set(Object.values(g.cell_coordinators));
  if (cc.has(a) && cc.has(b) && cellOf.get(a) !== cellOf.get(b)) return "bridge";
  if (cellOf.has(a) && cellOf.get(a) === cellOf.get(b)) return "cell";
  return "direct";
}

const portY = (id: string, hub: string | null) => (id === hub ? PORT_Y.hub : PORT_Y.robot);

const curveCache = new WeakMap<NodeLayout, Map<string, THREE.QuadraticBezierCurve3>>();
/** Arc between two nodes (cached per layout, direction-specific). */
export function arc(layout: NodeLayout, a: string, b: string): THREE.QuadraticBezierCurve3 | null {
  let m = curveCache.get(layout);
  if (!m) curveCache.set(layout, (m = new Map()));
  const key = `${a}|${b}`;
  const hit = m.get(key);
  if (hit) return hit;
  const pa = layout.pos.get(a);
  const pb = layout.pos.get(b);
  if (!pa || !pb) return null;
  const A = new THREE.Vector3(pa.x, portY(a, layout.hub), pa.z);
  const B = new THREE.Vector3(pb.x, portY(b, layout.hub), pb.z);
  const mid = A.clone().add(B).multiplyScalar(0.5);
  mid.y += 0.7 + A.distanceTo(B) * 0.07;
  const c = new THREE.QuadraticBezierCurve3(A, mid, B);
  m.set(key, c);
  return c;
}

/** Arc from a point to another point (claims → ACP etc.). */
export function arcPoints(A: THREE.Vector3, B: THREE.Vector3, lift: number): THREE.QuadraticBezierCurve3 {
  const mid = A.clone().add(B).multiplyScalar(0.5);
  mid.y += lift;
  return new THREE.QuadraticBezierCurve3(A, mid, B);
}

export function witnessInFlight(state: TwinState, t: number): { ev: WitnessEvent; progress: number; robot: string | null }[] {
  const out: { ev: WitnessEvent; progress: number; robot: string | null }[] = [];
  for (const ev of state.witness_events ?? []) {
    if (ev.t > t) break;
    if (t - ev.t < WITNESS_WINDOW) out.push({ ev, progress: (t - ev.t) / WITNESS_WINDOW, robot: assignmentAt(state, ev.task, t)?.agent ?? null });
  }
  return out;
}

/** Guarded learner updates ACP → learner right after a wave is committed. */
export function updatesInFlight(state: TwinState, t: number): { wave: Wave; progress: number }[] {
  const out: { wave: Wave; progress: number }[] = [];
  for (const w of state.waves) {
    if (!w.learning || w.status === "preview") continue;
    if (w.t1 <= t && t - w.t1 < UPDATE_WINDOW) out.push({ wave: w, progress: (t - w.t1) / UPDATE_WINDOW });
  }
  return out;
}

export const verdictColor = (c: Claim): string =>
  c.evidence === "CORROBORATED" && c.auth === "AUTHENTICATED" ? C.ok : c.evidence === "DISPUTED" || c.auth !== "AUTHENTICATED" ? C.bad : C.muted;

export function inFlight(state: TwinState, t: number) {
  return {
    handoffs: handoffsInFlight(state, t),
    claims: claimsInFlight(state, t, CLAIM_WINDOW),
    witness: witnessInFlight(state, t),
    updates: updatesInFlight(state, t),
  };
}
