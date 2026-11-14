"""Simulator engine and reward (integration versions of Dev A's Phase 2 modules)."""

from __future__ import annotations

import pytest

from samg.allocation import allocate
from samg.assurance.state_machine import Actor, transition_allowed
from samg.domain import (
    GroundTruthMetrics,
    RewardConfig,
    TaskState,
    TopologyCostConfig,
    TopologyName,
)
from samg.simulation import compute_reward, run
from samg.simulation.scenarios import judge_scenario
from samg.topology import build_graph

COSTS = TopologyCostConfig()


def _plan(topology: TopologyName = TopologyName.HIERARCHICAL):
    scenario = judge_scenario(7)
    _, graph = build_graph(scenario, topology, COSTS)
    return scenario, graph, allocate(scenario, graph, COSTS)


def test_same_seed_same_trace_and_different_seed_differs() -> None:
    scenario, graph, plan = _plan()
    a, b = run(scenario, graph, plan, 7, COSTS), run(scenario, graph, plan, 7, COSTS)
    assert a == b
    assert run(scenario, graph, plan, 8, COSTS).transitions != a.transitions


def test_clean_run_completes_every_task_in_legal_order() -> None:
    scenario, graph, plan = _plan()
    trace = run(scenario, graph, plan, 7, COSTS)
    assert all(o.completed for o in trace.outcomes)
    assert trace.metrics.weighted_completion == 1.0 and trace.metrics.mandatory_completed
    state = {t.task_id: TaskState.OPEN for t in scenario.mission.tasks}
    for tr in trace.transitions:
        assert tr.from_state is state[tr.task_id]
        # the witness signs REPORTED_COMPLETE as VERIFIED_COMPLETE (only it may verify)
        to = TaskState.VERIFIED_COMPLETE if tr.to_state is TaskState.REPORTED_COMPLETE else tr.to_state
        assert transition_allowed(tr.from_state, to, Actor.WITNESS)
        state[tr.task_id] = tr.to_state
    by_task = {o.task_id: o for o in trace.outcomes}
    for prereq, dependent in scenario.mission.dependency_edges():
        assert by_task[dependent].start >= by_task[prereq].end


def test_handoff_delay_follows_graph_path() -> None:
    scenario, graph, plan = _plan()
    trace = run(scenario, graph, plan, 7, COSTS.model_copy(update={"hop_failure_probability": 0.0}))
    by_task = {o.task_id: o for o in trace.outcomes}
    for h in plan.handoffs:
        assert by_task[h.dependent_task].start >= by_task[h.prerequisite_task].end + h.delay - 1e-9


def test_forced_failure_blocks_dependents_and_lowers_completion() -> None:
    scenario, graph, plan = _plan()
    trace = run(scenario, graph, plan, 7, COSTS, forced_failures={"T6"})
    outcome = {o.task_id: o for o in trace.outcomes}
    assert not outcome["T6"].completed and outcome["T6"].failure_reason == "TASK_FAILED"
    assert outcome["T7"].failure_reason.startswith("UPSTREAM_FAILED") and outcome["T7"].start is None
    final = {}
    for tr in trace.transitions:
        final[tr.task_id] = tr.to_state
    assert final["T6"] is TaskState.FAILED and final["T8"] is TaskState.FAILED
    assert trace.metrics.weighted_completion == pytest.approx(5.5 / 10.5)


def test_infeasible_plan_cannot_run_and_gets_failure_outcome() -> None:
    scenario, graph, plan = _plan()
    bad = plan.model_copy(update={"feasible": False, "reason_codes": ("SOLVER_INFEASIBLE",), "assignments": ()})
    with pytest.raises(ValueError):
        run(scenario, graph, bad, 7, COSTS)
    rb = compute_reward(None, RewardConfig())
    assert rb.failure_outcome and rb.reward == 0.0 and rb.failure_label == "INVALID_PLAN"


def test_reward_formula_matches_brief() -> None:
    m = GroundTruthMetrics(weighted_completion=0.8, makespan=1.0, duration_norm=0.5, resource_used=1.0,
                           resource_norm=0.25, coordination_cost=1.0, coordination_norm=0.4,
                           mandatory_completed=False)
    rb = compute_reward(m, RewardConfig())
    expected = 0.65 * 0.8 + 0.15 * 0.5 + 0.10 * 0.75 + 0.10 * 0.6
    assert rb.reward == pytest.approx(expected)
    assert sum(rb.contributions.values()) == pytest.approx(expected)
    best = m.model_copy(update={"weighted_completion": 1.0, "duration_norm": 0.0, "resource_norm": 0.0,
                                "coordination_norm": 0.0})
    worst = m.model_copy(update={"weighted_completion": 0.0, "duration_norm": 1.0, "resource_norm": 1.0,
                                 "coordination_norm": 1.0})
    assert compute_reward(best, RewardConfig()).reward == pytest.approx(1.0)
    assert compute_reward(worst, RewardConfig()).reward == pytest.approx(0.0)


def test_topology_changes_coordination_overhead() -> None:
    values = {}
    for topo in TopologyName:
        scenario, graph, plan = _plan(topo)
        values[topo] = run(scenario, graph, plan, 7, COSTS).metrics.coordination_cost
    assert len(set(values.values())) > 1
