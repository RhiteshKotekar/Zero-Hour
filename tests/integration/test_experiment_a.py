"""Experiment A/B over the real pipeline (allocator + simulator + witness + ACP) on a tiny config."""

from __future__ import annotations

import pytest

from samg.domain import EpisodeStatus
from samg.evaluation.executor import OrchestrationExecutor
from samg.evaluation.runner import PERFORMANCE_POLICIES, ExperimentConfig, build_splits, run_experiment_a

TINY = ExperimentConfig(n_dev=1, n_train=6, n_test=3, warmup_per_arm=1)


@pytest.fixture(scope="module")
def run():
    executor = OrchestrationExecutor()
    return executor, run_experiment_a(TINY, executor, costs=executor.settings.costs)


def test_executor_reuses_one_solve_per_scenario(run) -> None:
    executor, _ = run
    splits = build_splits(TINY)
    assert executor.calls["allocation"] == len(splits["train"]) + len(splits["test"])
    assert executor.calls["execution"] > executor.calls["allocation"]


def test_real_pipeline_reports_every_policy_with_ground_truth(run) -> None:
    _, result = run
    assert set(result.test) == set(PERFORMANCE_POLICIES)
    for name in PERFORMANCE_POLICIES:
        r = result.test[name]
        assert r.reward.n + r.not_applicable + r.infeasible == TINY.n_test
        assert {"C", "T", "R", "H", "makespan_ms", "coordination_cost"} <= set(r.metric_means)


def test_learning_only_from_admitted_and_ground_truth_kept_separate(run) -> None:
    _, result = run
    learned = [r for r in result.records if r.learned]
    assert learned and all(r.split == "train" and r.policy in {"P2", "P3"} for r in learned)
    assert all(r.episode_status is EpisodeStatus.ADMITTED for r in learned)
    # Faithful witness: the ACP-recomputed reward equals simulator ground truth (D033).
    for r in learned:
        assert r.admitted_reward == pytest.approx(r.reward)
    assert sum(result.learner_updates.values()) == len(learned)


def test_real_run_is_deterministic(run) -> None:
    _, first = run
    executor = OrchestrationExecutor()
    second = run_experiment_a(TINY, executor, costs=executor.settings.costs)
    assert [r.reward for r in first.records] == [r.reward for r in second.records]
    assert [r.topology for r in first.records] == [r.topology for r in second.records]
