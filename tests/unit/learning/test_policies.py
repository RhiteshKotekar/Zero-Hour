"""LinUCB, UCB1, fixed baselines and the protected learning gate."""

from __future__ import annotations

import json

import numpy as np
import pytest

from samg.domain import (
    EpisodeStatus,
    IneligibleLearningEvent,
    LearningEvent,
    ReasonCode,
    RewardSource,
    TopologyName,
)
from samg.learning import (
    ARM_ORDER,
    ContextualEpsilonGreedyPolicy,
    FixedTopologyPolicy,
    LinUCBPolicy,
    UCB1Policy,
    VulnerableLinUCB,
    best_fixed_from_training,
    make_policy,
)

H, F, D = TopologyName.HIERARCHICAL, TopologyName.FUNCTIONAL_CELL, TopologyName.DISTRIBUTED
X = (1.0, 0.25, 0.5, 0.1, 1.0)
ALL = list(TopologyName)


def _event(i: int = 0, **kw: object) -> LearningEvent:
    base = dict(event_id=f"le{i}", episode_id=f"ep{i}", decision_id=f"d{i}", topology=D,
                feature_schema_version="ctx-v1", context=X, reward=0.8,
                reward_source=RewardSource.ACP_RECOMPUTED, status=EpisodeStatus.ADMITTED)
    return LearningEvent(**{**base, **kw})


def test_linucb_one_update_matches_closed_form() -> None:
    policy = LinUCBPolicy(dim=5, alpha=1.0, lam=1.0)
    policy.observe(_event(reward=0.8))
    x = np.array(X)
    expected_theta = 0.8 * x / (1 + x @ x)  # (I + x x^T)^-1 r x, Sherman–Morrison
    np.testing.assert_allclose(policy.theta(D), expected_theta, rtol=1e-12)
    np.testing.assert_allclose(policy.theta(H), np.zeros(5))
    _, bonuses, _ = policy.arm_scores(x)
    assert bonuses[D] == pytest.approx(np.sqrt((x @ x) / (1 + x @ x)))
    assert bonuses[H] == pytest.approx(np.sqrt(x @ x))


def test_linucb_two_step_known_matrix() -> None:
    policy = LinUCBPolicy(dim=2, alpha=0.0, lam=1.0, feature_schema_version="t")
    policy.observe(_event(0, context=(1.0, 0.0), reward=1.0, feature_schema_version="t"))
    policy.observe(_event(1, context=(0.0, 1.0), reward=0.5, feature_schema_version="t"))
    np.testing.assert_allclose(policy.A[D], [[2, 0], [0, 2]])
    np.testing.assert_allclose(policy.b[D], [1.0, 0.5])
    np.testing.assert_allclose(policy.theta(D), [0.5, 0.25])


def test_linucb_warmup_then_greedy_and_deterministic() -> None:
    def run(seed: int) -> list[TopologyName]:
        p = LinUCBPolicy(seed=seed, alpha=0.0)
        picks = []
        for i in range(6):
            d = p.select(X, ALL, "ctx-v1")
            assert d.topology is not None
            picks.append(d.topology)
            p.observe(_event(i, topology=d.topology, reward=0.9 if d.topology is F else 0.1))
        return picks

    first = run(3)
    assert set(first[:3]) == set(ALL)  # balanced warm-up covers each arm once
    assert first[3:] == [F, F, F]
    assert run(3) == first


def test_linucb_respects_eligibility_and_ties() -> None:
    p = LinUCBPolicy(warmup_per_arm=0)
    decision = p.select(X, [H, F], "ctx-v1")
    assert decision.eligible == tuple(a for a in ARM_ORDER if a in {H, F})
    # fresh state → all scores equal → earliest eligible arm in ARM_ORDER wins
    assert decision.topology == decision.eligible[0]
    none = p.select(X, [], "ctx-v1")
    assert none.topology is None and none.reason_codes == (ReasonCode.NO_ELIGIBLE_TOPOLOGY,)


def test_linucb_rejects_wrong_schema_or_dim() -> None:
    p = LinUCBPolicy()
    with pytest.raises(ValueError, match="CONTEXT_SCHEMA_MISMATCH"):
        p.select(X, ALL, "ctx-v2")
    with pytest.raises(ValueError, match="CONTEXT_SCHEMA_MISMATCH"):
        p.select(X[:3], ALL, "ctx-v1")


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (dict(status=EpisodeStatus.PROVISIONAL, reward=None), ReasonCode.INELIGIBLE_STATUS),
        (dict(status=EpisodeStatus.REJECTED, reward=None), ReasonCode.INELIGIBLE_STATUS),
        (dict(status=EpisodeStatus.REJECTED, reward=0.99), ReasonCode.INELIGIBLE_STATUS),
        (dict(reward_source=RewardSource.AGENT_CLAIM), ReasonCode.UNTRUSTED_REWARD_SOURCE),
    ],
)
@pytest.mark.parametrize("make", [lambda: LinUCBPolicy(), lambda: UCB1Policy(),
                                   lambda: ContextualEpsilonGreedyPolicy(), lambda: FixedTopologyPolicy(D)])
def test_protected_policies_refuse_ineligible(make, overrides: dict, reason: ReasonCode) -> None:  # type: ignore[no-untyped-def]
    policy = make()
    before = json.dumps(policy.snapshot(), sort_keys=True)
    with pytest.raises(IneligibleLearningEvent) as exc:
        policy.observe(_event(**overrides))
    assert exc.value.reason is reason
    after = policy.snapshot()
    after_json = json.dumps(after, sort_keys=True)
    assert before == after_json  # state byte-identical
    assert policy.gate.rejected_attempts == [("le0", reason)]


def test_duplicate_episode_raises_and_does_not_double_count() -> None:
    p = LinUCBPolicy()
    p.observe(_event(0))
    A_before = p.A[D].copy()
    with pytest.raises(IneligibleLearningEvent) as exc:
        p.observe(_event(0).model_copy(update={"event_id": "le-replay"}))
    assert exc.value.reason is ReasonCode.DUPLICATE_EPISODE
    np.testing.assert_array_equal(p.A[D], A_before)
    assert p.updates[D] == 1


def test_vulnerable_learns_from_claimed_reward_protected_does_not() -> None:
    protected = LinUCBPolicy(seed=1)
    vulnerable = VulnerableLinUCB.from_snapshot(protected.snapshot())
    poison = _event(reward=1.0, reward_source=RewardSource.AGENT_CLAIM, status=EpisodeStatus.REJECTED)
    vulnerable.observe(poison)
    with pytest.raises(IneligibleLearningEvent):
        protected.observe(poison)
    assert not np.array_equal(vulnerable.A[D], protected.A[D])
    assert protected.A[D].tobytes() == (np.eye(5)).tobytes()
    assert protected.b[D].tobytes() == np.zeros(5).tobytes()


def test_snapshot_roundtrip_is_exact_and_json_safe() -> None:
    p = LinUCBPolicy(seed=4, alpha=0.7)
    for i in range(4):
        d = p.select(X, ALL, "ctx-v1")
        assert d.topology
        p.observe(_event(i, topology=d.topology, reward=0.1 * i))
    state = json.loads(json.dumps(p.snapshot()))
    q = LinUCBPolicy.from_snapshot(state)
    for arm in ARM_ORDER:
        assert q.A[arm].tobytes() == p.A[arm].tobytes()
        assert q.b[arm].tobytes() == p.b[arm].tobytes()
    assert q.select(X, ALL, "ctx-v1") == p.clone().select(X, ALL, "ctx-v1")


def test_ucb1_tries_each_arm_then_exploits() -> None:
    p = UCB1Policy(c=0.0)
    picks = []
    for i in range(5):
        d = p.select(X, ALL, "ctx-v1")
        assert d.topology
        picks.append(d.topology)
        p.observe(_event(i, topology=d.topology, reward=0.9 if d.topology is H else 0.2))
    assert picks[:3] == list(ARM_ORDER)
    assert picks[3:] == [H, H]


def test_epsilon_greedy_warmup_then_greedy_at_zero_epsilon() -> None:
    def run() -> list[TopologyName]:
        p = ContextualEpsilonGreedyPolicy(seed=5, epsilon=0.0, warmup_per_arm=1)
        picks = []
        for i in range(6):
            d = p.select(X, ALL, "ctx-v1")
            assert d.topology is not None
            picks.append(d.topology)
            p.observe(_event(i, topology=d.topology, reward=0.95 if d.topology is F else 0.1))
        return picks

    picks = run()
    assert set(picks[:3]) == set(ALL)
    assert picks[3:] == [F, F, F]
    assert run() == picks


def test_epsilon_greedy_samples_only_eligible_arms_and_replays_rng_state() -> None:
    p = ContextualEpsilonGreedyPolicy(seed=37, epsilon=1.0, warmup_per_arm=0)
    choices = [p.select(X, [H, F], "ctx-v1") for _ in range(30)]
    assert {d.topology for d in choices} == {H, F}
    assert all(d.explored and d.exploration_probability == 1.0 for d in choices)
    clone = ContextualEpsilonGreedyPolicy.from_snapshot(json.loads(json.dumps(p.snapshot())))
    assert [p.select(X, [H, F], "ctx-v1") for _ in range(20)] == [
        clone.select(X, [H, F], "ctx-v1") for _ in range(20)
    ]


def test_epsilon_greedy_handles_empty_eligibility_and_bad_context() -> None:
    p = ContextualEpsilonGreedyPolicy(seed=1, warmup_per_arm=0)
    none = p.select(X, [], "ctx-v1")
    assert none.topology is None and none.reason_codes == (ReasonCode.NO_ELIGIBLE_TOPOLOGY,)
    with pytest.raises(ValueError, match="CONTEXT_SCHEMA_MISMATCH"):
        p.select(X, [H], "ctx-v2")
    with pytest.raises(ValueError, match="CONTEXT_SCHEMA_MISMATCH"):
        p.select(X[:3], [H], "ctx-v1")


def test_fixed_policy_does_not_substitute() -> None:
    d = FixedTopologyPolicy(H).select(X, [F, D], "ctx-v1")
    assert d.topology is None and d.reason_codes == (ReasonCode.TOPOLOGY_NOT_ELIGIBLE,)
    assert FixedTopologyPolicy(H).select(X, ALL, "ctx-v1").topology is H


def test_best_fixed_and_factory() -> None:
    assert best_fixed_from_training({H: [0.2, 0.4], F: [0.5], D: [0.5, 0.5]}) is D
    assert make_policy("P0-F").select(X, ALL, "ctx-v1").topology is F
    assert make_policy("P1", {"topology": "HIERARCHICAL"}).kind == "P1-BestFixed"
    assert isinstance(make_policy("P2"), UCB1Policy)
    p4 = make_policy("P4", {"epsilon": 0.25}, seed=13)
    assert isinstance(p4, ContextualEpsilonGreedyPolicy)
    assert p4.epsilon == 0.25 and p4.seed == 13
    p3 = make_policy("P3", {"alpha": 0.5}, seed=9)
    assert type(p3) is LinUCBPolicy and p3.alpha == 0.5 and p3.seed == 9  # type: ignore[attr-defined]
    assert isinstance(make_policy("S1"), VulnerableLinUCB)
    with pytest.raises(ValueError):
        make_policy("P9")
