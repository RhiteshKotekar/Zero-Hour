"""ACP event validation, corroboration and episode admission (owner: Dev B, brief §8.2-8.7).

Minimal integration version, written by the integrator for the Phase 2
vertical slice. It composes Dev B's primitives only: ``verify_event``
(signatures), ``SecurityPolicy.allows`` (authorisation), ``FreshnessGuard``
(epoch / dedupe / clock) and ``TaskLedger`` (task-state machine).

Three stages, kept distinct (D015):

1. ``validate_event`` -> AUTHENTICATED / REJECTED / STALE / DUPLICATE.
   Witness transitions that pass advance the ``TaskLedger``; agent claims never do.
2. ``corroborate`` (agent claims only) -> CORROBORATED / DISPUTED / PROVISIONAL,
   by comparing the claim with the witness ledger. A ``REWARD_CLAIM`` is compared
   with the ACP-recomputed reward and is never used as the reward.
3. ``admit_episode`` -> ADMITTED / PROVISIONAL / REJECTED. ADMITTED needs a
   witness terminal state for every reward-critical task; the reward is then
   recomputed with ``samg.simulation.compute_reward`` from witness-verified
   outcomes. A disputed claim is quarantined (excluded) and the episode can still
   be ADMITTED when the witness covers every reward-critical task.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from samg.assurance.freshness import FreshnessGuard, SeenStore
from samg.assurance.identity import IdentityRegistry
from samg.assurance.policy import SecurityPolicy
from samg.assurance.signatures import verify_event
from samg.assurance.state_machine import TERMINAL_STATES, TaskLedger
from samg.domain import (
    AgentEvent,
    AllocationPlan,
    CoordinationGraph,
    EpisodeRecord,
    EpisodeStatus,
    EventDecision,
    EventStatus,
    EventType,
    GroundTruthMetrics,
    ReasonCode,
    RewardBreakdown,
    RewardConfig,
    Scenario,
    TaskOutcome,
    TaskState,
    TopologyCostConfig,
    WitnessEvent,
)
from samg.simulation import compute_metrics, compute_reward

ADMISSION_VERSION = "acp-v0-integration"

SignedEvent = AgentEvent | WitnessEvent


@dataclass
class ACPSession:
    """ACP state for one mission run: who is registered, what was seen, what the witness observed."""

    scenario: Scenario
    plan: AllocationPlan
    registry: IdentityRegistry
    policy: SecurityPolicy
    freshness: FreshnessGuard
    ledger: TaskLedger
    repo: object | None = None  # samg.persistence.repositories.Repository (duck-typed to avoid a cycle)
    _decision_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def next_decision_id(self, event_id: str) -> str:
        if self._decision_counts[event_id] == 0 and self.repo is not None:
            self._decision_counts[event_id] = self.repo.count("event_decisions", "event_id = ?", (event_id,))
        n = self._decision_counts[event_id]
        self._decision_counts[event_id] += 1
        return f"dec/{event_id}/{n}"

    def record(self, decision: EventDecision, event: SignedEvent) -> None:
        if self.repo is not None:
            self.repo.add_event_decision(decision, event)


def open_session(
    scenario: Scenario, plan: AllocationPlan, registry: IdentityRegistry, policy: SecurityPolicy,
    seen: SeenStore, repo: object | None = None,
) -> ACPSession:
    """Start an ACP session for the mission's active epoch with a (possibly DB-backed) seen-store."""
    mission = scenario.mission
    freshness = FreshnessGuard(
        active_epochs={mission.mission_id: mission.epoch},
        max_clock_skew=timedelta(seconds=policy.freshness.max_clock_skew_seconds),
        max_event_age=timedelta(seconds=policy.freshness.max_event_age_seconds),
        seen=seen,
    )
    assignments = {a.task_id: a.agent_id for a in plan.assignments}
    ledger = TaskLedger(assignments, task_ids=[t.task_id for t in mission.tasks])
    return ACPSession(scenario=scenario, plan=plan, registry=registry, policy=policy, freshness=freshness,
                      ledger=ledger, repo=repo)


def _decision(session: ACPSession, event: SignedEvent, status: EventStatus,
              reasons: Sequence[ReasonCode] = (), cites: Sequence[str] = ()) -> EventDecision:
    return EventDecision(
        decision_id=session.next_decision_id(event.event_id), event_id=event.event_id,
        mission_id=event.mission_id, epoch=event.epoch, signer_id=event.signer_id,
        event_type=event.event_type, task_id=event.task_id, status=status,
        reason_codes=tuple(reasons), corroborating_event_ids=tuple(cites),
    )


def _payload_problem(event: SignedEvent) -> ReasonCode | None:
    if isinstance(event, AgentEvent) and event.event_type is EventType.REWARD_CLAIM:
        claimed = event.payload.get("claimed_reward")
        if not isinstance(claimed, int | float) or isinstance(claimed, bool) or not math.isfinite(claimed):
            return ReasonCode.MALFORMED
    return None


def validate_event(session: ACPSession, event: SignedEvent, now: datetime) -> EventDecision:
    """Authentication, authorisation, freshness and state-transition checks (brief §8.2).

    Returns AUTHENTICATED, REJECTED, STALE or DUPLICATE and records the decision.
    Only events that pass every check are added to the seen-store (so forged or
    unauthorised events cannot burn a signer's sequence numbers).
    """
    def done(status: EventStatus, reasons: Sequence[ReasonCode] = ()) -> EventDecision:
        decision = _decision(session, event, status, reasons)
        session.record(decision, event)
        return decision

    bad_sig = verify_event(event, session.registry)
    if bad_sig is not None:
        return done(EventStatus.REJECTED, [bad_sig])
    identity = session.registry.by_key_id(event.key_id)
    assert identity is not None  # verify_event guarantees it
    if not session.policy.allows(identity.role, event.event_type):
        return done(EventStatus.REJECTED, [ReasonCode.UNAUTHORISED_EVENT_TYPE])
    stale = session.freshness.check(event, now)
    if stale is not None:
        return done(stale.status, [stale.reason])
    malformed = _payload_problem(event)
    if malformed is not None:
        return done(EventStatus.REJECTED, [malformed])
    if isinstance(event, WitnessEvent):
        illegal = session.ledger.apply_witness(event)
    else:
        illegal = session.ledger.check_agent_claim(event)
    if illegal is not None:
        return done(EventStatus.REJECTED, [illegal])
    session.freshness.record(event)
    return done(EventStatus.AUTHENTICATED)


# --- corroboration -----------------------------------------------------------


def _within(a: datetime, b: datetime, tolerance_s: float) -> bool:
    return abs((a - b).total_seconds()) <= tolerance_s


def _task_claim(session: ACPSession, event: AgentEvent) -> tuple[EventStatus, list[ReasonCode], list[str]]:
    assert event.task_id is not None
    target = TaskState.EXECUTING if event.event_type is EventType.TASK_STARTED else TaskState.VERIFIED_COMPLETE
    tol = session.policy.corroboration.evidence_tolerance_seconds
    witnessed = [w for w in session.ledger.witness_events(event.task_id) if w.to_state is target]
    if witnessed:
        w = witnessed[0]
        if _within(event.issued_at, w.issued_at, tol):
            return EventStatus.CORROBORATED, [ReasonCode.WITNESS_CONFIRMS], [w.event_id]
        return EventStatus.DISPUTED, [ReasonCode.WITNESS_CONTRADICTS], []
    state = session.ledger.state(event.task_id)
    if state in TERMINAL_STATES or state is TaskState.BLOCKED:
        return EventStatus.DISPUTED, [ReasonCode.WITNESS_CONTRADICTS], []
    return EventStatus.PROVISIONAL, [ReasonCode.NO_WITNESS_EVIDENCE], []


def reward_upper_bound(session: ACPSession, reward_config: RewardConfig) -> float:
    """Highest reward the witness evidence still permits when coverage is incomplete.

    Every task the witness saw FAILED or BLOCKED is lost; every other task is
    assumed completed and every penalty term assumed perfect.
    """
    mission = session.scenario.mission
    total = sum(t.priority_weight for t in mission.tasks)
    lost = sum(t.priority_weight for t in mission.tasks
               if session.ledger.state(t.task_id) in (TaskState.FAILED, TaskState.BLOCKED))
    w_c = reward_config.weights["completion"]
    return w_c * (1.0 - lost / total) + (1.0 - w_c)


def corroborate(
    session: ACPSession, event: AgentEvent, recomputed: RewardBreakdown | None, evidence_ids: Sequence[str],
    upper_bound: float = 1.0,
) -> EventDecision:
    """Compare an AUTHENTICATED agent claim with witness evidence; record and return the decision.

    A ``REWARD_CLAIM`` is CORROBORATED when it matches the ACP-recomputed reward
    within ``metric_relative_tolerance``, DISPUTED when it does not (or, with
    incomplete coverage, when it exceeds ``upper_bound``), otherwise PROVISIONAL.
    Even a corroborated claim is never used as the reward.
    """
    tol = session.policy.corroboration.metric_relative_tolerance
    if event.event_type in (EventType.TASK_STARTED, EventType.TASK_COMPLETE_CLAIM):
        status, reasons, cites = _task_claim(session, event)
    elif event.event_type is EventType.REWARD_CLAIM:
        claimed = float(event.payload["claimed_reward"])
        if recomputed is None:
            status = EventStatus.DISPUTED if claimed > upper_bound * (1.0 + tol) else EventStatus.PROVISIONAL
            first = (ReasonCode.WITNESS_CONTRADICTS if status is EventStatus.DISPUTED
                     else ReasonCode.NO_WITNESS_EVIDENCE)
            reasons, cites = [first, ReasonCode.REWARD_CLAIM_NOT_TRUSTED], []
        else:
            if abs(claimed - recomputed.reward) <= tol * max(abs(recomputed.reward), 1e-9):
                status, reasons, cites = EventStatus.CORROBORATED, [ReasonCode.WITNESS_CONFIRMS], list(evidence_ids)
            else:
                status, reasons, cites = (EventStatus.DISPUTED,
                                          [ReasonCode.WITNESS_CONTRADICTS, ReasonCode.REWARD_CLAIM_NOT_TRUSTED], [])
    else:  # GRAPH_PATCH: not part of the MVP evidence path
        status, reasons, cites = EventStatus.PROVISIONAL, [ReasonCode.NO_WITNESS_EVIDENCE], []
    decision = _decision(session, event, status, reasons, cites)
    session.record(decision, event)
    return decision


# --- episode admission -------------------------------------------------------


@dataclass(frozen=True)
class Admission:
    """Episode decision plus the evidence trail that produced it."""

    episode: EpisodeRecord
    final_decisions: tuple[EventDecision, ...]  # one per received event, in receipt order
    metrics: GroundTruthMetrics | None
    breakdown: RewardBreakdown | None


def witness_outcomes(session: ACPSession) -> list[TaskOutcome]:
    """Task outcomes as established by witness evidence alone."""
    outcomes = []
    for task in session.scenario.mission.tasks:
        events = session.ledger.witness_events(task.task_id)
        start = next((w.sim_time_ms for w in events if w.to_state is TaskState.EXECUTING), None)
        end = next((w.sim_time_ms for w in events if w.to_state in TERMINAL_STATES), None)
        outcomes.append(TaskOutcome(
            task_id=task.task_id, agent_id=session.ledger.assignee(task.task_id),
            completed=session.ledger.state(task.task_id) is TaskState.VERIFIED_COMPLETE,
            start=None if start is None else float(start), end=None if end is None else float(end),
        ))
    return outcomes


def admit_episode(
    session: ACPSession,
    received: Sequence[tuple[SignedEvent, EventDecision]],
    *,
    graph: CoordinationGraph,
    episode_id: str,
    topology_decision_id: str,
    reward_config: RewardConfig,
    costs: TopologyCostConfig,
) -> Admission:
    """Corroborate authenticated claims and decide the episode (brief §8.4)."""
    mission, plan = session.scenario.mission, session.plan
    common = dict(episode_id=episode_id, mission_id=mission.mission_id, epoch=mission.epoch,
                  topology_decision_id=topology_decision_id, topology=plan.topology, plan_id=plan.plan_id)

    def rejected(reason: ReasonCode, finals: Sequence[EventDecision]) -> Admission:
        episode = EpisodeRecord(**common, event_decisions=tuple(finals), admitted_task_states=session.ledger.states,
                                status=EpisodeStatus.REJECTED, reason_codes=(reason,))
        return Admission(episode, tuple(finals), None, None)

    if not plan.feasible:
        return rejected(ReasonCode.INFEASIBLE_PLAN, [d for _, d in received])
    if plan.graph_version != graph.graph_version or plan.mission_id != mission.mission_id:
        return rejected(ReasonCode.WRONG_MISSION, [d for _, d in received])
    witness_illegal = [d for e, d in received if isinstance(e, WitnessEvent)
                       and d.status is EventStatus.REJECTED and ReasonCode.ILLEGAL_TRANSITION in d.reason_codes]

    critical = [t.task_id for t in mission.tasks if t.reward_critical]
    uncovered = [t for t in critical if session.ledger.state(t) not in TERMINAL_STATES]
    metrics = breakdown = None
    if not uncovered and not witness_illegal:
        metrics = compute_metrics(session.scenario, graph, plan, witness_outcomes(session), costs)
        breakdown = compute_reward(metrics, reward_config)
    evidence = [w.event_id for t in critical for w in session.ledger.witness_events(t) if w.to_state in TERMINAL_STATES]
    bound = reward_upper_bound(session, reward_config)

    finals: list[EventDecision] = []
    for event, decision in received:
        if isinstance(event, AgentEvent) and decision.status is EventStatus.AUTHENTICATED:
            finals.append(corroborate(session, event, breakdown, evidence, bound))
        else:
            finals.append(decision)
    if witness_illegal:
        return rejected(ReasonCode.ILLEGAL_TRANSITION, finals)

    disputed = any(d.status is EventStatus.DISPUTED for d in finals)
    quarantine = (ReasonCode.DISPUTED_CLAIM_QUARANTINED,) if disputed else ()
    if uncovered:
        episode = EpisodeRecord(**common, event_decisions=tuple(finals), admitted_task_states=session.ledger.states,
                                status=EpisodeStatus.PROVISIONAL,
                                reason_codes=(ReasonCode.REWARD_CRITICAL_UNVERIFIED, *quarantine))
        return Admission(episode, tuple(finals), None, None)
    assert breakdown is not None
    episode = EpisodeRecord(
        **common, event_decisions=tuple(finals), admitted_task_states=session.ledger.states,
        reward=breakdown.reward, reward_terms=dict(breakdown.contributions),
        reward_schema_version=breakdown.reward_schema_version, status=EpisodeStatus.ADMITTED,
        reason_codes=(ReasonCode.ALL_REWARD_CRITICAL_VERIFIED, *quarantine),
    )
    return Admission(episode, tuple(finals), metrics, breakdown)


__all__ = [
    "ACPSession",
    "ADMISSION_VERSION",
    "Admission",
    "admit_episode",
    "corroborate",
    "open_session",
    "reward_upper_bound",
    "validate_event",
    "witness_outcomes",
]
