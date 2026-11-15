"use client";
// Assurance · security (plan §6.6): signed claim → signature → witness → ACP → learning, gated by time.
// Focus = selected claim, else the latest disputed claim, else the latest claim. Learning (step 5) is only
// revealed once the claim's wave has ended (episode admission + guarded update happen at wave end).
import { claimsAt, clockAt } from "@/lib/derive";
import { useStore } from "@/lib/store";
import type { Claim, TwinState } from "@/lib/types";
import { Badge, useSel, useTwin } from "@/components/shell/ui";

export interface SecurityPipelineProps {
  className?: string;
}

const what = (c: Claim) =>
  c.type === "REWARD_CLAIM" ? `Reward ${c.claimed_reward}` : c.type === "TASK_STARTED" ? `Started ${c.task}` : `${c.task} completed`;

export function SecurityPipeline({ className }: SecurityPipelineProps) {
  const { state, t } = useTwin();
  const { sel, is } = useSel();
  const select = useStore((s) => s.select);
  if (!state) return <div className="zh-empty">Loading…</div>;
  const seen = claimsAt(state, t);
  const rev = [...seen].reverse();
  const picked = sel?.kind === "claim" ? seen.find((c) => c.id === sel.id) : undefined;
  const focus =
    picked ??
    rev.find((c) => c.evidence === "DISPUTED" && c.type !== "REWARD_CLAIM") ??
    rev.find((c) => c.evidence === "DISPUTED") ??
    rev[0];
  const disputed = seen.filter((c) => c.evidence === "DISPUTED").length;
  const corroborated = seen.filter((c) => c.evidence === "CORROBORATED").length;

  return (
    <div className={`grid h-full min-h-0 grid-cols-[minmax(0,1.7fr)_minmax(320px,1fr)] ${className ?? ""}`}>
      <div className="zh-scroll border-r border-line px-3 py-2">
        {focus ? (
          <Focus key={`${focus.id}`} state={state} c={focus} t={t} />
        ) : (
          <div className="zh-empty">
            No signed claims yet. Each robot signs task claims with its Ed25519 key; the ACP checks every one against independent witness evidence.
          </div>
        )}
      </div>
      <div className="flex min-h-0 flex-col">
        <div className="flex-none border-b border-line px-3 py-1 text-[11px] text-ink2">
          {seen.length} signed claims · {corroborated} corroborated ·{" "}
          <b style={{ color: disputed ? "var(--sec)" : undefined }}>{disputed} disputed</b>
        </div>
        <div className="zh-scroll flex-1">
          {rev.slice(0, 120).map((c) => (
            <div
              key={c.id}
              className={`grid cursor-pointer grid-cols-[58px_34px_1fr_auto] items-center gap-1.5 border-b border-[#f0f2f6] px-3 py-[3px] text-[11px] hover:bg-panel2 ${
                is("claim", c.id) ? "bg-accent-bg" : c.evidence === "DISPUTED" ? "bg-[#faf7ff]" : ""
              }`}
              onClick={() => select(is("claim", c.id) ? null : { kind: "claim", id: c.id })}
            >
              <span className="mono text-muted">{clockAt(state, c.t)}</span>
              <span className="mono font-semibold">{c.agent}</span>
              <span className="truncate">{c.type === "REWARD_CLAIM" ? `reward ${c.claimed_reward}` : `${c.type === "TASK_STARTED" ? "started" : "done"} ${c.task}`}</span>
              <Badge cls={c.evidence === "DISPUTED" ? "DISPUTED" : c.evidence === "CORROBORATED" ? "CORROBORATED" : ""}>{c.evidence ?? c.auth}</Badge>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Focus({ state, c, t }: { state: TwinState; c: Claim; t: number }) {
  const bad = c.evidence === "DISPUTED";
  const w = state.waves.find((x) => x.number === c.wave);
  const admitted = !!w && t >= w.t1 - 1e-6 && w.status !== "preview";
  const witness =
    c.type === "REWARD_CLAIM"
      ? bad
        ? "Contradicted"
        : "Supported"
      : c.type === "TASK_STARTED"
        ? bad
          ? "Contradicted"
          : "Confirms start"
        : c.witness_state === "VERIFIED_COMPLETE"
          ? "Supports claim"
          : c.witness_state
            ? `Saw ${c.witness_state.replace(/_/g, " ")}`
            : "No supporting evidence";
  const learnTxt = !admitted
    ? "awaiting ACP episode admission (wave end)"
    : w?.learning?.applied
      ? `Learner used ACP reward ${w.learning.reward} (${w.learning.source})`
      : w?.learning?.rejection
        ? `Update blocked: ${w.learning.rejection}`
        : "No update (fixed baseline)";
  const steps: [cls: string, label: string, head: string, sub: string, lit: boolean][] = [
    ["violet", "1 · Agent claim", c.agent, what(c), true],
    [c.auth === "AUTHENTICATED" ? "good" : "bad", "2 · Signature", c.auth === "AUTHENTICATED" ? "VALID" : "INVALID", c.auth_reasons.join(", ") || "Ed25519 · registered key · fresh seq", true],
    [bad ? "bad" : "good", "3 · Witness", witness, "independent sensor, own key", true],
    [bad ? "bad" : "good", "4 · ACP result", bad ? "REJECTED" : "CORROBORATED", c.reasons.join(", ") || "—", true],
    [bad ? "violet" : "good", "5 · Learning", bad ? "Claim not learned" : "Eligible", learnTxt, admitted],
  ];
  return (
    <>
      <div className="flex items-center gap-2.5 text-[12px]">
        <div className="grid h-[32px] w-[32px] flex-none place-items-center rounded-lg" style={{ background: bad ? "var(--bad-bg)" : "var(--ok-bg)" }}>
          <svg width="18" height="18" viewBox="0 0 24 24">
            <path d="M12 2l8 3v6c0 5-3.5 9.5-8 11-4.5-1.5-8-6-8-11V5l8-3z" fill={bad ? "#d92d2d" : "#059669"} />
          </svg>
        </div>
        <div className="min-w-0">
          <b>{bad ? "Malicious agent report detected" : "Latest claim verified"}</b>
          <div className="truncate text-[11.5px] text-muted">
            {c.agent} · {c.type} · wave {c.wave} · {clockAt(state, c.t)}
            {c.false_claim && <span className="text-sec"> · simulator oracle: false claim</span>}
          </div>
        </div>
      </div>
      <div className="zh-flow mt-2">
        {steps.map(([cls, label, head, sub, lit], i) => (
          <div key={label} className={`zh-fs ${cls} ${lit ? "anim" : ""}`} style={lit ? { animationDelay: `${i * 0.3}s` } : undefined}>
            <label>{label}</label>
            <b>{head}</b>
            <small>{sub}</small>
          </div>
        ))}
      </div>
      <div className={`zh-verdict ${bad ? "bad" : "ok"}`} style={{ animationDelay: "1.4s" }}>
        {bad ? (
          <>
            <b>SECURITY VIOLATION DETECTED</b> · a valid signature proved <i>who</i> sent it, not that it is true. Claim quarantined;{" "}
            {admitted && w?.reward
              ? `reward recomputed from witness evidence: ${w.reward.value}${w.claimed_reward != null ? ` (claimed ${w.claimed_reward}, not used)` : ""}.`
              : "it will never reach the learner: only the ACP-recomputed reward can."}
          </>
        ) : (
          "Claim matches independent witness evidence."
        )}
      </div>
    </>
  );
}

export default SecurityPipeline;
