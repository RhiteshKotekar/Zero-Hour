"""Phase 2 vertical slice: one mission end to end, the signed false-report attack, replay, determinism."""

from __future__ import annotations

import numpy as np
import pytest

from samg.assurance.admission import admit_episode, open_session, validate_event
from samg.assurance.freshness import InMemorySeenStore
from samg.assurance.identity import IdentityRegistry
from samg.demo import DemoConfig, run_demo
from samg.domain import (
    EpisodeStatus,
    EventStatus,
    EventType,
    IneligibleLearningEvent,
    LearningEvent,
    PolicyMode,
    ReasonCode,
    RewardSource,
    TaskState,
    TopologyName,
)
from samg.evaluation.attacks import AttackConfig
from samg.learning import ARM_ORDER, LinUCBPolicy, VulnerableLinUCB
from samg.orchestration import (
    RunSettings,
    World,
    execute_mission,
    receipt_order,
    replay_events,
    run_single_mission,
)
from samg.simulation.scenarios import judge_scenario

pytestmark = pytest.mark.integration

SETTINGS = RunSettings.load()
SEED = 7


def _ab(policy: LinUCBPolicy) -> dict[str, list]:
    s = policy.snapshot()
    return {"A": s["A"], "b": s["b"]}


def _attack(**kw) -> AttackConfig:
    base = dict(compromised_agent="A4", preferred_topology=TopologyName.FUNCTIONAL_CELL, schedule=frozenset({0}))
    return AttackConfig(**{**base, **kw})


def test_one_mission_end_to_end_protected() -> None:
    policy = LinUCBPolicy(seed=0, alpha=0.3)
    world = World.create(policy)
    before = _ab(policy)
    rec = run_single_mission(judge_scenario(SEED), world, SETTINGS, seed=SEED)

    assert rec.plan is not None and rec.plan.feasible and rec.trace is not None
    assert all(rec.eligibility[t].eligible for t in TopologyName)
    assert rec.episode.status is EpisodeStatus.ADMITTED
    assert ReasonCode.ALL_REWARD_CRITICAL_VERIFIED in rec.episode.reason_codes
    # every agent claim authenticated and corroborated; no claim was used as the reward
    assert all(d.status is EventStatus.AUTHENTICATED for d in rec.auth_decisions)
    agent_finals = [d for d in rec.final_decisions if d.signer_id != SETTINGS.security.witness.identity_id]
    assert agent_finals and all(d.status is EventStatus.CORROBORATED for d in agent_finals)
    # ACP-recomputed reward from witness evidence equals the simulator ground truth (faithful witness)
    assert rec.episode.reward == pytest.approx(rec.ground_truth_reward.reward, abs=1e-12)
    assert set(rec.episode.admitted_task_states.values()) == {TaskState.VERIFIED_COMPLETE}
    # guarded update applied exactly once, to the chosen arm only
    assert rec.learning_applied and rec.learning_event.reward_source is RewardSource.ACP_RECOMPUTED
    after = _ab(policy)
    chosen = rec.decision.topology.value
    assert after["b"][chosen] != before["b"][chosen]
    assert all(after["b"][a.value] == before["b"][a.value] for a in ARM_ORDER if a.value != chosen)
    repo = world.repo
    assert repo.count("learning_events", "applied_at IS NOT NULL") == 1
    assert repo.count("events_received") == len(rec.witness_events) + len(rec.agent_events)
    assert repo.count("episodes_trusted") == 1
    columns = " ".join(r[1] for t in ("missions", "events_received", "policy_state")
                       for r in repo.conn.execute(f"PRAGMA table_info({t})"))
    assert "private" not in columns.lower()


def test_false_signed_claim_moves_vulnerable_but_not_protected() -> None:
    """Same pre-attack state, same mission and ground truth; only the reports differ."""
    pre = LinUCBPolicy(seed=0, alpha=0.3)
    run_single_mission(judge_scenario(1), World.create(pre), SETTINGS, seed=1)  # non-trivial start state
    state = pre.snapshot()
    scenario = judge_scenario(SEED)
    # Sabotage makes the completion claim false too; the clean references get the same ground-truth failure.
    attack = _attack(sabotage_schedule=frozenset({0}))

    def run(policy, mode, with_attack, forced=()):
        world = World.create(policy, mode=mode)
        return run_single_mission(scenario, world, SETTINGS, seed=SEED,
                                  attack=attack if with_attack else None, forced_failures=forced)

    s2, s2_ref = LinUCBPolicy.from_snapshot(state), LinUCBPolicy.from_snapshot(state)
    s1, s1_ref = VulnerableLinUCB.from_snapshot(state), VulnerableLinUCB.from_snapshot(state)
    r2 = run(s2, PolicyMode.PROTECTED, True)
    sabotaged = attack.sabotaged_task(0, r2.plan)
    assert sabotaged is not None
    r2_ref = run(s2_ref, PolicyMode.PROTECTED, False, {sabotaged})
    r1 = run(s1, PolicyMode.VULNERABLE, True)
    r1_ref = run(s1_ref, PolicyMode.VULNERABLE, False, {sabotaged})

    # the false claims are validly signed, authorised and fresh, yet disputed by witness evidence
    false_ids = set(r2.false_claim_event_ids)
    types = {e.event_type for e in r2.agent_events if e.event_id in false_ids}
    assert types == {EventType.TASK_COMPLETE_CLAIM, EventType.REWARD_CLAIM}
    assert all(d.status is EventStatus.AUTHENTICATED for d in r2.auth_decisions if d.event_id in false_ids)
    assert all(d.status is EventStatus.DISPUTED for d in r2.final_decisions if d.event_id in false_ids)
    # one disputed agent cannot halt learning: witness covers every reward-critical task
    assert r2.episode.status is EpisodeStatus.ADMITTED
    assert ReasonCode.DISPUTED_CLAIM_QUARANTINED in r2.episode.reason_codes
    assert r2.episode.reward == pytest.approx(r2_ref.episode.reward, abs=0)

    # protected A/b are byte-identical to the attack-free reference; vulnerable ones are not
    assert _ab(s2) == _ab(s2_ref)
    assert _ab(s1) != _ab(s1_ref)
    assert r1.learning_event.reward_source is RewardSource.AGENT_CLAIM
    assert r1.learning_event.reward != pytest.approx(r1.ground_truth_reward.reward)


def test_missing_witness_evidence_is_provisional_and_cannot_update_protected() -> None:
    policy = LinUCBPolicy(seed=0)
    rec = run_single_mission(judge_scenario(SEED), World.create(LinUCBPolicy(seed=0)), SETTINGS, seed=SEED)
    scenario = judge_scenario(SEED)
    # drop the witness's terminal observation of the last reward-critical task
    witness = [w for w in rec.witness_events if not (w.task_id == "T8" and w.to_state is TaskState.VERIFIED_COMPLETE)]
    session = open_session(scenario, rec.plan, IdentityRegistry(rec.identities), SETTINGS.security,
                           InMemorySeenStore())
    received = [(e, validate_event(session, e, now=e.issued_at)) for e in receipt_order(witness, rec.agent_events)]
    admission = admit_episode(session, received, graph=rec.graph, episode_id="ep-missing", topology_decision_id="d",
                              reward_config=SETTINGS.reward, costs=SETTINGS.costs)
    assert admission.episode.status is EpisodeStatus.PROVISIONAL and admission.episode.reward is None
    assert ReasonCode.REWARD_CRITICAL_UNVERIFIED in admission.episode.reason_codes
    before = _ab(policy)
    event = LearningEvent(event_id="le", episode_id="ep-missing", decision_id="d", topology=rec.decision.topology,
                          feature_schema_version="ctx-v1", context=rec.context.features, reward=None,
                          reward_source=RewardSource.ACP_RECOMPUTED, status=admission.episode.status)
    with pytest.raises(IneligibleLearningEvent):
        policy.observe(event)
    assert _ab(policy) == before


def test_replayed_events_cause_no_second_update() -> None:
    policy = LinUCBPolicy(seed=0)
    world = World.create(policy)
    scenario = judge_scenario(SEED)
    rec = run_single_mission(scenario, world, SETTINGS, seed=SEED)
    snap = policy.snapshot()
    decisions, applied, reason = replay_events(scenario, rec, world, SETTINGS,
                                               [*rec.agent_events, *rec.witness_events])
    assert {d.status for d in decisions} == {EventStatus.DUPLICATE}
    assert not applied and reason is ReasonCode.DUPLICATE_EPISODE
    assert policy.snapshot() == snap
    assert world.repo.count("learning_events", "applied_at IS NOT NULL") == 1


def test_run_record_is_deterministic() -> None:
    def once():
        world = World.create(LinUCBPolicy(seed=0))
        return run_single_mission(judge_scenario(SEED), world, SETTINGS, seed=SEED,
                                  attack=_attack()).deterministic_dump()

    assert once() == once()


def test_execute_mission_is_policy_free_and_matches_run() -> None:
    scenario = judge_scenario(SEED)
    rec = run_single_mission(scenario, World.create(LinUCBPolicy(seed=0)), SETTINGS, seed=SEED)
    ex = execute_mission(scenario, rec.decision.topology, SETTINGS, seed=SEED, decision_id="eval-0")
    assert ex.feasible and ex.episode.status is EpisodeStatus.ADMITTED
    assert ex.episode.reward == rec.episode.reward
    assert ex.ground_truth_reward.reward == rec.ground_truth_reward.reward
    assert set(ex.metrics_dict()) >= {"C", "T", "R", "H"}


def test_vulnerable_learner_is_never_default_wiring() -> None:
    with pytest.raises(ValueError):
        World.create(VulnerableLinUCB(seed=0))
    with pytest.raises(ValueError):
        World.create(LinUCBPolicy(seed=0), mode=PolicyMode.VULNERABLE)


def test_demo_is_deterministic_and_attack_only_moves_vulnerable() -> None:
    cfg = DemoConfig(n_learn=6, n_attack=4)
    lines_a: list[str] = []
    lines_b: list[str] = []
    res = run_demo(lines_a.append, cfg)
    run_demo(lines_b.append, cfg)
    assert lines_a == lines_b
    assert res.comparison is not None
    assert set(res.comparison.test) >= {"P0-H", "P0-F", "P0-D", "P1", "P2", "P3", "P4"}
    assert "SECTION 4. POLICY COMPARISON" in "\n".join(lines_a)
    assert all(not r.attacked or r.learning_event.reward_source is RewardSource.ACP_RECOMPUTED
               for r in res.protected_attack if r.learning_event)
    false_decisions = [d for r in res.protected_attack for d in r.final_decisions
                       if d.event_id in r.false_claim_event_ids]
    assert false_decisions and all(d.status is EventStatus.DISPUTED for d in false_decisions)
    assert all(r.learning_applied and r.learning_event.reward_source is RewardSource.AGENT_CLAIM
               for r in res.vulnerable_attack)
    s1, s2 = res.vulnerable_state, res.protected_state
    assert any(not np.array_equal(np.array(s1["A"][a.value]), np.array(s2["A"][a.value])) for a in ARM_ORDER)
