"""Coordination graph and allocation-plan contracts (owner: Dev A).

The persisted graph form is JSON-safe nodes/edges. Runtime NetworkX views are
built by ``samg.topology``; domain code never imports NetworkX.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from samg.domain.enums import (
    AllocationFailure,
    EdgeKind,
    IneligibilityReason,
    NodeKind,
    SolverName,
    TopologyName,
)
from samg.domain.mission import SamgModel

GRAPH_SCHEMA_VERSION = "graph-v1"
PLAN_SCHEMA_VERSION = "plan-v1"


class GraphNode(SamgModel):
    node_id: str
    kind: NodeKind
    attrs: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(SamgModel):
    """A directed typed edge. Coordination links are stored once per direction."""

    source: str
    target: str
    kind: EdgeKind
    attrs: dict[str, Any] = Field(default_factory=dict)


class CoordinationGraph(SamgModel):
    """One topology instantiated for one mission.

    ``nodes``/``edges`` hold the full typed mission graph (mission, tasks,
    capabilities, agents) plus the topology's ``coordinates_with`` edges.
    Only ``coordinates_with`` edges are permitted coordination paths.
    """

    schema_version: str = GRAPH_SCHEMA_VERSION
    topology: TopologyName
    mission_id: str
    graph_version: str = Field(description="Content hash of nodes + edges; stable across runs.")
    coordinators: tuple[str, ...] = ()
    cells: dict[str, tuple[str, ...]] = Field(default_factory=dict, description="Cell name -> member agent IDs.")
    cell_coordinators: dict[str, str] = Field(default_factory=dict)
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def coordination_links(self) -> list[tuple[str, str]]:
        """Undirected agent pairs ``(a, b)`` with ``a < b`` that may coordinate."""
        pairs = {
            tuple(sorted((e.source, e.target)))
            for e in self.edges
            if e.kind is EdgeKind.COORDINATES_WITH
        }
        return sorted(pairs)  # type: ignore[arg-type]

    def agent_ids(self) -> list[str]:
        return sorted(n.node_id for n in self.nodes if n.kind is NodeKind.AGENT)


class TopologyEligibility(SamgModel):
    """Whether a topology may be offered to the policy for this mission, and why not."""

    topology: TopologyName
    eligible: bool
    reasons: tuple[IneligibilityReason, ...] = ()
    detail: str = ""

    @model_validator(mode="after")
    def _reasons_iff_ineligible(self) -> TopologyEligibility:
        if self.eligible == bool(self.reasons):
            raise ValueError("an ineligible topology needs reasons; an eligible one has none")
        return self


class Assignment(SamgModel):
    task_id: str
    agent_id: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class Handoff(SamgModel):
    """Graph-derived explanation for one dependency edge ``prerequisite -> dependent``."""

    prerequisite_task: str
    dependent_task: str
    from_agent: str
    to_agent: str
    hops: int = Field(ge=0)
    path: tuple[str, ...]
    cost: float = Field(ge=0, description="0 if same agent, else h0 + h1 * hops.")
    delay: float = Field(ge=0, description="Transit time added before the dependent task may start.")


class ObjectiveTerms(SamgModel):
    """Raw allocation-objective terms plus the weighted total actually minimised."""

    makespan: float
    handoff_cost: float
    resource_use: float
    max_agent_load: float
    unserved_priority: float
    weighted_total: float
    weights: dict[str, float]


class AllocationPlan(SamgModel):
    schema_version: str = PLAN_SCHEMA_VERSION
    plan_id: str
    mission_id: str
    topology: TopologyName
    graph_version: str
    feasible: bool
    solver: SolverName
    solver_status: str = ""
    fallback_used: bool = False
    runtime_ms: float = 0.0
    assignments: tuple[Assignment, ...] = ()
    unassigned_tasks: tuple[str, ...] = ()
    handoffs: tuple[Handoff, ...] = ()
    objective: ObjectiveTerms | None = None
    reason_codes: tuple[AllocationFailure, ...] = ()
    detail: str = ""
    config_version: str = ""

    @model_validator(mode="after")
    def _consistency(self) -> AllocationPlan:
        if self.feasible and self.reason_codes:
            raise ValueError("a feasible plan carries no failure reason codes")
        if not self.feasible and not self.reason_codes:
            raise ValueError("an infeasible plan must carry reason codes")
        if self.feasible and self.objective is None:
            raise ValueError("a feasible plan must carry its objective terms")
        assigned = [a.task_id for a in self.assignments]
        if len(assigned) != len(set(assigned)):
            raise ValueError("a task may be assigned at most once")
        return self

    def assignee(self, task_id: str) -> str | None:
        for a in self.assignments:
            if a.task_id == task_id:
                return a.agent_id
        return None
