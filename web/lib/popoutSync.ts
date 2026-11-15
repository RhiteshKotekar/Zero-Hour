"use client";

import { useEffect } from "react";
import { useStore } from "./store";
import type { Selection } from "./types";

const CHANNEL_NAME = "zh-stage-popout-sync";
const STORAGE_KEY = "zh_popout_status";

export type PopoutMessage =
  | { type: "POPOUT_MOUNTED" }
  | { type: "POPOUT_UNMOUNTED" }
  | { type: "POPOUT_PING" }
  | { type: "POPOUT_PONG" }
  | { type: "CLOSE_POPOUT" }
  | { type: "CLOCK_SYNC"; t: number; playing: boolean; speed: number }
  | { type: "SELECT_SYNC"; selection: Selection | null };

let popoutWindowRef: Window | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;

export function getPopoutChannel(): BroadcastChannel | null {
  if (typeof window === "undefined" || !("BroadcastChannel" in window)) {
    return null;
  }
  return new BroadcastChannel(CHANNEL_NAME);
}

/** Open the 3D map in a standalone window/tab */
export function openPopoutWindow() {
  if (typeof window === "undefined") return;

  const currentReplay = new URLSearchParams(window.location.search).get("replay") ?? "/replays/judge_demo.json";
  const { clock, mode } = useStore.getState();
  const params = new URLSearchParams();
  if (mode === "live") {
    params.set("live", "1");
  } else {
    params.set("replay", currentReplay);
    params.set("t", String(Math.round(clock.t)));
    params.set("speed", String(clock.speed));
    if (!clock.playing) {
      params.set("paused", "1");
    }
  }

  const url = `/popout?${params.toString()}`;
  const win = window.open(url, "zh_simulation_popout");
  popoutWindowRef = win;

  useStore.getState().setPopoutActive(true);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ active: true, timestamp: Date.now() }));
  } catch {
    // ignore
  }

  // Poll for window closure
  if (pollTimer !== null) clearInterval(pollTimer);
  pollTimer = setInterval(() => {
    if (popoutWindowRef && popoutWindowRef.closed) {
      if (pollTimer !== null) clearInterval(pollTimer);
      pollTimer = null;
      popoutWindowRef = null;
      useStore.getState().setPopoutActive(false);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ active: false, timestamp: Date.now() }));
      } catch {
        // ignore
      }
    }
  }, 400);

  const channel = getPopoutChannel();
  channel?.postMessage({ type: "POPOUT_MOUNTED" });
}

/** Close the popout window and bring simulation back to dashboard */
export function closePopoutWindow() {
  const channel = getPopoutChannel();
  channel?.postMessage({ type: "CLOSE_POPOUT" });

  if (popoutWindowRef && !popoutWindowRef.closed) {
    try {
      popoutWindowRef.close();
    } catch {
      // ignore
    }
  }
  popoutWindowRef = null;

  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  useStore.getState().setPopoutActive(false);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ active: false, timestamp: Date.now() }));
  } catch {
    // ignore
  }
}

/** Broadcast clock updates to other tabs */
export function broadcastClockSync(t: number, playing: boolean, speed: number) {
  const channel = getPopoutChannel();
  channel?.postMessage({ type: "CLOCK_SYNC", t, playing, speed });
}

/** Broadcast selection updates to other tabs */
export function broadcastSelectSync(selection: Selection | null) {
  const channel = getPopoutChannel();
  channel?.postMessage({ type: "SELECT_SYNC", selection });
}

/** Hook for the main Dashboard tab to track popout status and listen to sync */
export function useDashboardPopoutTracker() {
  useEffect(() => {
    const channel = getPopoutChannel();

    // Check if popout is already open when dashboard mounts
    channel?.postMessage({ type: "POPOUT_PING" });

    const handleMessage = (e: MessageEvent<PopoutMessage>) => {
      if (!e.data || !e.data.type) return;
      switch (e.data.type) {
        case "POPOUT_MOUNTED":
        case "POPOUT_PONG":
          useStore.getState().setPopoutActive(true);
          break;
        case "POPOUT_UNMOUNTED":
          useStore.getState().setPopoutActive(false);
          popoutWindowRef = null;
          break;
        case "CLOCK_SYNC": {
          const s = useStore.getState();
          if (Math.abs(s.clock.t - e.data.t) > 1.5) {
            s.seek(e.data.t);
          }
          if (s.clock.playing !== e.data.playing) {
            if (e.data.playing) s.play();
            else s.pause();
          }
          if (s.clock.speed !== e.data.speed) {
            s.setSpeed(e.data.speed);
          }
          break;
        }
        case "SELECT_SYNC":
          useStore.getState().select(e.data.selection);
          break;
      }
    };

    // Storage fallback for cross-tab communication
    const handleStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue) {
        try {
          const data = JSON.parse(e.newValue);
          useStore.getState().setPopoutActive(Boolean(data.active));
        } catch {
          // ignore
        }
      }
    };

    channel?.addEventListener("message", handleMessage);
    window.addEventListener("storage", handleStorage);

    return () => {
      channel?.removeEventListener("message", handleMessage);
      channel?.close();
      window.removeEventListener("storage", handleStorage);
    };
  }, []);
}
