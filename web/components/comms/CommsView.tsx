"use client";
// 3D communication view (plan §6.7): same clock as the ops view. Nodes = WMS hub, robots, ACP, witness, LinUCB
// learner; edges = the current wave's SAMG coordination graph; traffic = handoffs, signed claims, witness
// observations and the guarded learner update, all revealed from the state by time.
import dynamic from "next/dynamic";
import { fmtS, topoLabel, waveAt } from "@/lib/derive";
import { useSimT, useStore } from "@/lib/store";
import type { TwinState } from "@/lib/types";
import { C, LINK_LABEL, classifyLink, inFlight, verdictColor, type LinkKind } from "./model";

const CommsCanvas = dynamic(() => import("./CommsScene"), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center cap">Loading comms view…</div>,
});

export interface CommsViewProps {
  className?: string;
}

export function CommsView({ className }: CommsViewProps) {
  const state = useStore((s) => s.state);
  if (!state)
    return (
      <div className={`grid h-full w-full place-items-center bg-bg ${className ?? ""}`}>
        <span className="cap">Loading…</span>
      </div>
    );
  return (
    <div className={`relative h-full w-full overflow-hidden bg-bg ${className ?? ""}`}>
      <CommsCanvas state={state} />
      <CommsOverlay state={state} />
    </div>
  );
}

const box = "rounded-[9px] border border-line bg-panel/95 shadow-[0_2px_10px_rgba(11,18,32,0.06)] backdrop-blur";

function CommsOverlay({ state }: { state: TwinState }) {
  const t = useSimT();
  const w = waveAt(state, t);
  const f = inFlight(state, t);
  const total = f.handoffs.length + f.claims.length + f.witness.length + f.updates.length;
  const sel = w?.arms.find((a) => a.selected);
  const kinds = new Set<LinkKind>(w?.graph ? w.graph.links.map(([a, b]) => classifyLink(w.graph!, a, b)) : []);
  const switching = w && w.number > 1 && t - w.t0 < 5;

  // recent traffic feed (revealed by t)
  type Row = { t: number; text: string; color: string };
  const rows: Row[] = [];
  for (const c of state.claims) {
    if (c.t > t) break;
    rows.push({ t: c.t, color: verdictColor(c), text: `${c.agent} → ACP · ${c.type.replace(/_/g, " ").toLowerCase()} ${c.task ?? ""} · ${c.evidence ?? c.auth}` });
  }
  for (const wv of state.waves)
    for (const h of wv.allocation?.handoffs ?? [])
      if (h.depart_s != null && h.depart_s <= t) rows.push({ t: h.depart_s, color: C.handoff, text: `handoff ${h.path.join(" → ")} · ${h.from_task} ⇒ ${h.to_task}` });
  for (const wv of state.waves)
    if (wv.learning && wv.status !== "preview" && wv.t1 <= t)
      rows.push({
        t: wv.t1,
        color: wv.learning.applied ? C.ok : C.bad,
        text: `ACP → learner · wave ${wv.number} ${wv.learning.applied ? `update applied (r=${wv.learning.reward?.toFixed(3)})` : `update rejected: ${wv.learning.rejection ?? "—"}`}`,
      });
  rows.sort((a, b) => b.t - a.t);

  return (
    <>
      {/* topology chip + in-flight counter */}
      <div className={`pointer-events-none absolute left-3 top-3 z-10 px-3 py-2 ${box}`}>
        <div className="cap">Coordination graph · wave {w?.number ?? "—"}</div>
        <div className="mt-0.5 flex items-baseline gap-2">
          <span className="text-[15px] font-extrabold tracking-wide">{topoLabel(w?.topology)}</span>
          {sel && (
            <span className="mono text-[11px] text-ink2">
              score {sel.score.toFixed(3)} <span className="text-faint">= {sel.mean.toFixed(3)} + {sel.bonus.toFixed(3)}</span>
            </span>
          )}
        </div>
        <div className="mt-0.5 text-[10.5px] text-muted">
          {w ? `${w.policy} · ${w.graph?.links.length ?? 0} links · ${w.status === "preview" ? "running (preview)" : "committed"}` : "no wave yet"}
          {w?.excluded.length ? ` · excluded ${w.excluded.join(", ")}` : ""}
        </div>
        <div className="mt-2 flex items-baseline gap-2 border-t border-line pt-1.5">
          <span className="mono text-[20px] font-bold leading-none">{total}</span>
          <span className="cap">messages in flight</span>
        </div>
        <div className="mono mt-1 grid grid-cols-4 gap-2 text-[10.5px] text-ink2">
          <span title="handoffs">⇄ {f.handoffs.length}</span>
          <span title="signed claims" style={{ color: C.claim }}>✉ {f.claims.length}</span>
          <span title="witness observations" style={{ color: C.witness }}>◉ {f.witness.length}</span>
          <span title="learner updates" style={{ color: C.ok }}>▲ {f.updates.length}</span>
        </div>
      </div>

      {switching && (
        <div className={`pointer-events-none absolute left-1/2 top-3 z-10 -translate-x-1/2 px-3 py-1.5 text-[12px] font-bold ${box}`}>
          Wave {w.number} · topology → <span className="text-accent">{topoLabel(w.topology)}</span>
          {w.excluded.length ? <span className="font-medium text-muted"> · without {w.excluded.join(", ")}</span> : null}
        </div>
      )}

      {/* legend */}
      <div className={`pointer-events-none absolute right-3 top-3 z-10 w-[230px] px-3 py-2 text-[11px] ${box}`}>
        <div className="cap">Links (SAMG coordination graph)</div>
        {(Object.keys(LINK_LABEL) as LinkKind[]).map((k) => (
          <div key={k} className={`mt-1 flex items-center gap-2 ${kinds.has(k) ? "" : "opacity-40"}`}>
            <span className="inline-block h-[3px] w-5 rounded" style={{ background: C[k] }} />
            {LINK_LABEL[k]}
          </div>
        ))}
        <div className="cap mt-2">Messages</div>
        <Legend color={C.handoff} shape="dot" text="Task handoff, hop by hop" />
        <Legend color={C.claim} shape="sq" text="Signed claim robot → ACP" />
        <Legend color={C.ok} shape="sq" text="… corroborated by witness" />
        <Legend color={C.bad} shape="sq" text="… disputed / rejected" />
        <Legend color={C.witness} shape="dia" text="Witness observation → ACP" />
        <Legend color={C.ok} shape="dot" text="Guarded update ACP → learner" />
        <div className="mt-2 text-[10px] leading-snug text-muted">
          Claims, observations and updates are instantaneous in SAMG; they are drawn over {"≈"}1.5–2.5 s so they stay visible.
        </div>
      </div>

      {/* recent traffic */}
      <div className={`pointer-events-none absolute bottom-3 left-3 z-10 w-[min(470px,calc(100%-24px))] px-3 py-2 ${box}`}>
        <div className="cap">Recent coordination traffic</div>
        {rows.slice(0, 5).map((r, i) => (
          <div key={i} className="mt-0.5 flex gap-2 truncate text-[11px]">
            <span className="mono w-[52px] shrink-0 text-muted">{fmtS(r.t)}</span>
            <span className="mt-[5px] inline-block h-[6px] w-[6px] shrink-0 rounded-full" style={{ background: r.color }} />
            <span className="truncate text-ink2">{r.text}</span>
          </div>
        ))}
        {!rows.length && <div className="mt-0.5 text-[11px] text-muted">No traffic yet.</div>}
      </div>
    </>
  );
}

function Legend({ color, shape, text }: { color: string; shape: "dot" | "sq" | "dia"; text: string }) {
  return (
    <div className="mt-1 flex items-center gap-2">
      <span
        className={`inline-block h-[8px] w-[8px] ${shape === "dot" ? "rounded-full" : shape === "dia" ? "rotate-45" : "rounded-[1px]"}`}
        style={{ background: color }}
      />
      {text}
    </div>
  );
}

export default CommsView;
