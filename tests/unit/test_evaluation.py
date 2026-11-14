"""Unit tests for the Experiment A/B runner and metrics (Dev A).

A synthetic executor stands in for simulator + ACP: its reward depends on the
mission context and topology, so the protocol (splits, P1 selection on training
only, gated online learning, frozen test, paired comparisons, regret) can be
checked without the full pipeline.
"""

from __future__ import annotations

import pytest

from samg.context import extract_features
from samg.domain import EpisodeRecord, EpisodeStatus, ReasonCode, Scenario, TopologyName
from samg.evaluation.metrics import bootstrap_ci, oracle_regret, paired_comparison, summarize
from samg.evaluation.runner import (
    PERFORMANCE_POLICIES,
    ExperimentConfig,
    MissionResult,
    build_splits,
    load_experiment,
    run_experiment_a,
)

SMALL = ExperimentConfig(n_dev=2, n_train=24, n_test=8, warmup_per_arm=1)


class SyntheticExecutor:
    """Deterministic context-dependent rewards; every 5th call is PROVISIONAL (no learning)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, TopologyName, str]] = []

    @staticmethod
    def reward_table(scenario: Scenario) -> dict[TopologyName, float]:
        f = extract_features(scenario).as_dict()
        return {
            TopologyName.DISTRIBUTED: 0.2 + 1.5 * f["dependency_density"],
            TopologyName.HIERARCHICAL: 1.2 - f["capability_heterogeneity"],
            TopologyName.FUNCTIONAL_CELL: 0.5,
        }

    def execute(self, scenario: Scenario, topology: TopologyName, *, seed: int, decision_id: str) -> MissionResult:
        self.calls.append((scenario.scenario_id, topology, decision_id))
        base = self.reward_table(scenario)[topology]
        reward = max(0.0, min(1.0, base + 0.01 * (seed % 3)))
        provisional = len(self.calls) % 5 == 0
        episode = EpisodeRecord(
            episode_id=f"ep-{decision_id}", mission_id=scenario.mission.mission_id, epoch=0,
            topology_decision_id=decision_id, topology=topology, plan_id="plan-x",
            status=EpisodeStatus.PROVISIONAL if provisional else EpisodeStatus.ADMITTED,
            reward=None if provisional else reward,
            reward_schema_version=None if provisional else "reward-v1",
            reason_codes=(ReasonCode.REWARD_CRITICAL_UNVERIFIED,) if provisional else (),
        )
        return MissionResult(feasible=True, ground_truth_reward=reward, episode=episode)


@pytest.fixture(scope="module")
def result():
    return run_experiment_a(SMALL, SyntheticExecutor())


def test_committed_experiment_yaml_equals_defaults() -> None:
    assert load_experiment() == ExperimentConfig()


def test_splits_are_disjoint_and_hold_out_combos_only_at_test() -> None:
    splits = build_splits(SMALL)
    ids = {k: {s.scenario_id for s, _ in v} for k, v in splits.items()}
    assert not (ids["dev"] & ids["train"] or ids["dev"] & ids["test"] or ids["train"] & ids["test"])
    assert not any(h for _, h in splits["train"] + splits["dev"])
    assert build_splits(SMALL)["test"][0][0] == splits["test"][0][0]


def test_every_policy_reported_including_weak_baselines(result) -> None:
    assert set(result.test) == set(PERFORMANCE_POLICIES)
    assert all(result.test[p].reward.n + result.test[p].not_applicable + result.test[p].infeasible == SMALL.n_test
               for p in PERFORMANCE_POLICIES)


def test_p1_is_chosen_from_training_only(result) -> None:
    train_means = {}
    for name, topology in (("P0-H", TopologyName.HIERARCHICAL), ("P0-F", TopologyName.FUNCTIONAL_CELL),
                           ("P0-D", TopologyName.DISTRIBUTED)):
        vals = [v for v in result.training_rewards[name] if v is not None]
        train_means[topology] = sum(vals) / len(vals)
    assert result.p1_topology == max(train_means, key=train_means.get)
    assert result.test["P1"].selection_counts == {result.p1_topology.value: result.test["P1"].reward.n}


def test_learners_update_only_from_admitted_and_never_at_test(result) -> None:
    assert result.learner_updates["P3"] > 0 and result.blocked_updates["P3"] > 0
    assert all(not r.learned for r in result.records if r.split == "test")
    assert all(not r.learned for r in result.records if r.policy.startswith("P0"))
    p3_train = [r for r in result.records if r.split == "train" and r.policy == "P3"]
    assert sum(r.learned for r in p3_train) == result.learner_updates["P3"]
    assert all(r.episode_status is EpisodeStatus.ADMITTED for r in p3_train if r.learned)


def test_linucb_adapts_to_context(result) -> None:
    """The synthetic best arm varies with context; LinUCB should follow it and beat the best fixed arm."""
    best_arms = {max(SyntheticExecutor.reward_table(s).items(), key=lambda kv: kv[1])[0]
                 for s, _ in build_splits(SMALL)["test"]}
    assert len(best_arms) >= 2, "synthetic test set must have context-dependent optima"
    assert len(result.test["P3"].selection_counts) >= 2
    assert result.test["P3"].reward.mean >= result.test["P1"].reward.mean
    assert result.test["P3"].regret.mean <= result.test["P1"].regret.mean


def test_comparisons_and_regret_are_paired(result) -> None:
    names = {(c.a, c.b) for c in result.comparisons}
    assert names == {("P3", "P1"), ("P3", "P2"), ("P2", "P1")}
    for c in result.comparisons:
        assert c.wins + c.losses + c.ties == c.n_pairs
    assert all(result.test[p].regret.mean is None or result.test[p].regret.mean >= 0 for p in PERFORMANCE_POLICIES)


def test_run_is_deterministic() -> None:
    a = run_experiment_a(SMALL, SyntheticExecutor())
    b = run_experiment_a(SMALL, SyntheticExecutor())
    assert a.model_dump() == b.model_dump()


def test_config_hash_changes_with_config() -> None:
    a = run_experiment_a(SMALL, SyntheticExecutor())
    b = run_experiment_a(SMALL.model_copy(update={"alpha": 0.9}), SyntheticExecutor())
    assert a.config_hash != b.config_hash


def test_summary_and_ci() -> None:
    s = summarize([1.0, 2.0, 3.0, 4.0], seed=0)
    assert s.n == 4 and s.mean == 2.5 and s.median == 2.5
    assert s.ci95_low <= 2.5 <= s.ci95_high
    assert summarize([], seed=0).mean is None
    assert bootstrap_ci([1.0], seed=0) == (None, None)
    assert bootstrap_ci([1.0, 2.0, 3.0], seed=1) == bootstrap_ci([1.0, 2.0, 3.0], seed=1)


def test_paired_comparison_and_regret() -> None:
    c = paired_comparison("a", {"m1": 0.5, "m2": 0.7, "m3": 0.4}, "b", {"m1": 0.4, "m2": 0.7, "m4": 0.9}, seed=0)
    assert c.n_pairs == 2 and c.wins == 1 and c.ties == 1 and c.mean_diff == pytest.approx(0.05)
    assert oracle_regret({"m1": 0.5}, {"m1": {"H": 0.5, "D": 0.8}}) == {"m1": pytest.approx(0.3)}
