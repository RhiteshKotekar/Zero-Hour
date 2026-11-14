"""Base typed mission graph (brief §5.1).

Node IDs: agents use their bare ``agent_id``; other nodes are prefixed
(``mission:``, ``task:``, ``cap:``) so they can never collide with agents.
"""

from __future__ import annotations

import hashlib
import json

from samg.domain import EdgeKind, GraphEdge, GraphNode, NodeKind, Scenario, TaskSpec


def mission_node(mission_id: str) -> str:
    return f"mission:{mission_id}"


def task_node(task_id: str) -> str:
    return f"task:{task_id}"


def capability_node(capability: str) -> str:
    return f"cap:{capability}"


def eligible_agents(scenario: Scenario, task: TaskSpec) -> list[str]:
    """Available agents that can take ``task`` at all (capability, capacity, budget), sorted by ID."""
    return sorted(
        a.agent_id
        for a in scenario.available_agents()
        if a.capacity > 0 and a.resource_budget >= task.resource_demand and task.is_capable(a)
    )


def base_graph(scenario: Scenario) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Mission, task, capability and agent nodes with structural edges; no coordination edges."""
    mission = scenario.mission
    nodes: list[GraphNode] = [
        GraphNode(node_id=mission_node(mission.mission_id), kind=NodeKind.MISSION,
                  attrs={"deadline_ms": mission.deadline_ms, "epoch": mission.epoch}),
    ]
    edges: list[GraphEdge] = []
    capabilities: set[str] = set()

    for task in mission.tasks:
        nodes.append(GraphNode(node_id=task_node(task.task_id), kind=NodeKind.TASK, attrs={
            "duration_ms": task.duration_ms, "resource_demand": task.resource_demand,
            "priority_weight": task.priority_weight, "mandatory": task.mandatory,
            "capability_match": task.capability_match.value,
        }))
        edges.append(GraphEdge(source=mission_node(mission.mission_id), target=task_node(task.task_id),
                               kind=EdgeKind.HAS_TASK))
        for cap in task.required_capabilities:
            capabilities.add(cap)
            edges.append(GraphEdge(source=task_node(task.task_id), target=capability_node(cap),
                                   kind=EdgeKind.REQUIRES))
        for dep in task.dependencies:
            edges.append(GraphEdge(source=task_node(task.task_id), target=task_node(dep),
                                   kind=EdgeKind.DEPENDS_ON))

    for agent in scenario.agents:
        capabilities.update(agent.capabilities)
        nodes.append(GraphNode(node_id=agent.agent_id, kind=NodeKind.AGENT, attrs={
            "role": agent.role, "available": agent.available, "can_coordinate": agent.can_coordinate,
            "is_mission_lead": agent.is_mission_lead, "capacity": agent.capacity,
            "resource_budget": agent.resource_budget, "capabilities": list(agent.capabilities),
        }))

    for task in mission.tasks:
        for agent_id in eligible_agents(scenario, task):
            edges.append(GraphEdge(source=agent_id, target=task_node(task.task_id), kind=EdgeKind.CAN_PERFORM))

    nodes.extend(GraphNode(node_id=capability_node(c), kind=NodeKind.CAPABILITY) for c in sorted(capabilities))
    return nodes, edges


def graph_version(nodes: list[GraphNode], edges: list[GraphEdge]) -> str:
    """Content hash, independent of insertion order."""
    payload = {
        "nodes": sorted((n.model_dump(mode="json") for n in nodes), key=lambda d: d["node_id"]),
        "edges": sorted((e.model_dump(mode="json") for e in edges),
                        key=lambda d: (d["kind"], d["source"], d["target"])),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
