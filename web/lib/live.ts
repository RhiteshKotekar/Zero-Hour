"use client";
// Live wiring (Phase 2-D): WS stream + REST commands → the main store (mode "live"), plus the auto-demo driver.
// The browser never decides anything: it shows the backend's state snapshots and follows its clock.
//
// Attach model: the WS always tracks the server's latest session (`useLive.server`), but the main store only
// follows it while `attached` (after Start/Attach/Auto demo). Switching to a replay detaches.

import { useEffect } from "react";
import { create } from "zustand";
import * as api from "./api";
import { buildPhases, type Phase } from "./derive";
import { connectWs, type WsStatus } from "./ws";
import { setLiveController, useStore } from "./store";
import type { TwinState } from "./types";

export const DEFAULT_REPLAY = "/replays/judge_demo.json";
export const DEFAULT_REPLAY_SOURCE = "REPLAY · recorded SAMG run";

export type Backend = "unknown" | "online" | "offline";

interface LiveStore {
  status: WsStatus | "idle";
  backend: Backend;
  attached: boolean;
  /** latest session known on the server (from WS), attached or not */
  server: { session_id: string; state: TwinState; revision: number } | null;
  /** creating a session (first adaptive one ≈12 s) */
  starting: { since: number; label: string } | null;
  error: string | null;
}

export const useLive = create<LiveStore>()(() => ({
  status: "idle",
  backend: "unknown",
  attached: false,
  server: null,
  starting: null,
  error: null,
}));

export interface LiveConnection {
  status: "idle" | "connecting" | "open" | "closed";
  backend: Backend;
  attached: boolean;
  /** a session exists on the server */
  hasServerSession: boolean;
}

const liveSource = (s: TwinState) => `LIVE · ${s.spec.label ?? s.spec.scenario}`;

function adopt(state: TwinState, revision?: number) {
  const st = useStore.getState();
  const prevSession = st.mode === "live" ? st.state?.live?.session_id : undefined;
  st.setState(state, {
    revision: revision ?? state.live?.revision,
    mode: "live",
    source: liveSource(state),
    resetClock: prevSession !== state.live?.session_id,
  });
  if (state.live && prevSession !== state.live.session_id)
    st.applyServerClock({ t: state.live.t, playing: state.live.playing, speed: state.live.speed });
}

// control calls are serialised so play/pause/speed reach the server in the order they were issued
let controlChain: Promise<void> = Promise.resolve();
function sendControl(action: api.ControlAction, value?: number): Promise<void> {
  controlChain = controlChain.then(() => doControl(action, value));
  return controlChain;
}
async function doControl(action: api.ControlAction, value?: number) {
  try {
    const r = await api.control(action, value);
    if (action === "reset") {
      const s = await api.getSession();
      if (s.state) adopt(s.state);
    }
    if (useLive.getState().attached) useStore.getState().applyServerClock(r.clock);
  } catch (e) {
    useStore.getState().pushToast("bad", `control ${action}: ${(e as Error).message}`);
  }
}

// while attached, store clock actions (play/pause/speed/step/reset) go to POST /api/session/control
useLive.subscribe((s, prev) => {
  if (s.attached !== prev.attached) setLiveController(s.attached ? (a, v) => void sendControl(a, v) : null);
});

/** Mount once (page shell). Connects the WS, tracks backend status, routes clock actions while attached. */
export function useLiveConnection(enabled = true): LiveConnection {
  const status = useLive((s) => s.status);
  const backend = useLive((s) => s.backend);
  const attached = useLive((s) => s.attached);
  const hasServerSession = useLive((s) => s.server != null);

  useEffect(() => {
    if (!enabled) return;
    const conn = connectWs({
      onStatus: (st) =>
        useLive.setState((s) => ({
          status: st,
          backend: st === "open" ? "online" : st === "closed" ? "offline" : s.backend,
        })),
      onMessage: (msg) => {
        const live = useLive.getState();
        if (msg.type === "hello" || msg.type === "state") {
          if (!msg.state) return useLive.setState({ server: null });
          const revision = msg.type === "state" ? msg.revision : (msg.clock.revision ?? msg.state.live?.revision ?? 0);
          useLive.setState({ server: { session_id: msg.state.live?.session_id ?? "", state: msg.state, revision } });
          // nothing loaded yet (e.g. `/?live=1`): follow the server session right away
          if (!live.attached && !useStore.getState().state) useLive.setState({ attached: true });
          if (useLive.getState().attached) {
            adopt(msg.state, revision);
            if (msg.type === "hello") useStore.getState().applyServerClock(msg.clock);
          }
        } else if (msg.type === "clock") {
          if (live.attached && useStore.getState().mode === "live") useStore.getState().applyServerClock(msg);
        } else if (msg.type === "notice") {
          if (live.attached) useStore.getState().pushToast(msg.level, msg.text);
        }
      },
    });
    return () => conn.close();
  }, [enabled]);

  return { status, backend, attached, hasServerSession };
}

// ---------------------------------------------------------------- commands

/** Create a live session on the server and follow it (paused at t=0). */
export async function startSession(spec: api.SessionSpec): Promise<TwinState> {
  useLive.setState({ starting: { since: Date.now(), label: spec.scenario }, error: null });
  try {
    const r = await api.createSession(spec);
    useLive.setState({ attached: true, backend: "online", server: { session_id: r.session_id, state: r.state, revision: r.state.live?.revision ?? 0 } });
    adopt(r.state);
    useStore.getState().applyServerClock({ t: r.state.live?.t ?? 0, playing: false, speed: r.state.live?.speed ?? 1 });
    return r.state;
  } catch (e) {
    useLive.setState({ error: (e as Error).message, backend: (e as api.ApiError).status === 0 ? "offline" : "online" });
    throw e;
  } finally {
    useLive.setState({ starting: null });
  }
}

/** Follow the session already running on the server. */
export async function attachLive(): Promise<void> {
  const s = await api.getSession();
  if (!s.state) throw new Error("no live session on the server");
  useLive.setState({ attached: true });
  adopt(s.state);
  const l = s.state.live;
  if (l) useStore.getState().applyServerClock({ t: l.t, playing: l.playing, speed: l.speed });
}

/** Stop following the live session and load a replay into the store (browser-owned clock). */
export async function loadReplayState(state: TwinState, source: string): Promise<void> {
  useLive.setState({ attached: false });
  useDemo.getState().stop();
  useStore.getState().setState(state, { mode: "replay", source, resetClock: true });
}
export async function switchToReplay(url = DEFAULT_REPLAY, source = DEFAULT_REPLAY_SOURCE): Promise<void> {
  useLive.setState({ attached: false });
  useDemo.getState().stop();
  await useStore.getState().loadReplay(url, source);
}
export async function loadSavedRun(id: string): Promise<void> {
  const r = await api.loadRun(id);
  await loadReplayState(r.state, `REPLAY · saved run ${r.meta.name ?? r.meta.id}`);
}

/**
 * Page-shell bootstrap: load the bundled recorded run only if nothing is loaded yet (so `/replays` → `/` keeps
 * the chosen run). `?run=<id>` loads a saved backend run instead.
 */
export async function ensureInitialState(): Promise<void> {
  if (useStore.getState().state) return;
  const run = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("run") : null;
  if (run) {
    try {
      return await loadSavedRun(run);
    } catch (e) {
      useStore.getState().pushToast("bad", `run ${run}: ${(e as Error).message}`);
    }
  }
  await switchToReplay();
}

// ---------------------------------------------------------------- auto demo (§6.8)

const DEMO_SPEED = 3;
const DEFAULT_HOLD_S = 3.5;

interface DemoStore {
  active: boolean;
  kind: "live" | "replay" | null;
  banner: Phase | null;
  total: number;
  holdingUntil: number | null;
  shown: string[];
  start: (prefer?: "live" | "replay") => Promise<void>;
  stop: () => void;
  dismiss: () => void;
}

const phaseKey = (p: Phase) => `${p.k}|${p.seq}`;

export const useDemo = create<DemoStore>()((set, get) => ({
  active: false,
  kind: null,
  banner: null,
  total: 0,
  holdingUntil: null,
  shown: [],
  start: async (prefer) => {
    get().stop();
    let kind: "live" | "replay" = prefer ?? (useLive.getState().backend === "offline" ? "replay" : "live");
    if (kind === "live") {
      try {
        await startSession({ scenario: "judge_demo" });
      } catch (e) {
        useStore.getState().pushToast("warn", `Live demo unavailable (${(e as Error).message}) — playing the recorded run`);
        kind = "replay";
      }
    }
    if (kind === "replay") {
      const st = useStore.getState();
      if (st.mode !== "replay" || st.state?.spec.scenario !== "judge_demo") await switchToReplay();
      useStore.getState().pause();
      useStore.getState().seek(0);
    }
    set({ active: true, kind, banner: null, shown: [], holdingUntil: null });
    useStore.getState().setSpeed(DEMO_SPEED);
    useStore.getState().play();
  },
  stop: () => set({ active: false, kind: null, holdingUntil: null }),
  dismiss: () => set({ banner: null }),
}));

let phaseCache: { state: TwinState; phases: Phase[] } | null = null;
function phasesOf(state: TwinState): Phase[] {
  if (phaseCache?.state !== state) phaseCache = { state, phases: buildPhases(state, false) };
  return phaseCache.phases;
}

/** Drives demo banners + holds (mounted by DemoBanner). Phases are anchored to real events of the state. */
export function useDemoDriver(): void {
  useEffect(() => {
    const id = window.setInterval(() => {
      const d = useDemo.getState();
      if (!d.active) return;
      const st = useStore.getState();
      const state = st.state;
      if (!state) return;
      const now = Date.now();
      if (d.holdingUntil != null) {
        if (now >= d.holdingUntil) {
          useDemo.setState({ holdingUntil: null });
          if (!d.banner?.final) st.play();
        }
        return;
      }
      const live = st.mode === "live";
      // in live mode the "final" phase sits at the preview end; only show it once the session is complete
      const phases = phasesOf(state).filter((p) => !p.final || !live || state.live?.complete);
      const t = st.localT();
      const shown = new Set(d.shown);
      const due = phases.filter((p) => !shown.has(phaseKey(p)) && p.t <= t + 1e-6);
      if (!due.length) {
        if (st.mode === "replay" && !st.clock.playing && t >= st.endT() - 1e-3) useDemo.setState({ active: false });
        return;
      }
      // skip phases far in the past (e.g. after a seek): show the most recent stale one only
      const fresh = due.filter((p) => t - p.t < 20);
      const p = fresh[0] ?? due[due.length - 1];
      const mark = due.filter((q) => q === p || (!fresh.includes(q) && q.t <= p.t)).map(phaseKey);
      const holdS = p.final ? 0 : (p.hold ?? DEFAULT_HOLD_S);
      useDemo.setState({ banner: p, total: phases.length, shown: [...d.shown, ...mark], holdingUntil: holdS ? now + holdS * 1000 : null, active: !p.final });
      if (holdS) st.pause();
    }, 120);
    return () => window.clearInterval(id);
  }, []);
}
