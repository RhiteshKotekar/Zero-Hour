"use client";
// Small shared building blocks for the Phase 2-C panels. Values only — no SAMG logic here.
import type { ReactNode } from "react";
import { ROLE_COLOR, selectionRobot } from "@/lib/derive";
import { useSimT, useStore } from "@/lib/store";
import type { Selection, SelectionKind, TwinState } from "@/lib/types";

export function Card({
  title,
  sub,
  right,
  className,
  bodyClassName,
  children,
}: {
  title: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  return (
    <section className={`zh-card ${className ?? ""}`}>
      <div className="zh-ch">
        <h2>{title}</h2>
        {sub != null && <span className="sub">{sub}</span>}
        {right && <div className="r">{right}</div>}
      </div>
      <div className={`zh-scroll flex-1 ${bodyClassName ?? ""}`}>{children}</div>
    </section>
  );
}

/** state + committed sim time (≈10 Hz). */
export function useTwin(): { state: TwinState | null; t: number } {
  const state = useStore((s) => s.state);
  const t = useSimT();
  return { state, t };
}

/** Current selection plus the robot it resolves to at t (robot / task assignee / claim signer). */
export function useSel(): { sel: Selection | null; selRobot: string | null; is: (kind: SelectionKind, id: string | null | undefined) => boolean } {
  const sel = useStore((s) => s.selection);
  const state = useStore((s) => s.state);
  const t = useSimT();
  return {
    sel,
    selRobot: selectionRobot(state, sel, t),
    is: (kind, id) => !!sel && !!id && sel.kind === kind && sel.id === id,
  };
}

export function AgentChip({ state, id, onClick, selected }: { state: TwinState; id: string; onClick?: () => void; selected?: boolean }) {
  const r = state.robots.find((x) => x.id === id);
  return (
    <span
      className={`zh-agent ${selected ? "sel" : ""}`}
      style={{ background: ROLE_COLOR[r?.role ?? ""] ?? "#334155" }}
      onClick={(e) => {
        if (!onClick) return;
        e.stopPropagation();
        onClick();
      }}
      title={r ? `${r.id} · ${r.label}` : id}
    >
      {id}
    </span>
  );
}

export const Pri = ({ p }: { p: string }) => <span className={`zh-pri ${p}`}>{p}</span>;
export const Badge = ({ cls, children }: { cls?: string; children: ReactNode }) => <span className={`zh-sb ${cls ?? ""}`}>{children}</span>;

export const TONE_VAR: Record<string, string> = { ok: "var(--ok)", warn: "var(--warn)", bad: "var(--bad)", ink: "var(--ink2)", sec: "var(--sec)" };

export const CTX_NAMES: Record<string, string> = {
  dependency_density: "Task dependency density",
  capability_heterogeneity: "Fleet capability diversity",
  resource_scarcity: "Resource pressure",
  agent_availability: "Robot availability",
};
