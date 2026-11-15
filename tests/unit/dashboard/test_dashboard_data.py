"""Dashboard data helpers return values consistent with the orchestration records they reshape."""

from __future__ import annotations

import pytest

from samg.dashboard import data
from samg.domain import EpisodeStatus, TopologyName


@pytest.fixture(scope="module")
def judge_run() -> data.MissionRun:
    return data.run_mission(seed=7, scenario_kind="judge", factors=None, policy="linucb", mode="adaptive",
                            alpha=0.3, use_cpsat=False)


def test_run_mission_identifies_the_run(judge_run: data.MissionRun) -> None:
    rec = judge_run.record
    assert rec.seed == 7
    assert rec.mission_id == judge_run.scenario.mission.mission_id
    assert judge_run.config_id == data.config_id(judge_run.settings)
    assert len(judge_run.config_id) == 16


def test_rows_mirror_the_record(judge_run: data.MissionRun) -> None:
    rec = judge_run.record
    scores = data.score_rows(rec)
    assert [r["topology"] for r in scores] == [t.value for t in data.ARM_ORDER]
    assert sum(r["selected"] for r in scores) == 1
    for r in scores:
        if r["offered"]:
            assert r["score"] == rec.decision.scores[TopologyName(r["topology"])]
    elig = data.eligibility_rows(rec)
    assert {r["topology"] for r in elig if r["eligible"]} == {t.value for t in rec.decision.eligible}
    assert len(data.assignment_rows(rec, judge_run.scenario)) == len(rec.plan.assignments)
    hand = data.handoff_rows(rec)
    assert sum(h["cost"] for h in hand) == pytest.approx(sum(h.cost for h in rec.plan.handoffs))
    assert len(data.event_rows(rec)) == len(rec.witness_events) + len(rec.agent_events)


def test_reward_rows_sum_to_acp_reward(judge_run: data.MissionRun) -> None:
    rec = judge_run.record
    assert rec.episode is not None and rec.episode.status is EpisodeStatus.ADMITTED
    rows = data.reward_rows(rec)
    assert {r["term"] for r in rows} == set(rec.acp_reward.weights)
    for r in rows:
        assert r["contribution"] == rec.acp_reward.contributions[r["term"]]
    assert rec.learning_applied


def test_fixed_mode_uses_fixed_policy() -> None:
    run = data.run_mission(seed=7, scenario_kind="judge", factors=None, policy="fixed", mode="fixed", alpha=0.3,
                           use_cpsat=False, fixed_topology=TopologyName.DISTRIBUTED)
    assert run.record.decision.topology in (TopologyName.DISTRIBUTED, None)
    assert "b" not in run.policy_after


def test_generated_scenario_with_factors() -> None:
    factors = {k: v[0] for k, v in data.FACTOR_CHOICES.items()}
    run = data.run_mission(seed=11, scenario_kind="generated", factors=factors, policy="ucb1", mode="adaptive",
                           alpha=0.3, use_cpsat=False)
    assert run.record.seed == 11


def test_topology_comparison_matches_eligibility(judge_run: data.MissionRun) -> None:
    cmp = data.compare_topologies(judge_run.scenario, 7, judge_run.settings)
    assert set(cmp.executions) == set(judge_run.record.decision.eligible)
    rows = data.comparison_rows(cmp)
    assert len(rows) == 3
    chosen = judge_run.record.decision.topology
    ex = cmp.executions[chosen]
    # same scenario/seed/topology through execute_mission gives the same ground truth as the live run
    assert ex.ground_truth_reward.reward == pytest.approx(judge_run.record.ground_truth_reward.reward)


def test_attack_comparison_small() -> None:
    run = data.run_attack_comparison(n_pre=3, n_attack=2)
    assert len(run.window) == 2
    summary = data.attack_summary(run, data.load_settings(False).security.witness.identity_id)
    assert summary["false claims corroborated (S2 ACP)"] == 0
    for r2, r1 in run.window:
        if r2.learning_applied:
            assert r2.learning_event.reward_source.value == "ACP_RECOMPUTED"
        assert r1.mode.value == "VULNERABLE"
    assert len(data.window_rows(run)) == 2
    assert {d["arm"] for d in run.divergence} == {t.value for t in TopologyName}


def test_saved_files_absent_is_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(data, "ARTIFACTS", tmp_path / "nope")
    assert data.saved_files("experiment_a*.json") == []
