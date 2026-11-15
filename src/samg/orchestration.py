"""End-to-end mission loop (owner: Dev B, brief §10).

Minimal integration version, written by the integrator for the Phase 2
vertical slice. ``run_single_mission`` is the one place where the decision plane
and the Assurance Control Plane meet:

    scenario -> features -> eligible topologies -> policy.select -> graph
      -> allocate -> simulate -> witness events + agent reports (+ attack)
      -> ACP validate / corroborate / admit -> persist -> guarded policy update

Protected mode: the policy observes only an ADMITTED episode with the
ACP-recomputed reward, through the policy's ``ProtectedGate``.
Vulnerable mode (Experiment C only, ``VulnerableLinUCB``): the policy observes
the last *authenticated* ``REWARD_CLAIM`` (signature, role and freshness pass;
corroboration ignored) — the flaw under test.

Each ``World`` is one deployment: its own SQLite store (dedupe barrier, audit
log) and one policy instance. Protected and vulnerable learners in the attack
comparison run in separate worlds so their events never collide.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from samg.allocation import allocate, feasible_topologies
from samg.assurance.admission import admit_episode, open_session, validate_event
from samg.assurance.freshness import InMemorySeenStore
from samg.assurance.identity import Identity, IdentityRegistry, KeyRing, build_identities
from samg.assurance.policy import SecurityPolicy, load_security_policy
from samg.context import MissionContext, extract_features
from samg.domain import (
    AgentEvent,
    AllocationConfig,
    AllocationPlan,
    CoordinationGraph,
    EpisodeRecord,
    EpisodeStatus,
    EventDecision,
    EventStatus,
    EventType,
    ExecutionTrace,
    GroundTruthMetrics,
    IdentityRole,
    IneligibleLearningEvent,
    LearningEvent,
    PolicyMode,
    ReasonCode,
    RewardBreakdown,
    RewardConfig,
    RewardSource,
    Scenario,
    TopologyCostConfig,
    TopologyEligibility,
    TopologyName,
    WitnessEvent,
    load_allocation,
    load_reward,
    load_topology_costs,
)
from samg.evaluation.attacks import AttackConfig, apply_attack
from samg.learning import PolicyDecision, TopologyPolicy, VulnerableLinUCB
from samg.persistence.db import connect
from samg.persistence.repositories import DbSeenStore, Repository
from samg.simulation import compute_reward
from samg.simulation import run as simulate
from samg.topology import build_graph
from samg.witness import WitnessService, draft_reports, sign_reports

ORCHESTRATION_VERSION = "orch-v0-integration"
SIM_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
"""Simulated clock origin. Mission ``i`` of a stream starts at ``SIM_BASE_TIME + i days``."""


# --- settings and worlds -----------------------------------------------------


@dataclass(frozen=True)
class RunSettings:
    costs: TopologyCostConfig
    allocation: AllocationConfig
    reward: RewardConfig
    security: SecurityPolicy

    @classmethod
    def load(cls, config_dir: Path | None = None, *, use_cpsat: bool | None = None) -> RunSettings:
        allocation = load_allocation(config_dir)
        if use_cpsat is not None:
            allocation = allocation.model_copy(update={"use_cpsat": use_cpsat})
        security_path = (config_dir / "security_policy.yaml") if config_dir else None
        return cls(costs=load_topology_costs(config_dir), allocation=allocation,
                   reward=load_reward(config_dir), security=load_security_policy(security_path))


@dataclass
class World:
    """One deployment: a SQLite audit store plus one policy instance."""

    repo: Repository
    policy: TopologyPolicy
    policy_instance: str
    mode: PolicyMode

    @classmethod
    def create(cls, policy: TopologyPolicy, *, mode: PolicyMode = PolicyMode.PROTECTED,
               policy_instance: str | None = None, db_path: str | Path = ":memory:") -> World:
        if (mode is PolicyMode.PROTECTED) == isinstance(policy, VulnerableLinUCB):
            raise ValueError("VulnerableLinUCB runs only in VULNERABLE mode, and VULNERABLE mode only with it")
        return cls(repo=Repository(connect(db_path)), policy=policy,
                   policy_instance=policy_instance or policy.kind, mode=mode)


# --- run record --------------------------------------------------------------


class MissionRunRecord(BaseModel):
    """Everything one mission run decided, observed and learned, for display, audit and tests."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    mission_index: int
    seed: int
    scenario_id: str
    mission_id: str
    epoch: int
    policy_instance: str
    policy_kind: str
    mode: PolicyMode
    context: MissionContext
    eligibility: dict[TopologyName, TopologyEligibility]
    decision: PolicyDecision
    topology_decision_id: str
    graph: CoordinationGraph | None = None
    plan: AllocationPlan | None = None
    trace: ExecutionTrace | None = None
    ground_truth_reward: RewardBreakdown | None = None
    identities: tuple[Identity, ...] = ()
    witness_events: tuple[WitnessEvent, ...] = ()
    agent_events: tuple[AgentEvent, ...] = ()
    auth_decisions: tuple[EventDecision, ...] = ()
    final_decisions: tuple[EventDecision, ...] = ()
    false_claim_event_ids: tuple[str, ...] = ()
    attacked: bool = False
    episode: EpisodeRecord | None = None
    acp_metrics: GroundTruthMetrics | None = None
    acp_reward: RewardBreakdown | None = None
    claimed_reward: float | None = None
    learning_event: LearningEvent | None = None
    learning_applied: bool = False
    learning_rejection: ReasonCode | None = None

    def deterministic_dump(self) -> dict[str, Any]:
        """JSON-safe dump without wall-clock fields (solver runtime)."""
        data = self.model_dump(mode="json")
        if data.get("plan"):
            data["plan"].pop("runtime_ms", None)
        return data


def identity_roles(scenario: Scenario, security: SecurityPolicy) -> dict[str, IdentityRole]:
    roles = {a.agent_id: IdentityRole.COORDINATOR if a.can_coordinate else IdentityRole.AGENT
             for a in scenario.agents}
    roles[security.witness.identity_id] = IdentityRole.WITNESS
    return roles


def mission_keys(scenario: Scenario, security: SecurityPolicy) -> tuple[IdentityRegistry, KeyRing]:
    """Deterministic simulation identities for the mission's agents and the witness (D019)."""
    return build_identities(scenario.seed, identity_roles(scenario, security))


def _last_authenticated_reward_claim(received: Sequence[tuple[AgentEvent | WitnessEvent, EventDecision]]) -> float | None:
    claimed = None
    for event, decision in received:
        if (isinstance(event, AgentEvent) and event.event_type is EventType.REWARD_CLAIM
                and decision.status is EventStatus.AUTHENTICATED):
            claimed = float(event.payload["claimed_reward"])
    return claimed


def receipt_order(witness: Sequence[WitnessEvent], agent: Sequence[AgentEvent]) -> list[AgentEvent | WitnessEvent]:
    """Order in which the ACP receives events: simulated time, witness first, then issue order."""
    tagged = [(w.issued_at, 0, i, w) for i, w in enumerate(witness)]
    tagged += [(a.issued_at, 1, i, a) for i, a in enumerate(agent)]
    return [e for *_, e in sorted(tagged, key=lambda x: x[:3])]


# --- execution of one chosen topology (policy-free) ---------------------------


class MissionExecution(BaseModel):
    """Result of executing one (scenario, topology): plan, ground truth, evidence and ACP admission.

    Maps onto ``samg.evaluation.runner.MissionResult``: ``feasible``,
    ``ground_truth_reward.reward``, ``episode`` and ``metrics_dict()``.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    decision_id: str
    graph: CoordinationGraph
    plan: AllocationPlan
    identities: tuple[Identity, ...]
    trace: ExecutionTrace | None = None
    ground_truth_reward: RewardBreakdown
    witness_events: tuple[WitnessEvent, ...] = ()
    agent_events: tuple[AgentEvent, ...] = ()
    auth_decisions: tuple[EventDecision, ...] = ()
    final_decisions: tuple[EventDecision, ...] = ()
    false_claim_event_ids: tuple[str, ...] = ()
    attacked: bool = False
    episode: EpisodeRecord
    acp_metrics: GroundTruthMetrics | None = None
    acp_reward: RewardBreakdown | None = None
    claimed_reward: float | None = None

    @property
    def feasible(self) -> bool:
        return self.plan.feasible

    def metrics_dict(self) -> dict[str, float]:
        """Ground-truth metrics (evaluation only) as a flat dict."""
        if self.trace is None:
            return {}
        m = self.trace.metrics
        return {"C": m.weighted_completion, "T": m.duration_norm, "R": m.resource_norm, "H": m.coordination_norm,
                "makespan_ms": m.makespan, "coordination_cost": m.coordination_cost,
                "communication_failures": float(m.communication_failures)}


@contextmanager
def _maybe_transaction(repo: Repository | None) -> Iterator[None]:
    if repo is None:
        yield
    else:
        with repo.transaction():
            yield


def execute_mission(
    scenario: Scenario,
    topology: TopologyName,
    settings: RunSettings,
    *,
    seed: int,
    decision_id: str,
    graph: CoordinationGraph | None = None,
    plan: AllocationPlan | None = None,
    repo: Repository | None = None,
    mission_index: int = 0,
    attack: AttackConfig | None = None,
    forced_failures: Collection[str] = (),
    task_delays_ms: Mapping[str, float] | None = None,
    agent_breakdowns: Mapping[str, str] | None = None,
) -> MissionExecution:
    """Graph -> allocate -> simulate -> witness + reports (+ attack) -> ACP validate/corroborate/admit.

    No policy is touched, so this is what a ``MissionExecutor`` adapter wraps.
    ``graph``/``plan`` may be passed in (e.g. from ``feasible_topologies``) to
    avoid solving twice. With ``repo`` every artefact is persisted and freshness
    uses the durable seen-store; the caller must have recorded the mission and
    the topology decision first (``run_single_mission`` does). Without ``repo``
    the ACP uses an in-memory seen-store and nothing is persisted.
    """
    mission = scenario.mission
    base_time = SIM_BASE_TIME + timedelta(days=mission_index)
    if graph is None or plan is None:
        _, graph = build_graph(scenario, topology, settings.costs)
        if graph is None:
            raise ValueError(f"{topology.value} is not structurally eligible for {mission.mission_id}")
        plan = allocate(scenario, graph, settings.costs, settings.allocation)
    if graph.topology is not topology or plan.topology is not topology:
        raise ValueError("graph/plan do not match the chosen topology")
    registry, ring = mission_keys(scenario, settings.security)
    if repo is not None:
        with repo.transaction():
            repo.add_graph_snapshot(graph_id=f"graph:{decision_id}", mission_id=mission.mission_id,
                                    epoch=mission.epoch, topology=topology.value, graph=graph)
            repo.add_allocation_plan(plan_id=plan.plan_id, decision_id=decision_id, feasible=plan.feasible,
                                     solver=plan.solver.value,
                                     plan=plan.model_dump(mode="json", exclude={"runtime_ms"}))
    seen = DbSeenStore(repo) if repo is not None else InMemorySeenStore()
    session = open_session(scenario, plan, registry, settings.security, seen, repo)

    trace = None
    witness_events: list[WitnessEvent] = []
    agent_events: list[AgentEvent] = []
    oracle: dict[str, bool] = {}
    attacked = False
    received: list[tuple[AgentEvent | WitnessEvent, EventDecision]] = []
    if plan.feasible:
        forced = set(forced_failures)
        sabotaged = attack.sabotaged_task(mission_index, plan) if attack is not None else None
        if sabotaged is not None:
            forced.add(sabotaged)
        trace = simulate(scenario, graph, plan, seed, settings.costs, forced_failures=forced,
                         task_delays_ms=task_delays_ms, agent_breakdowns=agent_breakdowns)
        gt_reward = compute_reward(trace.metrics, settings.reward)
        witness_events = WitnessService(settings.security.witness.identity_id, registry, ring).observe(trace, base_time)
        drafts = draft_reports(trace, plan, gt_reward)
        if attack is not None and attack.active(mission_index):
            attacked = True
            drafts = apply_attack(drafts, trace, plan, gt_reward, attack, agents=[a.agent_id for a in scenario.agents])
        agent_events, oracle = sign_reports(drafts, mission_id=mission.mission_id, epoch=mission.epoch,
                                            base_time=base_time, registry=registry, ring=ring)
        if repo is not None:
            repo.add_outcome(outcome_id=f"outcome:{decision_id}", plan_id=plan.plan_id, seed=seed, outcome=trace)
        with _maybe_transaction(repo):
            for event in receipt_order(witness_events, agent_events):
                received.append((event, validate_event(session, event, now=event.issued_at)))
    else:
        gt_reward = compute_reward(None, settings.reward)

    with _maybe_transaction(repo):
        admission = admit_episode(session, received, graph=graph, episode_id=f"episode:{decision_id}",
                                  topology_decision_id=decision_id, reward_config=settings.reward,
                                  costs=settings.costs)
        if repo is not None:
            repo.add_episode(admission.episode)
    return MissionExecution(
        decision_id=decision_id, graph=graph, plan=plan, identities=tuple(registry.identities()), trace=trace,
        ground_truth_reward=gt_reward, witness_events=tuple(witness_events), agent_events=tuple(agent_events),
        auth_decisions=tuple(d for _, d in received), final_decisions=admission.final_decisions,
        false_claim_event_ids=tuple(sorted(k for k, v in oracle.items() if v)), attacked=attacked,
        episode=admission.episode, acp_metrics=admission.metrics, acp_reward=admission.breakdown,
        claimed_reward=_last_authenticated_reward_claim(received),
    )


# --- the mission loop --------------------------------------------------------


def run_single_mission(
    scenario: Scenario,
    world: World,
    settings: RunSettings,
    *,
    seed: int,
    mission_index: int = 0,
    attack: AttackConfig | None = None,
    forced_failures: Collection[str] = (),
    task_delays_ms: Mapping[str, float] | None = None,
    agent_breakdowns: Mapping[str, str] | None = None,
    feasible: tuple[Any, Any, Any] | None = None,
) -> MissionRunRecord:
    """Run one mission end to end and apply (or refuse) the policy update. See module docstring.

    Eligibility follows D030: the policy is offered only topologies that build
    *and* have a feasible plan; the chosen arm's graph and plan are reused.
    """
    mission = scenario.mission
    repo, policy, instance = world.repo, world.policy, world.policy_instance
    prefix = f"{mission.mission_id}/e{mission.epoch}"

    context = extract_features(scenario)
    # ``feasible`` lets a caller that already solved feasible_topologies for this exact
    # scenario and settings (e.g. samg.warehouse's physical dry run) avoid solving twice.
    eligible, verdicts, plans = feasible or feasible_topologies(scenario, settings.costs, settings.allocation)
    decision = policy.select(context.features, eligible, context.feature_schema_version)
    decision_id = f"{prefix}/{instance}"

    identities = tuple(mission_keys(scenario, settings.security)[0].identities())
    with repo.transaction():
        repo.add_mission(mission_id=mission.mission_id, epoch=mission.epoch, seed=seed, mission=mission,
                         agents=[a.model_dump(mode="json") for a in scenario.agents],
                         identities=[i.model_dump(mode="json") for i in identities])
        repo.add_topology_decision(decision_id=decision_id, mission_id=mission.mission_id, epoch=mission.epoch,
                                   policy_instance=instance, decision=decision)
    base = dict(mission_index=mission_index, seed=seed, scenario_id=scenario.scenario_id,
                mission_id=mission.mission_id, epoch=mission.epoch, policy_instance=instance,
                policy_kind=policy.kind, mode=world.mode, context=context, eligibility=verdicts,
                decision=decision, topology_decision_id=decision_id, identities=identities)
    if decision.topology is None:
        return MissionRunRecord(**base)

    graph, plan = plans[decision.topology]
    ex = execute_mission(scenario, decision.topology, settings, seed=seed, decision_id=decision_id, graph=graph,
                         plan=plan, repo=repo, mission_index=mission_index, attack=attack,
                         forced_failures=forced_failures, task_delays_ms=task_delays_ms,
                         agent_breakdowns=agent_breakdowns)
    learning_event, applied, rejection = _learn(world, ex.episode, decision_id, context, ex.claimed_reward)
    repo.add_policy_snapshot(snapshot_id=f"policy:{decision_id}", policy_instance=instance, state=policy.snapshot())
    return MissionRunRecord(
        **base, graph=ex.graph, plan=ex.plan, trace=ex.trace, ground_truth_reward=ex.ground_truth_reward,
        witness_events=ex.witness_events, agent_events=ex.agent_events, auth_decisions=ex.auth_decisions,
        final_decisions=ex.final_decisions, false_claim_event_ids=ex.false_claim_event_ids, attacked=ex.attacked,
        episode=ex.episode, acp_metrics=ex.acp_metrics, acp_reward=ex.acp_reward, claimed_reward=ex.claimed_reward,
        learning_event=learning_event, learning_applied=applied, learning_rejection=rejection,
    )


def _learn(
    world: World, episode: EpisodeRecord, decision_id: str,
    context: MissionContext, claimed: float | None,
) -> tuple[LearningEvent | None, bool, ReasonCode | None]:
    """Offer the episode to the policy through its gate and record the attempt."""
    common = dict(event_id=f"le/{episode.episode_id}", episode_id=episode.episode_id, decision_id=decision_id,
                  topology=episode.topology, feature_schema_version=context.feature_schema_version,
                  context=context.features, status=episode.status)
    if world.mode is PolicyMode.VULNERABLE:
        if claimed is None:
            return None, False, ReasonCode.NO_WITNESS_EVIDENCE
        event = LearningEvent(**common, reward=claimed, reward_source=RewardSource.AGENT_CLAIM)
    elif episode.status is EpisodeStatus.ADMITTED:
        event = LearningEvent(**common, reward=episode.reward, reward_source=RewardSource.ACP_RECOMPUTED)
    else:
        # Not offered: the protected gate would refuse it (INV-05). Record why.
        event = LearningEvent(**common, reward=None, reward_source=RewardSource.ACP_RECOMPUTED)
        world.repo.add_learning_event(event, policy_instance=world.policy_instance, policy_kind=world.policy.kind,
                                      applied=False, rejection_reason=ReasonCode.INELIGIBLE_STATUS)
        return event, False, ReasonCode.INELIGIBLE_STATUS
    return event, *offer_learning_event(world, event)


def offer_learning_event(world: World, event: LearningEvent) -> tuple[bool, ReasonCode | None]:
    """Call ``policy.observe`` and persist whether the update was applied or refused."""
    try:
        world.policy.observe(event)
    except IneligibleLearningEvent as exc:
        world.repo.add_learning_event(event, policy_instance=world.policy_instance, policy_kind=world.policy.kind,
                                      applied=False, rejection_reason=exc.reason)
        return False, exc.reason
    world.repo.add_learning_event(event, policy_instance=world.policy_instance, policy_kind=world.policy.kind,
                                  applied=True)
    return True, None


def replay_events(
    scenario: Scenario, record: MissionRunRecord, world: World, settings: RunSettings,
    events: Sequence[AgentEvent | WitnessEvent],
) -> tuple[list[EventDecision], bool, ReasonCode | None]:
    """Resubmit already-processed signed events (secondary attack, brief §9.3).

    Validation uses the world's durable seen-store, so every event comes back
    DUPLICATE/STALE; the mission's learning event is then re-offered and must be
    refused as a duplicate episode (INV-08).
    """
    assert record.plan is not None
    registry = IdentityRegistry(record.identities)
    session = open_session(scenario, record.plan, registry, settings.security, DbSeenStore(world.repo), world.repo)
    with world.repo.transaction():
        decisions = [validate_event(session, e, now=e.issued_at) for e in events]
    applied, reason = (False, None)
    if record.learning_event is not None and record.learning_event.reward is not None:
        applied, reason = offer_learning_event(world, record.learning_event)
    return decisions, applied, reason


def run_stream(
    scenarios: Sequence[tuple[Scenario, int]], world: World, settings: RunSettings, *,
    start_index: int = 0, attack: AttackConfig | None = None,
) -> list[MissionRunRecord]:
    """Run ``(scenario, seed)`` pairs in order through one world."""
    return [run_single_mission(sc, world, settings, seed=seed, mission_index=start_index + i, attack=attack)
            for i, (sc, seed) in enumerate(scenarios)]


__all__ = [
    "ORCHESTRATION_VERSION",
    "SIM_BASE_TIME",
    "MissionExecution",
    "MissionRunRecord",
    "RunSettings",
    "World",
    "execute_mission",
    "identity_roles",
    "mission_keys",
    "offer_learning_event",
    "receipt_order",
    "replay_events",
    "run_single_mission",
    "run_stream",
]
