// Types for the `twin-state` contract (docs/CONTROL_CENTER_PLAN.md §4).
// Produced by samg.twin.build_state(); fields added in Phase 1-A are optional.

export type Cell = [number, number];
/** Inclusive grid rectangle [x0, y0, x1, y1]. */
export type Rect = [number, number, number, number];

export type Role = "control" | "picking" | "transport" | "packing" | "dispatch";
export type SegmentKind = "move" | "wait" | "work" | "idle" | "failed";
export type RobotStatus =
  | "IDLE"
  | "MOVING"
  | "TRANSPORTING"
  | "PICKING"
  | "PACKING"
  | "WAITING"
  | "FAILED"
  | "COMPLETED"
  | (string & {});
export type TaskStateName =
  | "OPEN"
  | "ASSIGNED"
  | "EXECUTING"
  | "REPORTED_COMPLETE"
  | "VERIFIED_COMPLETE"
  | "FAILED"
  | "BLOCKED"
  | "REPLANNED"
  | (string & {});
export type EventLevel = "info" | "samg" | "move" | "warn" | "ok" | "bad" | "sec";
export type Topology = "HIERARCHICAL" | "DISTRIBUTED" | "FUNCTIONAL_CELL" | "DIRECT" | (string & {});

export interface Spec {
  scenario: string;
  label?: string;
  seed: number;
  policy: string;
  policy_label: string;
  policy_kind: string;
  experience?: number;
  injections: string[];
  use_cpsat?: boolean;
  order_source?: "config" | "generated";
}

export interface Zone {
  id: string;
  label: string;
  rect: Rect;
}
export interface Rack {
  id: string;
  rect: Rect;
}
export interface Aisle {
  id: string;
  rect: Rect;
  blocked: boolean;
}
export interface Station {
  id: string;
  kind: "pack" | "dock" | "charger" | (string & {});
  label: string;
  rect: Rect;
  access: Cell | null;
  outbound: Cell | null;
}
export interface Consolidation {
  id: string;
  cell: Cell;
}
export interface Layout {
  width: number;
  height: number;
  zones: Zone[];
  racks: Rack[];
  aisles: Aisle[];
  stations: Station[];
  walls: Rect[];
  consolidation: Consolidation[];
}

export interface InventoryItem {
  sku: string;
  name: string;
  cell: Cell;
  pick_face: Cell;
  aisle: string;
  rack: string;
  stock: number;
}

export interface Segment {
  t0: number;
  /** null = forever */
  t1: number | null;
  kind: SegmentKind;
  status: RobotStatus;
  cell: Cell;
  path?: Cell[];
  task?: string;
  aisle?: string;
  blockers?: string[];
  note?: string;
  wave?: number;
  b0: number;
  b1: number;
  o0: number;
  o1: number;
}

export interface Robot {
  id: string;
  role: Role | (string & {});
  label: string;
  capabilities: string[];
  coordinator: boolean;
  lead: boolean;
  physical: boolean;
  mobile: boolean;
  home: Cell;
  station: string | null;
  speed: number;
  battery0: number;
  segments: Segment[];
  failed_at: number | null;
}

export interface Order {
  id: string;
  priority: "CRITICAL" | "HIGH" | "NORMAL" | "LOW" | (string & {});
  deadline_s: number;
  deadline: string;
  items: string[];
  tasks: string[];
  hold: boolean;
  hold_reason: string | null;
  dispatched_at: number | null;
  on_time: boolean | null;
  consolidation: string | null;
  dock: string | null;
  arrival?: string;
  arrival_s?: number;
}

export interface TaskState {
  t: number;
  state: TaskStateName;
  from?: TaskStateName;
  wave?: number;
  agent?: string;
}
export interface Assignment {
  wave: number;
  agent: string;
  plan_start: number;
  plan_end: number;
  reassigned_from: string | null;
}
export interface Task {
  id: string;
  order: string;
  kind: "PICK" | "TRANSPORT" | "PACK" | "DISPATCH" | (string & {});
  label: string;
  sku?: string | null;
  priority: string;
  capability: string;
  deps: string[];
  estimate_s: number;
  states: TaskState[];
  assignments: Assignment[];
  window: number[];
  latency_s: number | null;
  verified_at: number | null;
  zone?: string | null;
}

export interface ContextFeature {
  name: string;
  value: number;
}
export interface Arm {
  topology: Topology;
  offered: boolean;
  selected: boolean;
  /** null when no learning policy scored this wave (fixed baseline or operator-forced) */
  mean: number | null;
  bonus: number | null;
  score: number | null;
  reasons: string[];
}
export interface CoordGraph {
  topology: Topology;
  coordinators: string[];
  cells: Record<string, string[]>;
  cell_coordinators: Record<string, string>;
  links: [string, string][];
}
export interface Handoff {
  from_task: string;
  to_task: string;
  path: string[];
  hops: number;
  cost: number;
  /** Phase 1-A addition (null if the prerequisite never completed) */
  depart_s?: number | null;
  arrive_s?: number | null;
}
export interface Allocation {
  solver: string;
  status: string;
  fallback: boolean;
  objective: { makespan_s: number; handoff_cost: number; weighted_total: number };
  handoffs: Handoff[];
}
export interface RewardTerm {
  component: number;
  weight: number;
  contribution: number;
}
export interface Wave {
  number: number;
  mission_id: string;
  t0: number;
  t1: number;
  tasks: string[];
  excluded: string[];
  failing: string[];
  physical_passes?: number;
  delays_s: Record<string, number>;
  injections: Record<string, unknown>[];
  policy: string;
  topology: Topology | null;
  warmup: boolean;
  context: ContextFeature[];
  arms: Arm[];
  graph: CoordGraph | null;
  allocation: Allocation | null;
  episode: { status: string; reasons: string[] } | null;
  reward: { value: number; terms: Record<string, RewardTerm> } | null;
  ground_truth_reward?: number | null;
  claimed_reward?: number | null;
  metrics?: Record<string, number>;
  learning?: { applied: boolean; topology: string | null; reward: number | null; source: string | null; rejection: string | null } | null;
  /** Phase 1-A addition (live only; replay = committed) */
  status?: "planned" | "preview" | "committed";
}

export interface Claim {
  t: number;
  wave: number;
  id: string;
  agent: string;
  type: "TASK_STARTED" | "TASK_COMPLETED" | "REWARD_CLAIM" | (string & {});
  task: string | null;
  auth: string;
  auth_reasons: string[];
  evidence: "CORROBORATED" | "DISPUTED" | (string & {}) | null;
  reasons: string[];
  claimed_reward: number | null;
  witness_state: string | null;
  false_claim: boolean;
}

export interface Congestion {
  robot: string;
  task: string;
  aisle: string;
  cell: Cell;
  t0: number;
  t1: number;
  blockers: string[];
  wave: number;
}

export interface TwinEvent {
  t: number;
  seq: number;
  level: EventLevel;
  title: string;
  detail?: string;
  order?: string;
  robot?: string;
  task?: string;
  aisle?: string;
  wave?: number;
  claim?: string;
}

export interface Kpis {
  orders_total: number;
  orders_dispatched: number;
  order_completion_rate: number;
  on_time: number;
  avg_fulfilment_s: number | null;
  avg_task_latency_s: number | null;
  robot_utilization: number;
  travel_m: number;
  congestion_s: number;
  congestion_events: number;
  task_failures: number;
  unverified_tasks: number;
  security_violations: number;
  reward_last: number | null;
  rewards: number[];
  makespan_s: number;
  topologies: string[];
  replans: number;
}

/** Phase 1-A addition */
export interface WitnessEvent {
  t: number;
  task: string;
  /** task states (the comms edge is witness → ACP) */
  from: string;
  to: string;
  witness?: string;
  wave: number;
}
export interface Injection {
  t: number;
  kind: string;
  target?: string | null;
  effect?: string;
  /** null for environment / idle injections */
  wave?: number | null;
  source?: "operator" | "script";
}
export interface ScriptStep {
  at: number;
  kind: string;
  robot?: string;
  aisle?: string;
  sku?: string;
  task?: string;
  delay_s?: number;
  fired?: boolean;
}
export interface LiveInfo {
  session_id: string;
  mode: "live" | "replay";
  revision: number;
  t: number;
  playing: boolean;
  speed: number;
  rate: number;
  complete?: boolean;
  script: ScriptStep[];
  injections: Injection[];
  /** order ids arrived but not yet in a wave */
  pending_orders: string[];
  planning: "idle" | "planning" | "running";
  /** operator topology override in force for newly planned waves (null = the policy decides) */
  forced_topology?: Topology | null;
  forced_since?: number | null;
}

export interface TwinState {
  version: string;
  config_version: string;
  start_clock: string;
  spec: Spec;
  end_s: number;
  layout: Layout;
  inventory: InventoryItem[];
  robots: Robot[];
  orders: Order[];
  tasks: Task[];
  waves: Wave[];
  claims: Claim[];
  congestion: Congestion[];
  events: TwinEvent[];
  kpis: Kpis;
  witness_events?: WitnessEvent[];
  live?: LiveInfo;
}

export type SelectionKind = "robot" | "task" | "order" | "rack" | "aisle" | "claim" | "wave";
export interface Selection {
  kind: SelectionKind;
  id: string;
}
