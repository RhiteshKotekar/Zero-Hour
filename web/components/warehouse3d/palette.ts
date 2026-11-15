// 3D scene palette (light industrial, plan §6.2). Grid (x, y) maps to world (x, 0, y); 1 cell = 1 m.

export const C = {
  bg: "#eef1f5",
  floor: "#e9ecf0",
  floorOut: "#dde2e8",
  grid: "rgba(11,18,32,0.045)",
  ink: "#0b1220",
  muted: "#8a94a6",
  accent: "#2563eb",
  ok: "#059669",
  warn: "#c2700a",
  amber: "#f59e0b",
  bad: "#d92d2d",
  sec: "#7c3aed",
  samg: "#0e7490",
  lane: "#e8b13a",
  upright: "#7d8aa0",
  beam: "#b9c2cf",
  deck: "#dfe4ea",
  wall: "#c9d0da",
  wallTop: "#b7c0cc",
  robotBody: "#f4f6f9",
  robotDeck: "#2b3444",
  tote: "#f2a93b",
} as const;

export const ZONE_TINT: Record<string, string> = {
  RECEIVING: "#e6eefc",
  PARK: "#edf0f4",
  CONTROL: "#e9ebfb",
  CONSOLIDATION: "#fbf3e2",
  PACKING: "#f1ebfc",
  STAGING: "#e4f5ef",
  REPLEN: "#eef0f3",
  DISPATCH: "#fcefe4",
  STORAGE: "#eceff3",
};

/** muted tote colours for ordinary rack bins */
export const BIN_COLORS = ["#8ea4c2", "#a8b4c3", "#93b5ad", "#b9aa8c", "#9aa7bd", "#c0c7d1"];

/** shelf heights (m) */
export const SHELF_Y = [0.1, 0.68, 1.26, 1.84];
export const RACK_H = 2.25;

/** deterministic hash → [0,1) */
export function hash01(a: number, b: number, c = 0): number {
  const s = Math.sin(a * 127.1 + b * 311.7 + c * 74.7) * 43758.5453;
  return s - Math.floor(s);
}
