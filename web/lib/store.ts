"use client";
// Global UI store (plan §6.3). The store never computes SAMG decisions; it holds the latest state snapshot,
// the simulation clock and UI selection/toggles.
//
// Clock model: `clock.serverT` is the sim time at wall time `clock.receivedAt` (performance.now() ms).
// `localT()` extrapolates from there when playing — this is what the 3D view reads every frame.
// `clock.t` is a committed copy refreshed at ~10 Hz by `useClockDriver()` for React panels.
// Replay: the browser owns the clock. Live (Phase 2-D): call `applyServerClock()` on each WS `clock` message.

import { useEffect } from "react";
import { create } from "zustand";
import type { Selection, TwinState } from "./types";

export type Mode = "live" | "replay";
export type View = "ops" | "comms";
export type DashboardMode = "demo" | "detailed";
export type CameraCommandKind = "top" | "iso" | "reset" | "follow" | "focusSelection" | "focusCongestion" | "focusFailure";

export interface Clock {
  /** committed sim time (≈10 Hz), for React panels */
  t: number;
  playing: boolean;
  speed: number;
  /** sim time anchor */
  serverT: number;
  /** performance.now() at anchor */
  receivedAt: number;
}

export interface Toggles {
  routes: boolean;
  coord: boolean;
  labels: boolean;
  congestion: boolean;
  effects: boolean;
}

/** Phase 2-D: server notices / UI messages (rendered by the page shell). */
export interface Toast {
  id: number;
  level: "ok" | "warn" | "bad" | "info" | (string & {});
  text: string;
  at: number;
}
/** Phase 2-D: in live mode clock actions go to the backend (`POST /api/session/control`) via this hook. */
export type LiveControlAction = "play" | "pause" | "step" | "reset" | "speed";
let liveController: ((action: LiveControlAction, value?: number) => void) | null = null;
export const setLiveController = (fn: typeof liveController): void => {
  liveController = fn;
};

export interface CameraCommand {
  kind: CameraCommandKind;
  nonce: number;
}

export interface StoreState {
  state: TwinState | null;
  revision: number;
  mode: Mode;
  /** source label, e.g. "REPLAY · recorded SAMG run" */
  source: string;
  clock: Clock;
  selection: Selection | null;
  hover: Selection | null;
  toggles: Toggles;
  view: View;
  /** robot id the camera follows (null = free camera) */
  follow: string | null;
  camera: CameraCommand | null;
  toasts: Toast[];
  isPopoutActive: boolean;
  dashboardMode: DashboardMode;

  // ---- derived clock
  localT: () => number;
  endT: () => number;

  // ---- data
  setState: (state: TwinState, opts?: { revision?: number; mode?: Mode; source?: string; resetClock?: boolean }) => void;
  loadReplay: (url: string, source?: string) => Promise<void>;

  // ---- clock
  play: () => void;
  pause: () => void;
  togglePlay: () => void;
  setSpeed: (speed: number) => void;
  seek: (t: number) => void;
  /** advance by dt sim-seconds (live: server `step`) */
  step: (dt?: number) => void;
  /** replay: back to t=0, paused; live: server `reset` (new session, same params) */
  reset: () => void;
  /** live mode: follow the server clock (WS `clock` message) */
  applyServerClock: (msg: { t: number; playing: boolean; speed: number }) => void;
  /** commit localT() into clock.t (called by useClockDriver) */
  commit: () => void;

  // ---- UI
  select: (sel: Selection | null) => void;
  setHover: (sel: Selection | null) => void;
  toggle: (key: keyof Toggles) => void;
  setView: (view: View) => void;
  setFollow: (robot: string | null) => void;
  cameraCommand: (kind: CameraCommandKind) => void;
  pushToast: (level: Toast["level"], text: string) => void;
  dismissToast: (id: number) => void;
  setPopoutActive: (active: boolean) => void;
  setDashboardMode: (mode: DashboardMode) => void;
}

const now = () => (typeof performance !== "undefined" ? performance.now() : 0);

export const useStore = create<StoreState>()((set, get) => ({
  state: null,
  revision: 0,
  mode: "replay",
  source: "",
  clock: { t: 0, playing: false, speed: 1, serverT: 0, receivedAt: 0 },
  selection: null,
  hover: null,
  toggles: { routes: true, coord: false, labels: true, congestion: true, effects: true },
  view: "ops",
  follow: null,
  camera: null,
  toasts: [],
  isPopoutActive: false,
  dashboardMode: (typeof window !== "undefined" && (new URLSearchParams(window.location.search).get("mode") as DashboardMode)) ||
    (typeof window !== "undefined" && (localStorage.getItem("zh_dashboard_mode") as DashboardMode)) ||
    "demo",

  localT: () => {
    const { clock, mode, state } = get();
    if (!clock.playing) return clock.t;
    const rate = mode === "live" ? (state?.live?.rate ?? 1) : 1;
    const t = clock.serverT + ((now() - clock.receivedAt) / 1000) * clock.speed * rate;
    return mode === "replay" ? Math.min(t, get().endT()) : t;
  },
  endT: () => Math.max(get().state?.end_s ?? 0, 0),

  setState: (state, opts = {}) =>
    set((s) => {
      const mode = opts.mode ?? (state.live?.mode === "live" ? "live" : s.mode);
      const next: Partial<StoreState> = {
        state,
        revision: opts.revision ?? state.live?.revision ?? s.revision + 1,
        mode,
        source: opts.source ?? s.source,
      };
      if (opts.resetClock) next.clock = { t: 0, playing: false, speed: s.clock.speed, serverT: 0, receivedAt: now() };
      return next;
    }),

  loadReplay: async (url, source = "REPLAY · recorded SAMG run") => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`replay ${url}: HTTP ${res.status}`);
    const j = await res.json();
    // also accepts a saved backend run (`GET /api/runs/{id}` → {meta, spec, script, state})
    const state = (j && !j.layout && j.state ? j.state : j) as TwinState;
    get().setState(state, { mode: "replay", source, resetClock: true });
  },

  play: () => {
    if (get().mode === "live" && liveController) {
      liveController("play");
      return set((s) => ({ clock: { ...s.clock, playing: true, serverT: s.clock.t, receivedAt: now() } }));
    }
    set((s) => {
      const t = s.mode === "replay" && s.clock.t >= get().endT() - 1e-3 ? 0 : s.clock.t;
      return { clock: { ...s.clock, t, playing: true, serverT: t, receivedAt: now() } };
    });
  },
  pause: () => {
    if (get().mode === "live" && liveController) liveController("pause");
    set((s) => ({ clock: { ...s.clock, t: get().localT(), playing: false } }));
  },
  togglePlay: () => (get().clock.playing ? get().pause() : get().play()),
  setSpeed: (speed) => {
    if (get().mode === "live" && liveController) liveController("speed", speed);
    set((s) => {
      const t = get().localT();
      return { clock: { ...s.clock, t, serverT: t, receivedAt: now(), speed } };
    });
  },
  seek: (t) => {
    if (get().mode === "live") return; // the server owns the live clock
    set((s) => {
      const c = Math.max(0, s.mode === "replay" ? Math.min(t, get().endT()) : t);
      return { clock: { ...s.clock, t: c, serverT: c, receivedAt: now() } };
    });
  },
  step: (dt = 5) => {
    if (get().mode === "live" && liveController) return liveController("step", dt);
    get().pause();
    get().seek(get().clock.t + dt);
  },
  reset: () => {
    if (get().mode === "live" && liveController) return liveController("reset");
    get().pause();
    get().seek(0);
  },
  applyServerClock: ({ t, playing, speed }) =>
    set(() => ({ clock: { t, playing, speed, serverT: t, receivedAt: now() } })),
  commit: () =>
    set((s) => {
      const t = get().localT();
      if (s.mode === "replay" && s.clock.playing && t >= get().endT() - 1e-6)
        return { clock: { ...s.clock, t: get().endT(), playing: false } };
      return t === s.clock.t ? {} : { clock: { ...s.clock, t } };
    }),

  select: (selection) => set({ selection }),
  setHover: (hover) => set({ hover }),
  toggle: (key) => set((s) => ({ toggles: { ...s.toggles, [key]: !s.toggles[key] } })),
  setView: (view) => set({ view }),
  setFollow: (follow) => set({ follow }),
  cameraCommand: (kind) => set((s) => ({ camera: { kind, nonce: (s.camera?.nonce ?? 0) + 1 } })),
  pushToast: (level, text) =>
    set((s) => ({ toasts: [...s.toasts.slice(-5), { id: (s.toasts.at(-1)?.id ?? 0) + 1, level, text, at: Date.now() }] })),
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
  setPopoutActive: (isPopoutActive) => set({ isPopoutActive }),
  setDashboardMode: (dashboardMode) => {
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("zh_dashboard_mode", dashboardMode);
      } catch {
        // ignore
      }
    }
    set({ dashboardMode });
  },
}));

/** Mount once (page shell): commits the extrapolated clock into `clock.t` at `hz` and stops replays at the end. */
export function useClockDriver(hz = 10): void {
  useEffect(() => {
    const id = window.setInterval(() => {
      const s = useStore.getState();
      if (s.clock.playing) s.commit();
    }, 1000 / hz);
    return () => window.clearInterval(id);
  }, [hz]);
}

/** Committed sim time for React components (re-renders at the driver rate). */
export const useSimT = (): number => useStore((s) => s.clock.t);
/** Non-reactive accessor for per-frame code (useFrame). */
export const getLocalT = (): number => useStore.getState().localT();
