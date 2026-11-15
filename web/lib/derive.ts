// Pure derivations of (state, t) — ported from contract/reference/control_room_light.html.
// Nothing here decides anything: it only reveals what the recorded/live SAMG state says at time t.
// Per-state lookup indices are cached in a WeakMap (keyed by the state object) so per-frame calls stay cheap.

import type {
  Assignment,
  Claim,
  Congestion,
  Handoff,
  Robot,
  RobotStatus,
  Segment,
  Station,
  Task,
  TaskState,
  TwinEvent,
  TwinState,
  Wave,
} from "./types";

// ---------------------------------------------------------------- palettes (theme §6.2)
export const ROLE_COLOR: Record<string, string> = {
  picking: "#2563eb",
  transport: "#0d9488",
  packing: "#7c3aed",
  dispatch: "#ea580c",
  control: "#0b1220",
};
export const LEVEL_COLOR: Record<string, string> = {
  info: "#94a3b8",
  samg: "#0e7490",
  move: "#cbd5e1",
  warn: "#c2700a",
  ok: "#059669",
  bad: "#d92d2d",
  sec: "#7c3aed",
};
export const STATUS_COLOR: Record<string, string> = {
  MOVING: "#2563eb",
  TRANSPORTING: "#0d9488",
  PICKING: "#c2700a",
  PACKING: "#7c3aed",
  WAITING: "#d97706",
  FAILED: "#d92d2d",
  IDLE: "#94a3b8",
  COMPLETED: "#059669",
};
export const TASK_STATUS_LABEL: Record<string, string> = {
  VERIFIED_COMPLETE: "VERIFIED",
  REPORTED_COMPLETE: "REPORTED",
  EXECUTING: "EXECUTING",
  ASSIGNED: "ASSIGNED",
  OPEN: "PENDING",
};

// ---------------------------------------------------------------- formatting
export function clockAt(state: Pick<TwinState, "start_clock">, t: number): string {
  const [h, m, s] = state.start_clock.split(":").map(Number);
  const x = h * 3600 + m * 60 + s + Math.floor(Math.max(0, t));
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(Math.floor(x / 3600) % 24)}:${p(Math.floor(x / 60) % 60)}:${p(x % 60)}`;
}
export const fmtS = (s: number | null | undefined): string =>
  s == null ? "—" : s >= 60 ? `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s` : `${s.toFixed(1)}s`;
export const pct = (x: number | null | undefined): string => (x == null ? "—" : `${Math.round(x * 100)}%`);
export const topoLabel = (t: string | null | undefined): string => (t ?? "—").replace(/_/g, " ");

// ---------------------------------------------------------------- indices (cached per state object)
interface NSeg extends Omit<Segment, "t1"> {
  t1: number; // Infinity for open-ended
}
export interface StateIndex {
  task: Map<string, Task>;
  robot: Map<string, Robot>;
  segs: Map<string, NSeg[]>;
  /** fixed position (station robots) in grid units, centre-based */
  fixed: Map<string, [number, number] | null>;
  wms: Robot | undefined;
  wmsPos: [number, number];
  mobile: string[];
  physical: Robot[];
  disputed: Claim[];
  orderSkus: Set<string>;
  stages: string[]; // stageOf per event index
}
const CACHE = new WeakMap<TwinState, StateIndex>();

export function stationCenter(state: TwinState, id: string | null): [number, number] | null {
  const s: Station | undefined = state.layout.stations.find((x) => x.id === id);
  if (!s) return null;
  const [x0, y0, x1, y1] = s.rect;
  return [(x0 + x1 + 1) / 2, (y0 + y1 + 1) / 2];
}

export function indexOf(state: TwinState): StateIndex {
  let ix = CACHE.get(state);
  if (ix) return ix;
  const wms = state.robots.find((r) => r.lead);
  ix = {
    task: new Map(state.tasks.map((t) => [t.id, t])),
    robot: new Map(state.robots.map((r) => [r.id, r])),
    segs: new Map(state.robots.map((r) => [r.id, r.segments.map((s) => ({ ...s, t1: s.t1 == null ? Infinity : s.t1 }))])),
    fixed: new Map(state.robots.map((r) => [r.id, r.mobile ? null : stationCenter(state, r.station)])),
    wms,
    wmsPos: wms ? [wms.home[0] + 0.5, wms.home[1] + 0.5] : [26.5, 1.5],
    mobile: state.robots.filter((r) => r.mobile).map((r) => r.id),
    physical: state.robots.filter((r) => r.physical),
    disputed: state.claims.filter((c) => c.evidence === "DISPUTED"),
    orderSkus: new Set(state.orders.flatMap((o) => o.items)),
    stages: state.events.map(stageOf),
  };
  CACHE.set(state, ix);
  return ix;
}

// ---------------------------------------------------------------- robots
/** Position along a polyline of cells at fraction f; returns centre-based [x, y, dx, dy]. */
export function pathPos(p: [number, number][], f: number): [number, number, number, number] {
  const n = p.length - 1;
  const k = Math.max(0, Math.min(n, f * n));
  const i = Math.max(0, Math.min(Math.floor(k), n - 1));
  const fr = n ? k - i : 0;
  const a = p[i];
  const b = p[Math.min(i + 1, n)];
  return [a[0] + (b[0] - a[0]) * fr + 0.5, a[1] + (b[1] - a[1]) * fr + 0.5, b[0] - a[0], b[1] - a[1]];
}

export interface RobotPose {
  /** grid coordinates, cell-centre based (x right, y down) */
  x: number;
  y: number;
  dx?: number;
  dy?: number;
  status: RobotStatus;
  task?: string;
  battery: number;
  odo: number;
  seg: NSeg | null;
  idx: number;
  /** fraction through the current segment (0..1) when inside a finite segment */
  f?: number;
}

export function robotAt(state: TwinState, id: string, t: number): RobotPose {
  const ix = indexOf(state);
  const r = ix.robot.get(id);
  const segs = ix.segs.get(id) ?? [];
  const fixed = ix.fixed.get(id) ?? null;
  if (!r) return { x: 0, y: 0, status: "IDLE", battery: 0, odo: 0, seg: null, idx: -1 };
  let lo = 0,
    hi = segs.length - 1,
    k = -1;
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (segs[m].t0 <= t) {
      k = m;
      lo = m + 1;
    } else hi = m - 1;
  }
  const home: [number, number] = fixed ? [fixed[0], fixed[1]] : [r.home[0] + 0.5, r.home[1] + 0.5];
  if (k < 0) return { x: home[0], y: home[1], status: "IDLE", battery: r.battery0, odo: 0, seg: null, idx: -1 };
  const s = segs[k];
  if (t >= s.t1) {
    const end = s.kind === "move" && s.path?.length ? s.path[s.path.length - 1] : s.cell;
    const p = fixed || [end[0] + 0.5, end[1] + 0.5];
    const later = k < segs.length - 1;
    return {
      x: p[0],
      y: p[1],
      status: later ? "IDLE" : r.failed_at != null ? "FAILED" : "COMPLETED",
      battery: s.b1,
      odo: s.o1,
      seg: null,
      idx: k,
    };
  }
  const f = Math.min(1, (t - s.t0) / Math.max(s.t1 - s.t0, 1e-9));
  const battery = s.b0 + (s.b1 - s.b0) * (Number.isFinite(s.t1) ? f : 0);
  const odo = s.o0 + (s.o1 - s.o0) * (Number.isFinite(s.t1) ? f : 0);
  if (s.kind === "move" && s.path?.length) {
    const [x, y, dx, dy] = pathPos(s.path, f);
    return { x, y, dx, dy, status: s.status, task: s.task, battery, odo, seg: s, idx: k, f };
  }
  const p = fixed || [s.cell[0] + 0.5, s.cell[1] + 0.5];
  return { x: p[0], y: p[1], status: s.status, task: s.task, battery, odo, seg: s, idx: k, f: Number.isFinite(s.t1) ? f : undefined };
}

export interface RobotRoute {
  /** remaining points of the current move, starting at the robot */
  remaining: [number, number][];
  /** later move legs of the same task */
  future: [number, number][][];
  dest: [number, number] | null;
}
/** Route of a robot at t: remaining current move + next moves of the same task (as planned). */
export function robotRoute(state: TwinState, id: string, t: number, pose?: RobotPose): RobotRoute {
  const s = pose ?? robotAt(state, id, t);
  const out: RobotRoute = { remaining: [], future: [], dest: null };
  if (!s.seg || !s.task) return out;
  const segs = indexOf(state).segs.get(id) ?? [];
  if (s.seg.kind === "move" && s.seg.path?.length) {
    const p = s.seg.path,
      n = p.length - 1,
      k = Math.min(Math.floor((s.f ?? 0) * n) + 1, n);
    out.remaining = [[s.x, s.y], ...p.slice(k).map((c) => [c[0] + 0.5, c[1] + 0.5] as [number, number])];
    out.dest = [p[n][0] + 0.5, p[n][1] + 0.5];
  }
  for (const q of segs.slice(s.idx + 1)) {
    if (q.task !== s.task) break;
    if (q.kind === "move" && q.path?.length) {
      const leg = q.path.map((c) => [c[0] + 0.5, c[1] + 0.5] as [number, number]);
      out.future.push(leg);
      out.dest = leg[leg.length - 1];
    }
  }
  return out;
}

// ---------------------------------------------------------------- tasks / waves / orders
export function taskStateAt(state: TwinState, taskId: string, t: number): TaskState | null {
  const task = indexOf(state).task.get(taskId);
  if (!task) return null;
  let s: TaskState | null = null;
  for (const x of task.states) {
    if (x.t <= t) s = x;
    else break;
  }
  return s;
}

export function waveAt(state: TwinState, t: number): Wave | null {
  let w: Wave | null = state.waves[0] ?? null;
  for (const x of state.waves) if (x.t0 <= t) w = x;
  return w;
}

export function assignmentAt(state: TwinState, taskId: string, t: number): Assignment | null {
  const task = indexOf(state).task.get(taskId);
  if (!task) return null;
  let a: Assignment | null = task.assignments[0] ?? null;
  for (const x of task.assignments) {
    const w = state.waves.find((v) => v.number === x.wave);
    if (w && w.t0 <= t) a = x;
  }
  return a;
}

export type Tone = "ok" | "warn" | "bad" | "ink" | "sec";
export interface OrderStatus {
  label: string;
  tone: Tone;
  sub: string;
}
export function orderStatusAt(state: TwinState, orderId: string, t: number): OrderStatus {
  const o = state.orders.find((x) => x.id === orderId);
  if (!o) return { label: "—", tone: "ink", sub: "" };
  if (o.hold) return { label: "ON HOLD", tone: "warn", sub: o.hold_reason ?? "" };
  if (o.dispatched_at != null && o.dispatched_at <= t)
    return { label: o.on_time ? "DISPATCHED" : "DISPATCHED LATE", tone: o.on_time ? "ok" : "warn", sub: clockAt(state, o.dispatched_at) };
  const ix = indexOf(state);
  const sts = o.tasks.map((id) => taskStateAt(state, id, t)?.state || "OPEN");
  const late = t > o.deadline_s;
  if (sts.some((s) => s === "FAILED" || s === "BLOCKED" || s === "REPLANNED"))
    return { label: "RECOVERING", tone: "bad", sub: late ? "past deadline" : `due ${o.deadline}` };
  const verified = (k: string) =>
    o.tasks.filter((id) => ix.task.get(id)?.kind === k).every((id) => taskStateAt(state, id, t)?.state === "VERIFIED_COMPLETE");
  let s = "RECEIVED";
  if (sts.some((x) => x === "EXECUTING" || x === "REPORTED_COMPLETE" || x === "VERIFIED_COMPLETE")) s = "PICKING";
  if (verified("PICK")) s = "IN TRANSIT";
  if (verified("TRANSPORT")) s = "PACKING";
  if (verified("PACK")) s = "DISPATCHING";
  return { label: s, tone: late ? "bad" : "ink", sub: late ? "past deadline" : `due ${o.deadline}` };
}

// ---------------------------------------------------------------- KPIs
export interface KpisAt {
  ocr: number | null;
  ocrN: string;
  ful: number | null;
  lat: number | null;
  util: number | null;
  dist: number;
  cong: number;
  fails: number;
  viol: number;
  rew: number | null;
  rewW: string | null;
  topo: string | null;
}
export function kpisAt(state: TwinState, t: number): KpisAt {
  const ix = indexOf(state);
  const done = state.orders.filter((o) => o.dispatched_at != null && o.dispatched_at <= t);
  const lat = state.tasks
    .filter((x) => x.verified_at != null && x.verified_at <= t && x.latency_s != null)
    .map((x) => x.latency_s as number);
  let busy = 0,
    dist = 0,
    cong = 0;
  for (const [id, segs] of ix.segs) {
    const mobile = ix.mobile.includes(id);
    for (const s of segs) {
      if (s.t0 > t) break;
      const e = Math.min(s.t1, t);
      // busy = working on a task (driving back to the park is not work)
      if (mobile && s.task && (s.kind === "move" || s.kind === "work" || s.kind === "wait")) busy += e - s.t0;
      if (s.kind === "move") dist += (s.o1 - s.o0) * Math.min(1, (e - s.t0) / Math.max(s.t1 - s.t0, 1e-9));
      if (s.kind === "wait") cong += e - s.t0;
    }
  }
  const fails = state.tasks.reduce(
    (n, x) => n + x.states.filter((s) => s.state === "FAILED" && s.from === "EXECUTING" && s.t <= t).length,
    0,
  );
  const viol = ix.disputed.filter((c) => c.t <= t).length;
  const doneWaves = state.waves.filter((w) => w.reward && w.t1 <= t + 1e-6);
  const last = doneWaves[doneWaves.length - 1];
  const w = waveAt(state, t);
  return {
    ocr: state.orders.length ? done.length / state.orders.length : null,
    ocrN: `${done.length}/${state.orders.length} orders dispatched`,
    ful: done.length ? done.reduce((a, o) => a + (o.dispatched_at as number), 0) / done.length : null,
    lat: lat.length ? lat.reduce((a, b) => a + b, 0) / lat.length : null,
    util: t > 0 && ix.mobile.length ? busy / (ix.mobile.length * t) : null,
    dist,
    cong,
    fails,
    viol,
    rew: last?.reward ? last.reward.value : null,
    rewW: last ? last.mission_id : null,
    topo: w?.topology ?? null,
  };
}

// ---------------------------------------------------------------- congestion / events / claims
export interface AisleCongestion {
  aisle: string;
  entries: Congestion[];
  waiting: number;
  /** remaining wait seconds summed over waiting robots */
  remaining: number;
  label: string;
}
export function congestionAt(state: TwinState, t: number): AisleCongestion[] {
  const by = new Map<string, Congestion[]>();
  for (const c of state.congestion) if (c.t0 <= t && t < c.t1) by.set(c.aisle, [...(by.get(c.aisle) ?? []), c]);
  return [...by].map(([aisle, entries]) => {
    const remaining = Math.ceil(entries.reduce((a, c) => a + (c.t1 - t), 0));
    return { aisle, entries, waiting: entries.length, remaining, label: `${aisle} · ${entries.length} waiting · +${remaining} s` };
  });
}

export function visibleEvents(state: TwinState, t: number): TwinEvent[] {
  const ev = state.events;
  let lo = 0,
    hi = ev.length;
  while (lo < hi) {
    const m = (lo + hi) >> 1;
    if (ev[m].t <= t) lo = m + 1;
    else hi = m;
  }
  return ev.slice(0, lo);
}

export const STAGES: [key: string, label: string, cls: "" | "alert" | "sec"][] = [
  ["wh", "Warehouse", ""],
  ["orders", "Customer orders", ""],
  ["mission", "SAMG mission", ""],
  ["topo", "Topology", ""],
  ["alloc", "Allocation", ""],
  ["exec", "Robot execution", ""],
  ["disrupt", "Congestion / failure", "alert"],
  ["witness", "Witness", ""],
  ["acp", "Assurance (ACP)", "sec"],
  ["reward", "Secure reward", ""],
  ["learn", "Adaptive decision", ""],
];
export function stageOf(e: Pick<TwinEvent, "title">): string {
  const T = e.title;
  if (/^Order .* (received|on hold)/.test(T)) return "orders";
  if (/^Mission .* generated|^Replanning|^Context/.test(T)) return "mission";
  if (/selected|No eligible/.test(T)) return "topo";
  if (/allocation|reassigned/.test(T)) return "alloc";
  if (/^Congestion|FAILED$|failed$|blocked|Injection|Condition|Delay injected/.test(T)) return "disrupt";
  if (/^Witness/.test(T)) return "witness";
  if (/^SECURITY|^ACP/.test(T)) return "acp";
  if (/^Secure reward/.test(T)) return "reward";
  if (/update|no learning/.test(T)) return "learn";
  if (/dispatched/.test(T)) return "witness";
  return "exec";
}

export function claimsAt(state: TwinState, t: number): Claim[] {
  return state.claims.filter((c) => c.t <= t);
}

/** Robots that have failed by t. */
export function failedRobotsAt(state: TwinState, t: number): string[] {
  return state.robots.filter((r) => r.failed_at != null && r.failed_at <= t).map((r) => r.id);
}

// ---------------------------------------------------------------- comms view helpers
export interface HandoffFlight {
  wave: number;
  handoff: Handoff;
  /** 0..1 along handoff.path */
  progress: number;
}
/** Handoffs travelling the coordination graph at t (needs Phase 1-A `depart_s/arrive_s`; else empty). */
export function handoffsInFlight(state: TwinState, t: number): HandoffFlight[] {
  const out: HandoffFlight[] = [];
  for (const w of state.waves)
    for (const h of w.allocation?.handoffs ?? []) {
      if (h.depart_s == null || h.arrive_s == null) continue;
      if (h.depart_s <= t && t < h.arrive_s)
        out.push({ wave: w.number, handoff: h, progress: (t - h.depart_s) / Math.max(h.arrive_s - h.depart_s, 1e-9) });
    }
  return out;
}
export interface ClaimFlight {
  claim: Claim;
  /** 0..1 robot → ACP; verdict shown at 1 */
  progress: number;
}
/** Signed claims in transit robot → ACP during `window` seconds after they were made. */
export function claimsInFlight(state: TwinState, t: number, window = 1.5): ClaimFlight[] {
  const out: ClaimFlight[] = [];
  for (const c of state.claims) {
    if (c.t > t) break;
    if (t - c.t < window) out.push({ claim: c, progress: (t - c.t) / window });
  }
  return out;
}

// ---------------------------------------------------------------- transient 3D effects
export interface Effect {
  kind: "witness" | "rejected" | "failure";
  robot: string;
  t: number;
  age: number;
  event: TwinEvent;
}
/** Witness ticks, rejected claims and failures from events within the last `maxAge` seconds. */
export function effectsAt(state: TwinState, t: number, maxAge = 6): Effect[] {
  const out: Effect[] = [];
  for (const e of state.events) {
    if (e.t > t) break;
    const age = t - e.t;
    if (age > maxAge) continue;
    if (/^Witness verified/.test(e.title) && e.task) {
      const a = assignmentAt(state, e.task, t);
      if (a) out.push({ kind: "witness", robot: a.agent, t: e.t, age, event: e });
    } else if (e.level === "sec" && e.robot) out.push({ kind: "rejected", robot: e.robot, t: e.t, age, event: e });
    else if (/ FAILED$/.test(e.title) && e.robot) out.push({ kind: "failure", robot: e.robot, t: e.t, age, event: e });
  }
  return out;
}

// ---------------------------------------------------------------- demo phases (§6.8)
export interface Phase {
  n: number;
  t: number;
  seq: number;
  k: string;
  h: string;
  p: string;
  panel: string;
  hold?: number;
  final?: boolean;
}
export function buildPhases(state: TwinState, hasCompare = false): Phase[] {
  const S = state;
  const END = Math.max(S.end_s, 1);
  const first = (pred: (e: TwinEvent) => boolean, after = -1) => S.events.find((e) => e.t > after && pred(e));
  const P: Omit<Phase, "n">[] = [];
  const add = (e: TwinEvent | undefined, k: string, h: string, p: string, panel: string) => {
    if (e) P.push({ t: e.t, seq: e.seq, k, h, p, panel });
  };
  const w1 = S.waves[0];
  add(S.events[0], "Warehouse operation", `${S.orders.length} customer orders arrive`,
    S.orders.map((o) => `${o.id} ${o.priority} · ${o.items.length} items · due ${o.deadline}`).join("  ·  "), "orders");
  if (w1) {
    add(first((e) => /^Mission .* generated/.test(e.title)), "SAMG mission generation", `Orders become ${w1.tasks.length} SAMG tasks`,
      "Each order: PICK (per SKU, in parallel) → TRANSPORT → PACK → DISPATCH. Durations include A* travel estimates on this floor plan.", "mission");
    const sel = first((e) => / selected /.test(e.title));
    add(sel, "Topology selection", `${w1.policy} selects ${topoLabel(w1.topology)}`,
      (sel?.detail || "") + ". Scores and the context vector are shown in the topology panel.", "topo");
    add(first((e) => /allocation/.test(e.title)), "Task allocation", `${w1.allocation?.solver || ""} assigns every task`,
      "Coordination paths of the chosen graph price every cross-robot handoff (h0 + h1·hops).", "alloc");
  }
  add(first((e) => / started /.test(e.title)), "Robots execute", "Robots drive the routes SAMG's schedule implies",
    "Dashed lines are the A* routes; robots hold a narrow aisle exclusively while inside.", "map");
  const cg = first((e) => e.title.startsWith("Congestion"));
  add(cg, "Congestion", cg?.title || "", (cg?.detail || "") + ". The wait is measured and fed back into SAMG execution as a task delay.", "map");
  const fl = first((e) => / FAILED$/.test(e.title) && !!e.robot);
  add(fl, "Controlled failure", fl?.title || "", (fl?.detail || "") + ". The witness records the failure; dependent tasks are blocked.", "map");
  const sc = first((e) => e.level === "sec");
  add(sc, "Malicious agent report", sc ? `${sc.robot} signs a false claim` : "",
    "The signature is valid: the robot holds a real, registered key. The ACP checks the claim against independent witness evidence…", "sec");
  if (sc)
    P.push({ t: sc.t, seq: sc.seq + 0.5, k: "Assurance verdict", h: "Claim rejected · reward update protected",
      p: "Witness evidence contradicts the claim → DISPUTED and quarantined. The learner only ever receives the ACP-recomputed reward.", panel: "sec", hold: 6.5 });
  const rp = first((e) => e.title === "Replanning");
  add(rp, "System response", "SAMG replans what the witness did not verify", (rp?.detail || "") + ". A new topology decision and CP-SAT allocation follow.", "alloc");
  const rw = first((e) => /^Secure reward/.test(e.title));
  add(rw, "Secure reward & learning", rw?.title || "", (rw?.detail || "") + ". The guarded update uses only ADMITTED, ACP-recomputed rewards.", "topo");
  P.push({ t: END, seq: 1e9, k: "Final metrics", h: "Mission complete",
    p: hasCompare ? "Final KPIs below; the topology comparison runs the same orders under every policy."
      : "Final KPIs are below. Run the topology comparison for the fixed-baseline comparison.", panel: "kpis", final: true });
  P.sort((a, b) => a.t - b.t || a.seq - b.seq);
  return P.map((p, i) => ({ ...p, n: i + 1 }));
}

// ---------------------------------------------------------------- selection → robot (Phase 2-C)
/** Robot that a selection points at, at time t: the robot itself, a task's current assignee, a claim's signer. */
export function selectionRobot(state: TwinState | null, sel: { kind: string; id: string } | null, t: number): string | null {
  if (!state || !sel) return null;
  if (sel.kind === "robot") return sel.id;
  if (sel.kind === "task") return assignmentAt(state, sel.id, t)?.agent ?? null;
  if (sel.kind === "claim") return state.claims.find((c) => c.id === sel.id)?.agent ?? null;
  return null;
}
