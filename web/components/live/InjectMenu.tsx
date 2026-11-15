"use client";
// Inject ▾ (plan §5.1 time-anchored injections). The backend decides what an injection does; the UI only sends
// it and shows the returned `effect` (or rejection reason).
import { useState } from "react";
import * as api from "@/lib/api";
import { fmtS, waveAt } from "@/lib/derive";
import { useLive } from "@/lib/live";
import { useSimT, useStore } from "@/lib/store";
import { OfflineNote, useMeta, usePopover } from "./SessionDrawer";

export interface InjectMenuProps {
  className?: string;
}

type Params = { robot: string; aisle: string; sku: string; task: string; delay_s: string };

export function InjectMenu({ className }: InjectMenuProps) {
  const { open, setOpen, ref } = usePopover();
  const mode = useStore((s) => s.mode);
  const state = useStore((s) => s.state);
  const t = useSimT();
  const attached = useLive((s) => s.attached);
  const { meta, error, retry } = useMeta(open);
  const [kind, setKind] = useState("robot_failure");
  const [p, setP] = useState<Params>({ robot: "auto:TRANSPORT", aisle: "", sku: "", task: "", delay_s: "20" });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<api.InjectResult | { error: string } | null>(null);

  const live = mode === "live" && attached;
  const inj = meta?.injections.find((i) => i.kind === kind);
  const needs = (inj?.needs ?? []).map((n) => n.replace("?", ""));
  const w = state ? waveAt(state, t) : null;
  const running = !!(state?.live?.planning === "running" && w && w.status === "preview" && t < w.t1);

  const scope =
    inj?.scope === "environment"
      ? { text: running ? "applies to the next wave (current wave keeps its plan)" : "applies to the next wave — triggers planning if idle", cls: "text-samg" }
      : running
        ? { text: `hits running wave ${w?.number} now (t=${fmtS(t)})`, cls: "text-bad" }
        : kind === "robot_failure"
          ? { text: "no wave running: robot goes down idle, excluded from later waves", cls: "text-warn" }
          : { text: "needs a running wave", cls: "text-warn" };

  const submit = async () => {
    setBusy(true);
    setResult(null);
    const r: api.InjectRequest = { kind };
    if (needs.includes("robot") && p.robot) r.robot = p.robot;
    if (needs.includes("aisle") && p.aisle) r.aisle = p.aisle;
    if (needs.includes("sku") && p.sku) r.sku = p.sku;
    if (needs.includes("task") && p.task) r.task = p.task;
    if (needs.includes("delay_s") && p.delay_s) r.delay_s = Number(p.delay_s);
    try {
      const res = await api.inject(r);
      setResult(res);
      useStore.getState().pushToast(res.accepted ? "warn" : "info", `${res.accepted ? "Injected" : "Rejected"} ${kind}: ${res.effect}`);
    } catch (e) {
      setResult({ error: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const field = "w-full rounded-[6px] border border-line2 bg-white px-2 py-1 text-[12px]";
  const set = (k: keyof Params) => (e: { target: { value: string } }) => setP({ ...p, [k]: e.target.value });
  const tasks = (state?.tasks ?? []).filter((x) => !w || w.tasks.includes(x.id));
  const recent = (state?.live?.injections ?? []).slice(-4).reverse();

  return (
    <div ref={ref} className={`relative ${className ?? ""}`}>
      <button className={`btn ${open ? "on" : ""}`} onClick={() => setOpen(!open)} title={live ? "" : "Injections need a live session"}>
        ⚡ Inject ▾
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1.5 w-[350px] rounded-[10px] border border-line bg-panel p-3 shadow-[0_8px_28px_rgba(11,18,32,0.14)]">
          <div className="cap">Inject disruption · at current sim time</div>
          {!live ? (
            <div className="mt-2 text-[11.5px] text-ink2">
              Injections are applied by the live backend. Start or attach a live session (Session ▾ or Auto demo); a replay is a fixed
              recording.
            </div>
          ) : error && !meta ? (
            <div className="mt-2">
              <OfflineNote onRetry={retry} />
            </div>
          ) : !meta ? (
            <div className="mt-2 text-[11.5px] text-muted">Loading…</div>
          ) : (
            <>
              <div className="mt-2 grid grid-cols-2 gap-1">
                {meta.injections.map((i) => (
                  <button
                    key={i.kind}
                    className={`rounded-[6px] border px-2 py-1 text-left text-[11.5px] font-semibold ${i.kind === kind ? "border-ink bg-ink text-white" : "border-line2 bg-white text-ink2 hover:bg-panel2"}`}
                    onClick={() => {
                      setKind(i.kind);
                      setResult(null);
                    }}
                  >
                    {i.label}
                    <span className={`block text-[9.5px] font-bold uppercase tracking-wider ${i.kind === kind ? "text-white/70" : "text-faint"}`}>{i.scope}</span>
                  </button>
                ))}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {needs.includes("robot") && (
                  <label className="col-span-2">
                    <span className="cap">Robot</span>
                    <select className={field} value={p.robot} onChange={set("robot")}>
                      <option value="auto:TRANSPORT">auto: robot on a TRANSPORT task</option>
                      <option value="auto:PICK">auto: robot on a PICK task</option>
                      {meta.robots
                        .filter((r) => r.physical)
                        .map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.id} · {r.label}
                          </option>
                        ))}
                    </select>
                  </label>
                )}
                {needs.includes("aisle") && (
                  <label className="col-span-2">
                    <span className="cap">Aisle</span>
                    <select className={field} value={p.aisle} onChange={set("aisle")}>
                      <option value="">— choose —</option>
                      {meta.aisles.map((a) => (
                        <option key={a}>{a}</option>
                      ))}
                    </select>
                  </label>
                )}
                {needs.includes("sku") && (
                  <label className="col-span-2">
                    <span className="cap">SKU</span>
                    <select className={field} value={p.sku} onChange={set("sku")}>
                      <option value="">— choose —</option>
                      {meta.skus.map((s) => (
                        <option key={s.sku} value={s.sku}>
                          {s.sku} · {s.name} (stock {s.stock})
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {needs.includes("task") && (
                  <label>
                    <span className="cap">Task</span>
                    <select className={field} value={p.task} onChange={set("task")}>
                      <option value="">auto (running)</option>
                      {tasks.map((x) => (
                        <option key={x.id}>{x.id}</option>
                      ))}
                    </select>
                  </label>
                )}
                {needs.includes("delay_s") && (
                  <label>
                    <span className="cap">Delay (s)</span>
                    <input className={`${field} mono`} inputMode="numeric" value={p.delay_s} onChange={(e) => setP({ ...p, delay_s: e.target.value.replace(/[^\d.]/g, "") })} />
                  </label>
                )}
              </div>
              <div className={`mt-2 text-[11.5px] font-semibold ${scope.cls}`}>{scope.text}</div>
              <button className="btn primary mt-2 w-full justify-center" disabled={busy} onClick={submit}>
                {busy ? "Re-planning…" : `Inject ${inj?.label ?? kind}`}
              </button>
              {result && (
                <div
                  className={`mt-2 rounded-[7px] border px-2.5 py-1.5 text-[11.5px] ${"error" in result ? "border-bad/40 bg-bad-bg" : result.accepted ? "border-ok/40 bg-ok-bg" : "border-warn/40 bg-warn-bg"}`}
                >
                  {"error" in result ? (
                    result.error
                  ) : (
                    <>
                      <b className={result.accepted ? "text-ok" : "text-warn"}>{result.accepted ? "ACCEPTED" : "REJECTED"}</b>
                      <span className="mono text-muted"> @ {fmtS(result.at)}</span> — {result.effect}
                    </>
                  )}
                </div>
              )}
            </>
          )}
          {recent.length > 0 && (
            <div className="mt-3 border-t border-line pt-2">
              <div className="cap">Injections this session</div>
              {recent.map((r, i) => (
                <div key={i} className="mt-1 text-[11px] leading-snug text-ink2">
                  <span className="mono text-muted">{fmtS(r.t)}</span> <b>{r.kind}</b> {r.target ?? ""}{" "}
                  <span className="text-faint">· {r.source ?? "operator"}</span>
                  {r.effect && <div className="text-muted">{r.effect}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default InjectMenu;
