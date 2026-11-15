"""Mission model v2 (D041): opt-in rules, and proof that v1 is unchanged when they are off."""

from __future__ import annotations

import pytest

from samg.allocation import feasible_topologies
from samg.domain import TaskState, TopologyCostConfig, TopologyName, config_hash
from samg.domain.config import SimulationModelConfig
from samg.simulation import run as simulate
from samg.simulation.reward import compute_metrics
from samg.simulation.scenarios import (
    GENERATOR_VERSION,
    V2_DEADLINE_FACTOR,
    generate_scenario,
    judge_scenario,
)

V1 = TopologyCostConfig()


def _hierarchical(costs: TopologyCostConfig = V1):
    scenario = judge_scenario()
    _, _, plans = feasible_topologies(scenario, costs)
    graph, plan = plans[TopologyName.HIERARCHICAL]
    return scenario, graph, plan


def test_v1_is_the_default_and_keeps_frozen_hashes() -> None:
    assert V1.simulation_model is None
    assert config_hash(V1) == config_hash(V1.model_copy(update={"simulation_model": None}))
    assert config_hash(V1) != config_hash(V1.with_model_v2())


def test_neutral_v2_reproduces_v1_trace_exactly() -> None:
    """v2 machinery with every rule neutralised must equal v1 bit for bit (same draws, same order)."""
    scenario, graph, plan = _hierarchical()
    neutral = V1.model_copy(update={"simulation_model": SimulationModelConfig(
        handoff_max_attempts=3, enforce_deadline=False, relay_queue=False, keyed_randomness=False)})
    for seed in (0, 1, 2):
        assert simulate(scenario, graph, plan, seed, V1) == simulate(scenario, graph, plan, seed, neutral)


def test_lost_handoff_fails_the_task_and_blocks_downstream() -> None:
    scenario, graph, plan = _hierarchical()
    lossy = V1.with_model_v2(hop_failure_probability=0.999)
    trace = simulate(scenario, graph, plan, 0, lossy)
    outcomes = {o.task_id: o for o in trace.outcomes}
    cross = [h for h in plan.handoffs if h.hops > 0]
    assert cross, "the judge plan under hierarchical has cross-agent handoffs"
    first_lost = min(cross, key=lambda h: plan.assignments[[a.task_id for a in plan.assignments].index(h.dependent_task)].start)
    assert not outcomes[first_lost.dependent_task].completed
    assert outcomes[first_lost.dependent_task].failure_reason.startswith("MESSAGE_LOST")
    finals = {}
    for tr in trace.transitions:
        finals[tr.task_id] = tr.to_state
    assert finals[first_lost.dependent_task] is TaskState.FAILED  # terminal, so the ACP can admit it
    assert trace.metrics.weighted_completion < 1.0
    assert trace.metrics.communication_failures > 0


def test_relay_queue_only_ever_delays() -> None:
    scenario, graph, plan = _hierarchical()
    no_queue = V1.with_model_v2(SimulationModelConfig(relay_queue=False, enforce_deadline=False),
                                hop_failure_probability=0.0)
    queue = V1.with_model_v2(SimulationModelConfig(relay_queue=True, enforce_deadline=False),
                             hop_failure_probability=0.0)
    for seed in (0, 1, 2):
        a = simulate(scenario, graph, plan, seed, no_queue)
        b = simulate(scenario, graph, plan, seed, queue)
        ends_a = {o.task_id: o.end for o in a.outcomes}
        ends_b = {o.task_id: o.end for o in b.outcomes}
        assert all(ends_b[t] >= ends_a[t] for t in ends_a if ends_a[t] is not None)
        assert b.metrics.makespan >= a.metrics.makespan


def test_deadline_misses_do_not_count_as_completed() -> None:
    scenario, graph, plan = _hierarchical()
    trace = simulate(scenario, graph, plan, 0, V1)
    tight = scenario.model_copy(update={"mission": scenario.mission.model_copy(
        update={"deadline_ms": trace.metrics.makespan * 0.5})})
    enforce = V1.with_model_v2(hop_failure_probability=V1.hop_failure_probability)
    v1 = compute_metrics(tight, graph, plan, trace.outcomes, V1)
    v2 = compute_metrics(tight, graph, plan, trace.outcomes, enforce)
    assert v1.weighted_completion == pytest.approx(1.0)
    assert v2.weighted_completion < v1.weighted_completion


def test_generator_default_is_unchanged_and_v2_deadline_is_tagged() -> None:
    v1 = generate_scenario(5)
    v2 = generate_scenario(5, deadline_factor=V2_DEADLINE_FACTOR)
    assert v1.mission.generator_version == GENERATOR_VERSION
    assert "deadline_factor" not in v1.mission.generator_params
    assert v2.scenario_id != v1.scenario_id and v2.mission.mission_id != v1.mission.mission_id
    assert v2.mission.deadline_ms < v1.mission.deadline_ms
    assert v2.mission.tasks == v1.mission.tasks and v2.agents == v1.agents  # only the deadline differs


def test_keyed_randomness_gives_equal_luck_across_plans() -> None:
    """Common random numbers: a task's jitter does not depend on the rest of the plan."""
    scenario = judge_scenario()
    keyed = V1.model_copy(update={"simulation_model": SimulationModelConfig(
        handoff_max_attempts=3, enforce_deadline=False, relay_queue=False, keyed_randomness=True)})
    _, _, plans = feasible_topologies(scenario, keyed)
    durations = {}
    for topo, (graph, plan) in plans.items():
        trace = simulate(scenario, graph, plan, 3, keyed)
        planned = {a.task_id: a.end - a.start for a in plan.assignments}
        durations[topo] = {o.task_id: round((o.end - o.start) / planned[o.task_id], 6)
                           for o in trace.outcomes if o.completed and o.start is not None}
    first, *rest = durations.values()
    for other in rest:
        shared = set(first) & set(other)
        assert shared and all(abs(first[t] - other[t]) < 1e-5 for t in shared)  # same jitter (ms rounding)
