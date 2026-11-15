"use client";
// Session ▾ (plan §6.4 control bar): start a live SAMG session, attach to the running one, or switch to a replay.
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";
import { attachLive, startSession, switchToReplay, useLive } from "@/lib/live";
import { useStore } from "@/lib/store";

export interface SessionDrawerProps {
  className?: string;
}

/** Closes a popover on outside click / Escape. */
export function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  return { open, setOpen, ref };
}

/** Meta from the backend (cached); `error` set when the backend is unreachable. */
export function useMeta(enabled: boolean) {
  const [meta, setMeta] = useState<api.Meta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    if (!enabled || meta) return;
    let off = false;
    api
      .getMeta()
      .then((m) => !off && (setMeta(m), setError(null)))
      .catch((e) => !off && setError((e as Error).message));
    return () => {
      off = true;
    };
  }, [enabled, meta, nonce]);
  return { meta, error, retry: () => setNonce((n) => n + 1) };
}

export function OfflineNote({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="rounded-[7px] border border-warn/40 bg-warn-bg px-2.5 py-2 text-[11.5px] text-ink2">
      <b className="text-warn">Backend offline.</b> Start it with <code className="mono text-[11px]">.venv/bin/python -m samg.api</code>
      {" "}— replay of the recorded run still works.
      {onRetry && (
        <button className="ml-2 font-semibold text-accent underline" onClick={onRetry}>
          retry
        </button>
      )}
    </div>
  );
}

const WARMUP_S = 12;

export function SessionDrawer({ className }: SessionDrawerProps) {
  const { open, setOpen, ref } = usePopover();
  const mode = useStore((s) => s.mode);
  const source = useStore((s) => s.source);
  const { meta, error, retry } = useMeta(open);
  const starting = useLive((s) => s.starting);
  const server = useLive((s) => s.server);
  const attached = useLive((s) => s.attached);
  const liveErr = useLive((s) => s.error);

  const [scenario, setScenario] = useState("judge_demo");
  const [policy, setPolicy] = useState("");
  const [seed, setSeed] = useState("");
  const [experience, setExperience] = useState("");
  const [cpsat, setCpsat] = useState(true);
  const [elapsed, setElapsed] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!starting) return;
    const id = window.setInterval(() => setElapsed((Date.now() - starting.since) / 1000), 200);
    return () => window.clearInterval(id);
  }, [starting]);

  const sc = meta?.scenarios.find((s) => s.id === scenario);
  const start = async () => {
    setMsg(null);
    setElapsed(0);
    try {
      await startSession({
        scenario,
        policy: policy || undefined,
        seed: seed === "" ? undefined : Number(seed),
        experience: experience === "" ? undefined : Number(experience),
        use_cpsat: cpsat,
      });
      setOpen(false);
    } catch (e) {
      setMsg((e as Error).message);
    }
  };
  const run = async (fn: () => Promise<unknown>, close = true) => {
    setMsg(null);
    try {
      await fn();
      if (close) setOpen(false);
    } catch (e) {
      setMsg((e as Error).message);
    }
  };
  const save = () =>
    run(async () => {
      const r = await api.saveRun();
      setMsg(`Saved run ${r.id}`);
    }, false);

  const field = "w-full rounded-[6px] border border-line2 bg-white px-2 py-1 text-[12px]";
  return (
    <div ref={ref} className={`relative ${className ?? ""}`}>
      <button className={`btn ${open ? "on" : ""}`} onClick={() => setOpen(!open)}>
        <span className={`inline-block h-[7px] w-[7px] rounded-full ${mode === "live" ? "bg-bad pulse" : "bg-samg"}`} />
        {mode === "live" ? "Live" : "Replay"} session ▾
      </button>
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-[340px] rounded-[10px] border border-line bg-panel p-3 shadow-[0_8px_28px_rgba(11,18,32,0.14)]">
          <div className="cap">Now showing</div>
          <div className="mt-0.5 truncate text-[12px] font-semibold">{source || "—"}</div>

          <div className="mt-3 flex items-center justify-between">
            <div className="cap">Start live SAMG session</div>
          </div>
          {error && !meta ? (
            <div className="mt-1.5">
              <OfflineNote onRetry={retry} />
            </div>
          ) : !meta ? (
            <div className="mt-2 text-[11.5px] text-muted">Loading backend meta…</div>
          ) : (
            <div className="mt-1.5 grid grid-cols-2 gap-2">
              <label className="col-span-2">
                <span className="cap">Scenario</span>
                <select className={field} value={scenario} onChange={(e) => setScenario(e.target.value)}>
                  {meta.scenarios.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className="cap">Policy</span>
                <select className={field} value={policy} onChange={(e) => setPolicy(e.target.value)}>
                  <option value="">scenario default{sc?.policy ? ` (${sc.policy})` : ""}</option>
                  {meta.policies.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className="cap">Seed</span>
                <input className={`${field} mono`} inputMode="numeric" placeholder={String(sc?.seed ?? "default")} value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ""))} />
              </label>
              <label>
                <span className="cap">Learner experience</span>
                <input className={`${field} mono`} inputMode="numeric" placeholder="config default" value={experience} onChange={(e) => setExperience(e.target.value.replace(/\D/g, ""))} />
              </label>
              <label className="flex items-end gap-1.5 pb-1 text-[12px]">
                <input type="checkbox" checked={cpsat} onChange={(e) => setCpsat(e.target.checked)} /> CP-SAT allocation
              </label>
              {sc && sc.script.length > 0 && (
                <div className="col-span-2 text-[11px] text-muted">
                  Scripted: {sc.script.map((s) => `${s.kind}@${s.at}s`).join(", ")}
                </div>
              )}
              <button className="btn primary col-span-2 justify-center" disabled={!!starting} onClick={start}>
                {starting ? "Starting…" : "▶ Start live session"}
              </button>
            </div>
          )}
          {starting && (
            <div className="mt-2">
              <div className="h-1.5 overflow-hidden rounded bg-line">
                <div className="h-full bg-accent transition-[width]" style={{ width: `${Math.min(100, (elapsed / WARMUP_S) * 100)}%` }} />
              </div>
              <div className="mt-1 text-[11px] text-muted">
                <span className="mono">{elapsed.toFixed(1)} s</span> · first adaptive session ≈{WARMUP_S} s (LinUCB learner warm-up), cached afterwards
              </div>
            </div>
          )}

          {server && !attached && (
            <div className="mt-3 rounded-[7px] border border-line bg-panel2 p-2">
              <div className="text-[11.5px]">
                Session on server: <b>{server.state.spec.label ?? server.state.spec.scenario}</b> ·{" "}
                <span className="mono">t={Math.round(server.state.live?.t ?? 0)}s</span>
              </div>
              <button className="btn mt-1.5" onClick={() => run(attachLive)}>
                Attach to live session
              </button>
            </div>
          )}

          <div className="mt-3 cap">Replay</div>
          <div className="mt-1.5 flex flex-wrap gap-2">
            <button className="btn" onClick={() => run(() => switchToReplay())}>
              Recorded judge demo
            </button>
            <Link className="btn" href="/replays">
              Saved runs →
            </Link>
            {attached && (
              <button className="btn" onClick={save}>
                Save this run
              </button>
            )}
          </div>
          {(msg || liveErr) && <div className="mt-2 text-[11.5px] text-ink2">{msg ?? liveErr}</div>}
        </div>
      )}
    </div>
  );
}

export default SessionDrawer;
