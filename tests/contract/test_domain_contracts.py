"""Contract tests for Dev A's domain models and configs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from samg.domain import (
    AgentProfile,
    AllocationConfig,
    AllocationFailure,
    AllocationPlan,
    CapabilityMatch,
    IneligibilityReason,
    MissionSpec,
    RewardConfig,
    SolverName,
    TaskSpec,
    TopologyCostConfig,
    TopologyEligibility,
    TopologyName,
    config_hash,
    load_allocation,
    load_reward,
    load_topology_costs,
)
from samg.simulation.scenarios import judge_scenario


def _task(tid: str, deps: list[str] | None = None) -> TaskSpec:
    return TaskSpec(task_id=tid, required_capabilities=["x"], duration=1, resource_demand=0, dependencies=deps or [])


def _mission(tasks: list[TaskSpec]) -> MissionSpec:
    return MissionSpec(mission_id="m", scenario_id="s", tasks=tasks, deadline=10)


def test_enum_values_are_stable() -> None:
    assert [t.value for t in TopologyName] == ["distributed", "functional_cell", "hierarchical"]


def test_models_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        TaskSpec(task_id="t", required_capabilities=["x"], duration=1, resource_demand=0, colour="red")


def test_models_are_immutable() -> None:
    task = _task("t")
    with pytest.raises(ValidationError):
        task.duration = 5  # type: ignore[misc]


def test_capabilities_are_sorted_and_deduplicated() -> None:
    task = TaskSpec(task_id="t", required_capabilities=["b", "a", "b"], duration=1, resource_demand=0)
    assert task.required_capabilities == ("a", "b")


def test_self_dependency_rejected() -> None:
    with pytest.raises(ValidationError):
        _task("t", ["t"])


def test_unknown_dependency_rejected() -> None:
    with pytest.raises(ValidationError):
        _mission([_task("a", ["zzz"])])


def test_cycle_rejected() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        _mission([_task("a", ["b"]), _task("b", ["a"])])


def test_duplicate_task_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        _mission([_task("a"), _task("a")])


def test_topological_order_and_depth_are_deterministic() -> None:
    mission = _mission([_task("c", ["a", "b"]), _task("b"), _task("a"), _task("d", ["c"])])
    assert mission.topological_order() == ["a", "b", "c", "d"]
    assert mission.depth() == {"a": 0, "b": 0, "c": 1, "d": 2}
    assert mission.dependency_edges() == [("a", "c"), ("b", "c"), ("c", "d")]


def test_capability_matching_any_and_all() -> None:
    agent = AgentProfile(agent_id="x", role="r", capabilities=["a"], max_tasks=1, resource_budget=1, public_key_id="k")
    any_task = TaskSpec(task_id="t", required_capabilities=["a", "b"], capability_match=CapabilityMatch.ANY,
                        duration=1, resource_demand=0)
    all_task = TaskSpec(task_id="u", required_capabilities=["a", "b"], duration=1, resource_demand=0)
    assert any_task.is_capable(agent)
    assert not all_task.is_capable(agent)


def test_judge_scenario_matches_brief() -> None:
    scenario = judge_scenario()
    assert [a.agent_id for a in scenario.agents] == ["A0", "A1", "A2", "A3", "A4", "A5"]
    mission = scenario.mission
    assert mission.topological_order() == [f"T{i}" for i in range(1, 9)]
    assert len(mission.dependency_edges()) == 7
    # every task has at least one capable, available agent
    for task in mission.tasks:
        assert any(task.is_capable(a) for a in scenario.available_agents()), task.task_id


def test_judge_scenario_round_trips_through_json() -> None:
    scenario = judge_scenario()
    assert type(scenario).model_validate_json(scenario.model_dump_json()) == scenario


def test_eligibility_reasons_iff_ineligible() -> None:
    TopologyEligibility(topology=TopologyName.HIERARCHICAL, eligible=True)
    TopologyEligibility(topology=TopologyName.HIERARCHICAL, eligible=False,
                        reasons=[IneligibilityReason.NO_COORDINATOR])
    with pytest.raises(ValidationError):
        TopologyEligibility(topology=TopologyName.HIERARCHICAL, eligible=False)


def test_infeasible_plan_needs_reason_codes() -> None:
    base = dict(plan_id="p", mission_id="m", topology=TopologyName.DISTRIBUTED, graph_version="g",
                solver=SolverName.GREEDY)
    AllocationPlan(**base, feasible=False, reason_codes=[AllocationFailure.NO_CAPABLE_AGENT])
    with pytest.raises(ValidationError):
        AllocationPlan(**base, feasible=False)
    with pytest.raises(ValidationError):
        AllocationPlan(**base, feasible=True)  # no objective terms


def test_committed_yaml_equals_model_defaults() -> None:
    assert load_topology_costs() == TopologyCostConfig()
    assert load_allocation() == AllocationConfig()
    assert load_reward() == RewardConfig()


def test_handoff_cost_rule() -> None:
    costs = TopologyCostConfig()
    assert costs.handoff_cost(0) == 0
    assert costs.handoff_cost(2) == pytest.approx(costs.h0 + 2 * costs.h1)
    high = costs.with_setting("high")
    assert (high.h0, high.h1) == (2.0, 1.0)


def test_reward_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        RewardConfig(weights={"completion": 0.5, "duration": 0.1, "resources": 0.1, "coordination": 0.1})


def test_config_hash_is_stable_and_sensitive() -> None:
    assert config_hash(RewardConfig()) == config_hash(RewardConfig())
    assert config_hash(TopologyCostConfig()) != config_hash(TopologyCostConfig(h1=0.6))
