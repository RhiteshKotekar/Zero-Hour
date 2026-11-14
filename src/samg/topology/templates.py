"""The three deterministic topology templates (brief §5.3).

- Hierarchical: one hub coordinator (mission lead preferred, else the first
  coordinator-eligible agent by ID) linked to every other available agent; all
  other pairs route through it.
- Functional-cell: available non-hub agents are grouped into cells by ``role``;
  members of a cell are directly linked; each cell coordinator links to the
  hub (the mission lead when present). Cross-cell handoffs route
  coordinator -> hub -> coordinator.
- Distributed: for each dependency edge, link eligible agents of the
  prerequisite to eligible agents of the dependent, in sorted order, skipping
  a link if either endpoint already has ``distributed_max_degree`` links.

Every template only uses links permitted by ``Scenario.permitted_links`` (the
physical/policy network). Ties are always broken by agent ID. No randomness.
"""

from __future__ import annotations

from collections import defaultdict

from samg.domain import (
    CoordinationGraph,
    EdgeKind,
    GraphEdge,
    IneligibilityReason,
    Scenario,
    TopologyCostConfig,
    TopologyEligibility,
    TopologyName,
)
from samg.topology.builder import base_graph, eligible_agents, graph_version
from samg.topology.costs import HopTable

Link = tuple[str, str]


def _norm(a: str, b: str) -> Link:
    return (a, b) if a < b else (b, a)


def _hub(scenario: Scenario) -> str | None:
    """Coordinator for hierarchical / cell hub: mission lead preferred, then any coordinator, by ID."""
    candidates = sorted((a for a in scenario.available_agents() if a.can_coordinate),
                        key=lambda a: (not a.is_mission_lead, a.agent_id))
    return candidates[0].agent_id if candidates else None


def _permitted(scenario: Scenario, links: set[Link]) -> set[Link]:
    return {link for link in links if scenario.link_permitted(*link)}


def _hierarchical(scenario: Scenario) -> tuple[set[Link], dict, IneligibilityReason | None]:
    hub = _hub(scenario)
    if hub is None:
        return set(), {}, IneligibilityReason.NO_COORDINATOR
    links = {_norm(hub, a.agent_id) for a in scenario.available_agents() if a.agent_id != hub}
    return _permitted(scenario, links), {"coordinators": (hub,)}, None


def _functional_cell(scenario: Scenario) -> tuple[set[Link], dict, IneligibilityReason | None]:
    hub = _hub(scenario)
    if hub is None:
        return set(), {}, IneligibilityReason.NO_COORDINATOR
    members: dict[str, list] = defaultdict(list)
    for agent in scenario.available_agents():
        if agent.agent_id != hub:
            members[agent.role].append(agent)
    links: set[Link] = set()
    cells: dict[str, tuple[str, ...]] = {"hub": (hub,)}
    cell_coordinators: dict[str, str] = {"hub": hub}
    for role in sorted(members):
        group = sorted(members[role], key=lambda a: (not a.can_coordinate, a.agent_id))
        ids = sorted(a.agent_id for a in group)
        coordinator = group[0].agent_id
        cells[role] = tuple(ids)
        cell_coordinators[role] = coordinator
        links.add(_norm(coordinator, hub))
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                links.add(_norm(a, b))
    coordinators = tuple(sorted(set(cell_coordinators.values())))
    extra = {"coordinators": coordinators, "cells": cells, "cell_coordinators": cell_coordinators}
    return _permitted(scenario, links), extra, None


def _distributed(scenario: Scenario, costs: TopologyCostConfig) -> tuple[set[Link], dict, IneligibilityReason | None]:
    mission = scenario.mission
    degree: dict[str, int] = defaultdict(int)
    links: set[Link] = set()
    for prereq, dependent in mission.dependency_edges():
        sources = eligible_agents(scenario, mission.task(prereq))
        targets = eligible_agents(scenario, mission.task(dependent))
        for a in sources:
            for b in targets:
                if a == b or not scenario.link_permitted(a, b):
                    continue
                link = _norm(a, b)
                if link in links:
                    continue
                if degree[a] >= costs.distributed_max_degree or degree[b] >= costs.distributed_max_degree:
                    continue
                links.add(link)
                degree[a] += 1
                degree[b] += 1
    return links, {}, None


def _assemble(scenario: Scenario, topology: TopologyName, links: set[Link], extra: dict) -> CoordinationGraph:
    nodes, edges = base_graph(scenario)
    for a, b in sorted(links):
        edges.append(GraphEdge(source=a, target=b, kind=EdgeKind.COORDINATES_WITH))
        edges.append(GraphEdge(source=b, target=a, kind=EdgeKind.COORDINATES_WITH))
    nodes.sort(key=lambda n: n.node_id)
    edges.sort(key=lambda e: (e.kind.value, e.source, e.target))
    version = graph_version(nodes, edges)
    return CoordinationGraph(topology=topology, mission_id=scenario.mission.mission_id, graph_version=version,
                             nodes=tuple(nodes), edges=tuple(edges), **extra)


def _unreachable_dependencies(scenario: Scenario, graph: CoordinationGraph, costs: TopologyCostConfig) -> list[str]:
    """Dependency edges for which no (prerequisite agent, dependent agent) pair is connected."""
    table = HopTable(graph, costs)
    mission = scenario.mission
    bad = []
    for prereq, dependent in mission.dependency_edges():
        sources = eligible_agents(scenario, mission.task(prereq))
        targets = eligible_agents(scenario, mission.task(dependent))
        if not any(a == b or table.route(a, b) is not None for a in sources for b in targets):
            bad.append(f"{prereq}->{dependent}")
    return bad


def build_graph(
    scenario: Scenario, topology: TopologyName, costs: TopologyCostConfig | None = None
) -> tuple[TopologyEligibility, CoordinationGraph | None]:
    """Build ``topology`` for ``scenario``. Returns the eligibility verdict and the graph (None if ineligible)."""
    costs = costs or TopologyCostConfig()
    if not scenario.available_agents():
        return TopologyEligibility(topology=topology, eligible=False,
                                   reasons=[IneligibilityReason.NO_AVAILABLE_AGENTS]), None
    if topology is TopologyName.HIERARCHICAL:
        links, extra, failure = _hierarchical(scenario)
    elif topology is TopologyName.FUNCTIONAL_CELL:
        links, extra, failure = _functional_cell(scenario)
    else:
        links, extra, failure = _distributed(scenario, costs)
    if failure is not None:
        return TopologyEligibility(topology=topology, eligible=False, reasons=[failure]), None
    graph = _assemble(scenario, topology, links, extra)
    unreachable = _unreachable_dependencies(scenario, graph, costs)
    if unreachable:
        return TopologyEligibility(topology=topology, eligible=False,
                                   reasons=[IneligibilityReason.UNREACHABLE_DEPENDENCY],
                                   detail=", ".join(unreachable)), None
    return TopologyEligibility(topology=topology, eligible=True), graph


def eligible_topologies(
    scenario: Scenario, costs: TopologyCostConfig | None = None
) -> tuple[list[TopologyName], dict[TopologyName, TopologyEligibility]]:
    """Topologies the policy may choose from, plus every verdict for the audit log."""
    verdicts = {t: build_graph(scenario, t, costs)[0] for t in TopologyName}
    return [t for t in TopologyName if verdicts[t].eligible], verdicts
