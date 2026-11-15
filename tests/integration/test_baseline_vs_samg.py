"""Conventional baseline vs SAMG on the warehouse twin (D042): the brief's validation tests 1-6.

Test 7 (existing SAMG tests still pass) is the rest of the suite.
"""

from __future__ import annotations

import pytest

from samg.baseline import BASELINE_KIND, run_metrics, run_mode
from samg.domain import TopologyName
from samg.domain.config import SimulationModelConfig
from samg.twin import Injection, RunSpec, preset
from samg.twin.layout import load_config

CFG = load_config()


@pytest.fixture(scope="module")
def judge_runs():
    spec = preset(CFG, "judge_demo")  # robot failure + malicious report
    return {mode: run_mode(spec, mode, CFG) for mode in ("samg", "baseline")}


@pytest.fixture(scope="module")
def judge_metrics(judge_runs):
    return {mode: run_metrics(run) for mode, run in judge_runs.items()}


def test_1_identical_initial_state(judge_runs) -> None:
    samg, base = judge_runs["samg"], judge_runs["baseline"]
    assert samg.initial_states == base.initial_states
    assert samg.tasks == base.tasks and samg.orders == base.orders and samg.holds == base.holds
    assert samg.env.robots == base.env.robots
    assert repr(samg.env.layout) == repr(base.env.layout)


def test_2_both_modes_execute_normal_scenario() -> None:
    spec = preset(CFG, "clean")
    for mode in ("samg", "baseline"):
        k = run_metrics(run_mode(spec, mode, CFG))
        assert k["tasks_truly_completed"] > 0 and k["mode"] == mode


def test_3_physical_environment_identical_under_congestion() -> None:
    aisle = CFG["scenarios"].get("rush", {}).get("injections", [{}])
    blocked = next((i["aisle"] for i in aisle if i.get("kind") == "aisle_blockage"), None)
    injections = (Injection("aisle_blockage", aisle=blocked),) if blocked else ()
    spec = RunSpec(seed=11, injections=injections, scenario="custom")
    samg, base = (run_mode(spec, m, CFG) for m in ("samg", "baseline"))
    assert repr(samg.env.layout) == repr(base.env.layout)
    assert samg.env.inventory._skus == base.env.inventory._skus  # same stock, same pick faces


def test_4_robot_failure_handled_independently(judge_runs) -> None:
    base = judge_runs["baseline"]
    # the baseline never switches topology: every wave uses the fixed controller star
    assert {w.record.decision.topology for w in base.waves} == {TopologyName.HIERARCHICAL}
    assert all(w.record.policy_kind == BASELINE_KIND for w in base.waves)
    for run in judge_runs.values():
        failed = set().union(*(w.failing_robots for w in run.waves))
        if failed and len(run.waves) > 1:
            assert failed <= run.waves[-1].excluded_robots  # broken robots are not re-dispatched


def test_5_false_completion_accepted_by_baseline_rejected_by_samg(judge_metrics) -> None:
    base, samg = judge_metrics["baseline"], judge_metrics["samg"]
    assert base["false_claims"] > 0 and samg["false_claims"] > 0
    assert base["false_claims_accepted"] == base["false_claims"] and base["false_claims_rejected"] == 0
    assert samg["false_claims_accepted"] == 0 and samg["false_claims_rejected"] == samg["false_claims"]
    assert base["corrupted_tasks"] >= 1 and samg["corrupted_tasks"] == 0
    assert base["orders_truly_fulfilled"] <= samg["orders_truly_fulfilled"]


@pytest.mark.parametrize("sim", [None, SimulationModelConfig()], ids=["v1", "v2-crn"])
def test_6_no_hidden_randomness(sim) -> None:
    spec = preset(CFG, "judge_demo")
    a = run_metrics(run_mode(spec, "baseline", CFG, sim))
    b = run_metrics(run_mode(spec, "baseline", CFG, sim))
    assert a == b


def test_baseline_never_uses_samg_mechanisms(monkeypatch) -> None:
    def forbidden(*_a, **_k):
        raise AssertionError("baseline must not call this SAMG mechanism")

    import samg.allocation.cpsat as cpsat
    import samg.assurance.admission as admission
    from samg.learning import LinUCBPolicy, UCB1Policy

    monkeypatch.setattr(LinUCBPolicy, "select", forbidden)
    monkeypatch.setattr(UCB1Policy, "select", forbidden)
    monkeypatch.setattr(cpsat, "allocate_cpsat", forbidden)
    monkeypatch.setattr(admission, "admit_episode", forbidden)
    monkeypatch.setattr(admission, "corroborate", forbidden)
    k = run_metrics(run_mode(preset(CFG, "judge_demo"), "baseline", CFG))
    assert k["coordination"] == "CENTRALIZED GREEDY"
