// Reconnecting WebSocket client for samg.api `/ws` (server → client only; §8 Phase 1-A log).
import { API_URL } from "./api";
import type { TwinState } from "./types";

export type WsMessage =
  | { type: "hello"; state: TwinState | null; clock: { t: number; playing: boolean; speed: number; revision?: number } }
  | { type: "state"; revision: number; state: TwinState }
  | { type: "clock"; t: number; playing: boolean; speed: number; revision: number }
  | { type: "notice"; level: "ok" | "warn" | "bad" | (string & {}); text: string };

export type WsStatus = "connecting" | "open" | "closed";

export interface WsHandlers {
  onMessage: (msg: WsMessage) => void;
  onStatus?: (status: WsStatus) => void;
}

export interface WsConnection {
  close: () => void;
}

export const WS_URL = `${API_URL.replace(/^http/, "ws")}/ws`;

/** Connects and keeps reconnecting (backoff 0.5 s → 5 s) until `close()`. */
export function connectWs(handlers: WsHandlers, url: string = WS_URL): WsConnection {
  let ws: WebSocket | null = null;
  let closed = false;
  let delay = 500;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const open = () => {
    if (closed) return;
    handlers.onStatus?.("connecting");
    try {
      ws = new WebSocket(url);
    } catch {
      schedule();
      return;
    }
    ws.onopen = () => {
      delay = 500;
      handlers.onStatus?.("open");
    };
    ws.onmessage = (ev) => {
      try {
        handlers.onMessage(JSON.parse(ev.data as string) as WsMessage);
      } catch (e) {
        console.error("ws message", e);
      }
    };
    ws.onclose = () => {
      ws = null;
      if (closed) return;
      handlers.onStatus?.("closed");
      schedule();
    };
    ws.onerror = () => ws?.close();
  };
  const schedule = () => {
    if (closed) return;
    timer = setTimeout(open, delay);
    delay = Math.min(delay * 2, 5000);
  };
  open();
  return {
    close: () => {
      closed = true;
      if (timer) clearTimeout(timer);
      ws?.close();
      handlers.onStatus?.("closed");
    },
  };
}
