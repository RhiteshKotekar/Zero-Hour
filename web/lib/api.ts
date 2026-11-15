// REST client for samg.api (plan §5.2; exact shapes = §8 Phase 1-A log). No mock fallbacks: errors propagate.
import type { TwinState } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const BACKEND_HINT = "backend offline — start `.venv/bin/python -m samg.api`";

export interface SessionSpec {
  scenario: string;
  policy?: string;
  seed?: number;
  experience?: number;
  use_cpsat?: boolean;
}
export type ControlAction = "play" | "pause" | "step" | "reset" | "speed";
export interface InjectRequest {
  kind: string;
  robot?: string;
  aisle?: string;
  sku?: string;
  task?: string;
  delay_s?: number;
}
export interface InjectResult {
  accepted: boolean;
  at: number;
  kind?: string;
  target?: string | null;
  effect: string;
  wave?: number | null;
  source?: "operator" | "script";
}
export interface MetaScenario {
  id: string;
  label: string;
  seed: number | null;
  policy: string | null;
  order_source: string;
  script: Record<string, unknown>[];
}
export interface MetaInjection {
  kind: string;
  label: string;
  scope: "wave" | "environment";
  /** e.g. ["robot"], ["task?", "delay_s?"] — "?" = optional */
  needs: string[];
}
export interface Meta {
  scenarios: MetaScenario[];
  policies: { id: string; label: string }[];
  injections: MetaInjection[];
  robots: { id: string; role: string; label: string; physical: boolean }[];
  aisles: string[];
  skus: { sku: string; name: string; stock: number }[];
  layout: unknown;
  environment_injections: string[];
}
export interface RunInfo {
  id: string;
  saved_at?: string | number;
  scenario?: string;
  policy?: string;
  seed?: number;
  t?: number;
  end_s?: number;
  waves?: number;
  complete?: boolean;
  name?: string;
  [k: string]: unknown;
}
export interface ServerClock {
  t: number;
  playing: boolean;
  speed: number;
  revision: number;
}
export interface Stat {
  mean: number | null;
  std: number | null;
  n: number;
}
export interface CompareRow {
  policy: string;
  label: string;
  runs: Record<string, number | string | boolean | null>[];
  summary: Record<string, Stat>;
  topologies: Record<string, number>;
  infeasible: number;
}
export interface CompareResult {
  seeds: number[];
  policies: CompareRow[];
  metrics: string[];
  note: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function req<T>(path: string, body?: unknown, method?: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: method ?? (body === undefined ? "GET" : "POST"),
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(BACKEND_HINT, 0);
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not json */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export async function getHealth(): Promise<{ ok: boolean }> {
  return req("/api/health");
}
let metaCache: Promise<Meta> | null = null;
export async function getMeta(): Promise<Meta> {
  metaCache ??= req<Meta>("/api/meta").catch((e) => {
    metaCache = null;
    throw e;
  });
  return metaCache;
}
export async function createSession(spec: SessionSpec): Promise<{ session_id: string; state: TwinState }> {
  return req("/api/session", spec);
}
export async function getSession(): Promise<{ session_id: string | null; state: TwinState | null }> {
  return req("/api/session");
}
export async function control(action: ControlAction, value?: number): Promise<{ session_id: string; clock: ServerClock }> {
  return req("/api/session/control", value === undefined ? { action } : { action, value });
}
export async function inject(r: InjectRequest): Promise<InjectResult> {
  return req("/api/session/inject", r);
}
export async function compare(opts: { seeds?: number[]; use_cpsat?: boolean } = {}): Promise<CompareResult> {
  return req("/api/compare", opts);
}
export async function listRuns(): Promise<RunInfo[]> {
  return req("/api/runs");
}
export async function saveRun(name?: string): Promise<RunInfo> {
  return req("/api/runs/save", name ? { name } : {});
}
export async function loadRun(id: string): Promise<{ meta: RunInfo; spec: unknown; script: unknown; state: TwinState }> {
  return req(`/api/runs/${encodeURIComponent(id)}`);
}
