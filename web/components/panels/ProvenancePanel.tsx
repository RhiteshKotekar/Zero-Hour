"use client";
// Backend provenance (plan §6.6; idea retained from the teammate's Streamlit twin): where every number on this page
// comes from — all values below are read from the state snapshot, nothing is hard-coded.
import { clockAt, fmtS } from "@/lib/derive";
import { useStore } from "@/lib/store";
import { Badge, useTwin } from "@/components/shell/ui";

export interface ProvenancePanelProps {
  className?: string;
}

export function ProvenancePanel({ className }: ProvenancePanelProps) {
  const { state, t } = useTwin();
  const mode = useStore((s) => s.mode);
  const source = useStore((s) => s.source);
  const revision = useStore((s) => s.revision);
  if (!state) return <div className="zh-empty">Loading…</div>;
  const sp = state.spec;
  const waves = state.waves.filter((w) => w.t0 <= t);
  return (
    <div className={`zh-scroll grid h-full grid-cols-3 gap-3 p-3 text-[11.5px] ${className ?? ""}`}>
      <Block title="Run">
        <KV k="Source" v={mode === "live" ? `LIVE · session ${state.live?.session_id ?? "—"} · rev ${revision}` : source || "REPLAY · recorded SAMG run"} />
        <KV k="Scenario" v={`${sp.scenario}${sp.label ? ` — ${sp.label}` : ""}`} />
        <KV k="Policy" v={`${sp.policy_label} (${sp.policy_kind})`} />
        <KV k="Seed" v={sp.seed} />
        <KV k="Learner warm-up" v={sp.experience ? `${sp.experience} generated warehouse missions` : "none"} />
        <KV k="Allocator" v={sp.use_cpsat === false ? "greedy (CP-SAT off)" : "OR-Tools CP-SAT"} />
        <KV k="Order source" v={sp.order_source === "generated" ? "generated (seeded synthetic demand)" : "config order book"} />
        <KV k="Injections" v={sp.injections.length ? sp.injections.join("; ") : "none"} />
        <KV k="Contract" v={`${state.version} · ${state.config_version} · start ${state.start_clock}`} />
      </Block>
      <Block title="SAMG waves (revealed by time)">
        {waves.map((w) => {
          const done = t >= w.t1 - 1e-6 && w.status !== "preview";
          return (
            <div key={w.number} className="mb-1.5 rounded-md border border-line px-2 py-1">
              <div className="flex items-center gap-1.5">
                <b className="mono">{w.mission_id}</b>
                <span className="text-muted">
                  {clockAt(state, w.t0)}–{done ? clockAt(state, w.t1) : "…"}
                </span>
                {w.status && <Badge cls={w.status === "preview" ? "" : "ok"}>{w.status.toUpperCase()}</Badge>}
              </div>
              <div className="text-muted">
                {w.policy} → {w.topology ?? "none"} · {w.allocation ? `${w.allocation.solver} ${w.allocation.status}${w.allocation.fallback ? " (fallback)" : ""} · makespan ${fmtS(w.allocation.objective.makespan_s)}` : "no allocation"}
                {w.physical_passes ? ` · ${w.physical_passes} physical passes` : ""}
              </div>
              {done && (
                <div className="text-muted">
                  episode <b className="text-ink2">{w.episode?.status ?? "—"}</b>
                  {w.episode?.reasons?.length ? ` (${w.episode.reasons.join(", ")})` : ""} · reward {w.reward ? w.reward.value : "—"}
                  {w.claimed_reward != null ? ` · agent-claimed ${w.claimed_reward} (not used)` : ""} · learning{" "}
                  {w.learning ? (w.learning.applied ? `applied ← ${w.learning.source}` : w.learning.rejection ?? "none") : "—"}
                </div>
              )}
            </div>
          );
        })}
        {!waves.length && <div className="text-muted">No wave yet.</div>}
      </Block>
      <Block title="Data provenance">
        <p className="mb-1.5 text-ink2">
          Every robot position, route, wait, task state, claim verdict, reward and topology score here comes from SAMG (
          <span className="mono">samg.*</span>) via the warehouse twin (<span className="mono">samg.twin.build_state</span>)
          {mode === "live" ? ", streamed from the live session" : ", recorded from one deterministic run"}. SAMG chooses the topology, allocates, executes,
          verifies (witness + ACP) and learns; the UI only reveals the state at t.
        </p>
        <KV k="Records" v={`${state.events.length} events · ${state.claims.length} signed claims · ${state.witness_events?.length ?? "—"} witness obs.`} />
        <KV k="Fleet" v={`${state.robots.filter((r) => r.physical).length} physical robots + ${state.robots.filter((r) => !r.physical).map((r) => r.id).join(", ") || "—"}`} />
        <KV k="Floor" v={`${state.layout.width} × ${state.layout.height} m · ${state.layout.racks.length} racks · ${state.layout.aisles.length} aisles`} />
        <div className="mt-1.5 rounded-md bg-panel2 px-2 py-1 text-[10.5px] text-muted">
          Simulated, not mock: robot motion and battery (twin physics model: A* routes, aisle locks fed back as task delays), simulated clock
          {sp.order_source === "generated" ? ", generated order stream (seeded generate_orders)" : ""}. No mock data on this page.
        </div>
      </Block>
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="cap mb-1.5">{title}</div>
      {children}
    </div>
  );
}
function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-2 py-[1px]">
      <span className="text-muted">{k}</span>
      <span className="min-w-0 break-words">{v}</span>
    </div>
  );
}

export default ProvenancePanel;
