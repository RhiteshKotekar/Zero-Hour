"""Unit tests for CP-SAT and greedy allocation (Dev A)."""

from __future__ import annotations

import pytest

from samg.allocation import AllocationProblem, allocate, allocate_cpsat, allocate_greedy
from samg.domain import (
    AgentProfile,
    AllocationConfig,
    AllocationFailure,
    AllocationPlan,
    MissionSpec,
    Scenario,
    SolverName,
    TaskSpec,
    TopologyCostConfig,
    TopologyName,
)
from samg.simulation.scenarios import ScenarioFactors, factor_grid, generate_scenario, judge_scenario
from samg.topology import HopTable, build_graph, eligible_topologies

COSTS = TopologyCostConfig()
CONFIG = AllocationConfig()


def _problem(scenario: Scenario, topology: TopologyName) -> AllocationProblem:
    verdict, graph = build_graph(scenario, topology, COSTS)
    assert verdict.eligible, verdict
    return AllocationProblem(scenario, graph, COSTS, CONFIG)


def assert_plan_valid(problem: AllocationProblem, plan: AllocationPlan) -> None:
    """Every hard constraint, checked independently of the solver."""
    assert plan.feasible
    mission, scenario = problem.mission, problem.scenario
    by_task = {a.task_id: a for a in plan.assignments}
    for task in mission.tasks:
        if task.mandatory:
            assert task.task_id in by_task, f"mandatory {task.task_id} unassigned"
    per_agent: dict[str, list] = {}
    for a in plan.assignments:
        task, agent = mission.task(a.task_id), scenario.agent(a.agent_id)
        assert agent.available and task.is_capable(agent)
        assert a.end == pytest.approx(a.start + task.duration_ms)
        per_agent.setdefault(a.agent_id, []).append(a)
    for agent_id, items in per_agent.items():
        agent = scenario.agent(agent_id)
        assert len(items) <= agent.capacity
        assert sum(mission.task(a.task_id).resource_demand for a in items) <= agent.resource_budget + 1e-9
        items.sort(key=lambda a: a.start)
        for prev, nxt in zip(items, items[1:]):
            assert nxt.start >= prev.end - 1e-6, f"overlap on {agent_id}"
    table = HopTable(problem.graph, COSTS)
    for prereq, dependent in mission.dependency_edges():
        if dependent not in by_task:
            continue
        p, d = by_task[prereq], by_task[dependent]
        route = table.route(p.agent_id, d.agent_id)
        assert route is not None, f"no permitted path {p.agent_id}->{d.agent_id}"
        assert d.start >= p.end + route.delay - 1e-6
    explained = {(h.prerequisite_task, h.dependent_task): h for h in plan.handoffs}
    for prereq, dependent in mission.dependency_edges():
        if dependent in by_task:
            h = explained[(prereq, dependent)]
            assert h.cost == pytest.approx(COSTS.handoff_cost(h.hops))
            assert h.path[0] == h.from_agent and h.path[-1] == h.to_agent


@pytest.mark.parametrize("topology", list(TopologyName))
def test_both_allocators_produce_valid_plans_on_judge_mission(topology: TopologyName) -> None:
    problem = _problem(judge_scenario(), topology)
    cp, status = allocate_cpsat(problem)
    assert cp is not None and status == "OPTIMAL"
    assert_plan_valid(problem, cp)
    greedy = allocate_greedy(problem)
    assert_plan_valid(problem, greedy)
    assert cp.objective.weighted_total <= greedy.objective.weighted_total + 1e-6


@pytest.mark.parametrize("topology", list(TopologyName))
def test_allocators_are_deterministic(topology: TopologyName) -> None:
    problem = _problem(judge_scenario(), topology)
    for allocator in (lambda: allocate_greedy(problem), lambda: allocate_cpsat(problem)[0]):
        first, second = allocator(), allocator()
        assert first.plan_id == second.plan_id
        assert first.assignments == second.assignments
        assert first.objective == second.objective


def test_topology_changes_the_objective() -> None:
    """Brief §12.10: the graph must change the allocator objective, not just the picture."""
    scenario = judge_scenario()
    totals = {t: allocate(scenario, _problem(scenario, t).graph, COSTS, CONFIG).objective for t in TopologyName}
    assert len({round(o.weighted_total, 6) for o in totals.values()}) > 1
    assert len({o.handoff_cost for o in totals.values()}) > 1


def test_zero_handoff_cost_removes_the_topology_pathway() -> None:
    """§12.9 ablation: with h0 = h1 = 0 and no delay, handoff cost is zero under every topology."""
    flat = COSTS.model_copy(update={"h0": 0.0, "h1": 0.0, "handoff_delay_ms_per_hop": 0.0})
    scenario = judge_scenario()
    for t in TopologyName:
        _, graph = build_graph(scenario, t, flat)
        plan = allocate(scenario, graph, flat, CONFIG)
        assert plan.objective.handoff_cost == 0


def test_handoff_explanation_matches_validator_oracle() -> None:
    """Hierarchical: every cross-agent handoff goes worker -> A0 -> worker = 2 hops."""
    problem = _problem(judge_scenario(), TopologyName.HIERARCHICAL)
    plan = allocate_greedy(problem)
    for h in plan.handoffs:
        if h.from_agent != h.to_agent:
            assert h.hops == 2 and h.path[1] == "A0"
            assert h.cost == pytest.approx(COSTS.h0 + 2 * COSTS.h1)
        else:
            assert h.hops == 0 and h.cost == 0


def _tiny(capacity: int, *, optional_second: bool = False) -> Scenario:
    agents = (AgentProfile(agent_id="X", role="r", capabilities=["a"], capacity=capacity, resource_budget=10,
                           can_coordinate=True, public_key_id="kx"),)
    tasks = (
        TaskSpec(task_id="t1", required_capabilities=["a"], duration_ms=1000, resource_demand=1),
        TaskSpec(task_id="t2", required_capabilities=["a"], duration_ms=1000, resource_demand=1,
                 dependencies=["t1"], mandatory=not optional_second, reward_critical=not optional_second),
    )
    mission = MissionSpec(mission_id="tiny", tasks=tasks, deadline_ms=10_000)
    return Scenario(scenario_id="tiny", seed=0, mission=mission, agents=agents)


def test_capacity_shortfall_is_reported_not_hidden() -> None:
    problem = _problem(_tiny(capacity=1), TopologyName.DISTRIBUTED)
    cp, _ = allocate_cpsat(problem)
    assert not cp.feasible and cp.reason_codes == (AllocationFailure.SOLVER_INFEASIBLE,)
    greedy = allocate_greedy(problem)
    assert not greedy.feasible and greedy.reason_codes == (AllocationFailure.CAPACITY_EXCEEDED,)


def test_optional_task_may_go_unserved_with_penalty() -> None:
    problem = _problem(_tiny(capacity=1, optional_second=True), TopologyName.DISTRIBUTED)
    for plan in (allocate_cpsat(problem)[0], allocate_greedy(problem)):
        assert plan.feasible and plan.unassigned_tasks == ("t2",)
        assert plan.objective.unserved_priority == 1.0


def test_no_capable_agent_is_caught_before_search() -> None:
    scenario = _tiny(capacity=2)
    graph = _problem(scenario, TopologyName.DISTRIBUTED).graph
    broken = scenario.model_copy(update={"agents": (scenario.agents[0].model_copy(update={"capabilities": ("b",)}),)})
    problem = AllocationProblem(broken, graph, COSTS, CONFIG)
    plan = allocate_greedy(problem)
    assert plan.reason_codes == (AllocationFailure.NO_CAPABLE_AGENT,)
    assert allocate_cpsat(problem)[0].reason_codes == (AllocationFailure.NO_CAPABLE_AGENT,)


def test_allocate_uses_greedy_when_cpsat_disabled() -> None:
    scenario = judge_scenario()
    graph = _problem(scenario, TopologyName.DISTRIBUTED).graph
    plan = allocate(scenario, graph, COSTS, CONFIG.model_copy(update={"use_cpsat": False}))
    assert plan.solver is SolverName.GREEDY and not plan.fallback_used


@pytest.mark.slow
@pytest.mark.parametrize("index", range(0, len(factor_grid()), 9))
def test_generated_scenarios_allocate_validly(index: int) -> None:
    factors: ScenarioFactors = factor_grid()[index]
    scenario = generate_scenario(1000 + index, factors)
    eligible, _ = eligible_topologies(scenario, COSTS)
    for topology in eligible:
        problem = _problem(scenario, topology)
        cp, _ = allocate_cpsat(problem)
        greedy = allocate_greedy(problem)
        if cp is not None and cp.feasible:
            assert_plan_valid(problem, cp)
        if greedy.feasible:
            assert_plan_valid(problem, greedy)
            assert cp is not None and cp.feasible, "CP-SAT missed a solution greedy found"
            assert cp.objective.weighted_total <= greedy.objective.weighted_total + 1e-6
