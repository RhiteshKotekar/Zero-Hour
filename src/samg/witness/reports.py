"""Simulated agent reports derived from the execution trace (owner: Dev B).

Minimal integration version, written by the integrator for the Phase 2
vertical slice. Agent-side report generation sits next to the witness because
both turn the same ``ExecutionTrace`` into signed events; Dev B may move it.

Reports are built in two steps so an attack can rewrite them before signing:

1. ``draft_reports`` produces unsigned ``ReportDraft``s. Honest agents report
   ``TASK_STARTED`` when their task starts and ``TASK_COMPLETE_CLAIM`` when it
   finishes; they report nothing for failed or blocked tasks. One reporting
   agent (most assigned tasks, ties by agent id) files the after-action
   ``REWARD_CLAIM`` with the reward it computed from what it observed.
2. ``sign_reports`` assigns per-agent monotonically increasing ``seq`` numbers
   (in issue order) and signs each event with that agent's registered key.

A signature proves which key signed a report, never that the report is true.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from samg.assurance.identity import IdentityRegistry, KeyRing
from samg.assurance.signatures import sign_with_ring
from samg.domain import AgentEvent, AllocationPlan, EventType, ExecutionTrace, RewardBreakdown, TaskState
from samg.witness.service import event_id, sim_datetime


@dataclass(frozen=True)
class ReportDraft:
    """An unsigned report: who claims what, about which task, at which simulated time."""

    agent_id: str
    event_type: EventType
    sim_time_ms: int
    task_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    false_claim: bool = False  # evaluation-oracle label only; never signed or shown to the ACP


def reporting_agent(plan: AllocationPlan) -> str | None:
    """The agent that files the after-action report: most assigned tasks, ties by agent id."""
    counts = Counter(a.agent_id for a in plan.assignments)
    if not counts:
        return None
    return min(counts, key=lambda a: (-counts[a], a))


def reward_claim_payload(reward: RewardBreakdown, metrics: dict[str, float]) -> dict[str, Any]:
    return {"claimed_reward": round(reward.reward, 9),
            "claimed_metrics": {k: round(v, 9) for k, v in metrics.items()}}


def draft_reports(trace: ExecutionTrace, plan: AllocationPlan, observed_reward: RewardBreakdown) -> list[ReportDraft]:
    """Honest report drafts for every agent, in simulated-time order."""
    drafts: list[ReportDraft] = []
    for tr in trace.transitions:
        if tr.agent_id is None:
            continue
        ms = int(round(tr.sim_time))
        if tr.from_state is TaskState.ASSIGNED and tr.to_state is TaskState.EXECUTING:
            drafts.append(ReportDraft(tr.agent_id, EventType.TASK_STARTED, ms, tr.task_id))
        elif tr.to_state is TaskState.REPORTED_COMPLETE:
            drafts.append(ReportDraft(tr.agent_id, EventType.TASK_COMPLETE_CLAIM, ms, tr.task_id,
                                      {"sim_time_ms": ms}))
    reporter = reporting_agent(plan)
    if reporter is not None:
        m = trace.metrics
        end = int(round(max((t.sim_time for t in trace.transitions), default=0.0)))
        metrics = {"C": m.weighted_completion, "T": m.duration_norm, "R": m.resource_norm, "H": m.coordination_norm}
        drafts.append(ReportDraft(reporter, EventType.REWARD_CLAIM, end, None,
                                  reward_claim_payload(observed_reward, metrics)))
    return drafts


def sign_reports(
    drafts: list[ReportDraft], *, mission_id: str, epoch: int, base_time: datetime,
    registry: IdentityRegistry, ring: KeyRing,
) -> tuple[list[AgentEvent], dict[str, bool]]:
    """Sign drafts in order. Returns the events and an oracle map ``event_id -> false_claim``."""
    seq: dict[str, int] = defaultdict(int)
    events: list[AgentEvent] = []
    oracle: dict[str, bool] = {}
    for d in drafts:
        identity = registry.by_identity_id(d.agent_id)
        if identity is None:
            raise ValueError(f"agent {d.agent_id} has no registered identity")
        n = seq[d.agent_id]
        seq[d.agent_id] += 1
        unsigned = AgentEvent(
            event_id=event_id(mission_id, epoch, d.agent_id, n), mission_id=mission_id, epoch=epoch, seq=n,
            event_type=d.event_type, task_id=d.task_id, issued_at=sim_datetime(base_time, d.sim_time_ms),
            payload=d.payload, key_id=identity.key_id, agent_id=d.agent_id,
        )
        event = sign_with_ring(unsigned, ring)
        events.append(event)
        oracle[event.event_id] = d.false_claim
    return events, oracle


__all__ = ["ReportDraft", "draft_reports", "reporting_agent", "reward_claim_payload", "sign_reports"]
