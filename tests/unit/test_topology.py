"""Unit tests for topology templates and graph-derived costs (Dev A)."""

from __future__ import annotations

import pytest

from samg.domain import (
    AgentProfile,
    IneligibilityReason,
    MissionSpec,
    Scenario,
    TaskSpec,
    TopologyCostConfig,
    TopologyName,
)
from samg.simulation.scenarios import judge_scenario
from samg.topology import HopTable, build_graph, eligible_topologies, max_coordination_cost, to_networkx

COSTS = TopologyCostConfig()


def _graph(topology: TopologyName, scenario: Scenario | None = None):
    verdict, graph = build_graph(scenario or judge_scenario(), topology, COSTS)
    assert verdict.eligible, verdict
    assert graph is not None
    return graph


def _two_agent_scenario(*, linkable: bool) -> Scenario:
    """Fixture-1/2 shape: two agents, two dependent tasks needing different agents."""
    agents = (
        AgentProfile(agent_id="X", role="alpha", capabilities=["a"], max_tasks=1, resource_budget=5,
                     can_coordinate=True, is_mission_lead=linkable, public_key_id="kx"),
        AgentProfile(agent_id="Y", role="beta", capabilities=["b"], max_tasks=1, resource_budget=5,
                     public_key_id="ky"),
    )
    tasks = (
        TaskSpec(task_id="t1", required_capabilities=["a"], duration=5, resource_demand=1),
        TaskSpec(task_id="t2", required_capabilities=["b"], duration=5, resource_demand=1, dependencies=["t1"]),
    )
    mission = MissionSpec(mission_id="m2", scenario_id="s2", tasks=tasks, deadline=30)
    return Scenario(scenario_id="s2", seed=0, mission=mission, agents=agents)


def test_hierarchical_routes_through_mission_lead() -> None:
    graph = _graph(TopologyName.HIERARCHICAL)
    assert graph.coordinators == ("A0",)
    assert graph.coordination_links() == [("A0", f"A{i}") for i in range(1, 6)]
    table = HopTable(graph, COSTS)
    assert table.hops("A1", "A4") == 2
    assert table.route("A1", "A4").path == ("A1", "A0", "A4")


def test_functional_cells_group_by_role_and_link_coordinators_to_lead() -> None:
    graph = _graph(TopologyName.FUNCTIONAL_CELL)
    assert graph.cells["transport"] == ("A2", "A3")
    assert graph.cell_coordinators["transport"] == "A2"
    table = HopTable(graph, COSTS)
    assert table.hops("A2", "A3") == 1  # intra-cell direct
    assert table.hops("A3", "A4") == 3  # member -> cell coordinator -> lead -> cell coordinator


def test_distributed_links_dependency_candidates_with_degree_cap() -> None:
    graph = _graph(TopologyName.DISTRIBUTED)
    links = graph.coordination_links()
    degree: dict[str, int] = {}
    for a, b in links:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    assert max(degree.values()) <= COSTS.distributed_max_degree
    assert ("A1", "A4") in links  # T2 (A1) -> T3 (A4)
    assert "A0" not in degree  # the lead performs no tasks, so gets no links


@pytest.mark.parametrize("topology", list(TopologyName))
def test_construction_is_deterministic(topology: TopologyName) -> None:
    assert _graph(topology) == _graph(topology)


def test_topologies_give_different_hop_structures() -> None:
    """Brief §12.10: if topology does not change graph-derived costs, the graph is decorative."""
    hops = {t: HopTable(_graph(t), COSTS).hops("A3", "A4") for t in TopologyName}
    assert len(set(hops.values())) == 3
    versions = {_graph(t).graph_version for t in TopologyName}
    assert len(versions) == 3


def test_route_cost_and_delay_follow_config() -> None:
    table = HopTable(_graph(TopologyName.HIERARCHICAL), COSTS)
    route = table.route("A1", "A4")
    assert route.cost == pytest.approx(COSTS.h0 + 2 * COSTS.h1)
    assert route.delay == pytest.approx(2 * COSTS.handoff_delay_per_hop)
    assert table.route("A4", "A4").cost == 0


def test_path_longer_than_max_hops_is_not_permitted() -> None:
    tight = COSTS.model_copy(update={"max_path_hops": 2})
    table = HopTable(_graph(TopologyName.FUNCTIONAL_CELL), tight)
    assert table.hops("A3", "A4") == 3
    assert table.route("A3", "A4") is None


def test_no_coordinator_makes_hierarchical_ineligible() -> None:
    scenario = _two_agent_scenario(linkable=False)
    agents = tuple(a.model_copy(update={"can_coordinate": False}) for a in scenario.agents)
    scenario = scenario.model_copy(update={"agents": agents})
    verdict, graph = build_graph(scenario, TopologyName.HIERARCHICAL, COSTS)
    assert not verdict.eligible and graph is None
    assert verdict.reasons == (IneligibilityReason.NO_COORDINATOR,)


def test_no_lead_makes_functional_cell_ineligible() -> None:
    verdict, _ = build_graph(_two_agent_scenario(linkable=False), TopologyName.FUNCTIONAL_CELL, COSTS)
    assert verdict.reasons == (IneligibilityReason.NO_MISSION_LEAD,)


def test_unreachable_dependency_is_recorded() -> None:
    capped = COSTS.model_copy(update={"distributed_max_degree": 1})
    scenario = _two_agent_scenario(linkable=True)
    assert build_graph(scenario, TopologyName.DISTRIBUTED, capped)[0].eligible
    # remove the only candidate link by making Y unavailable for t2: no eligible agent pair remains
    agents = (scenario.agents[0], scenario.agents[1].model_copy(update={"available": False}))
    blocked = scenario.model_copy(update={"agents": agents})
    verdict, _ = build_graph(blocked, TopologyName.DISTRIBUTED, capped)
    assert verdict.reasons == (IneligibilityReason.UNREACHABLE_DEPENDENCY,)
    assert "t1->t2" in verdict.detail


def test_eligible_topologies_on_judge_mission() -> None:
    eligible, verdicts = eligible_topologies(judge_scenario(), COSTS)
    assert eligible == list(TopologyName)
    assert all(v.eligible for v in verdicts.values())


def test_max_coordination_cost_bounds_actual_cost() -> None:
    scenario = judge_scenario()
    bound = max_coordination_cost(len(scenario.mission.dependency_edges()), len(scenario.agents), COSTS)
    for t in TopologyName:
        table = HopTable(_graph(t), COSTS)
        worst = 7 * COSTS.handoff_cost(COSTS.max_path_hops) + table.link_maintenance_cost()
        assert worst <= bound


def test_networkx_view_has_typed_nodes() -> None:
    g = to_networkx(_graph(TopologyName.HIERARCHICAL))
    kinds = {data["kind"] for _, data in g.nodes(data=True)}
    assert kinds == {"mission", "task", "capability", "agent"}
