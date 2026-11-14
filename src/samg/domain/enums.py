"""Enumerations shared across SAMG packages.

Enum *values* are persisted and signed; never rename a value without a new
schema version and a ``docs/DECISIONS.md`` entry.

Ownership: Dev A owns the mission/graph/allocation enums in this file; Dev B
appends the event, episode and report enums below the marked section.
"""

from __future__ import annotations

from enum import StrEnum


class TopologyName(StrEnum):
    """The three coordination topologies (bandit arms)."""

    DISTRIBUTED = "distributed"
    FUNCTIONAL_CELL = "functional_cell"
    HIERARCHICAL = "hierarchical"


class TaskState(StrEnum):
    """Task lifecycle states (brief §8.8)."""

    OPEN = "open"
    ASSIGNED = "assigned"
    EXECUTING = "executing"
    REPORTED_COMPLETE = "reported_complete"
    VERIFIED_COMPLETE = "verified_complete"
    BLOCKED = "blocked"
    FAILED = "failed"


class PolicyMode(StrEnum):
    """Whether the learning path is evidence-gated."""

    PROTECTED = "protected"
    VULNERABLE = "vulnerable"


class CapabilityMatch(StrEnum):
    """How a task's ``required_capabilities`` are matched against an agent."""

    ALL = "all"
    ANY = "any"


class NodeKind(StrEnum):
    """Node types of the typed mission graph (brief §5.1)."""

    AGENT = "agent"
    CAPABILITY = "capability"
    MISSION = "mission"
    TASK = "task"


class EdgeKind(StrEnum):
    """Edge types of the typed mission graph (brief §5.1)."""

    CAN_PERFORM = "can_perform"
    COORDINATES_WITH = "coordinates_with"
    DEPENDS_ON = "depends_on"
    HAS_TASK = "has_task"
    REQUIRES = "requires"


class SolverName(StrEnum):
    """Allocator that produced a plan."""

    CP_SAT = "cp_sat"
    GREEDY = "greedy"


class IneligibilityReason(StrEnum):
    """Machine-readable reasons a topology is excluded before selection."""

    NO_AVAILABLE_AGENTS = "no_available_agents"
    NO_COORDINATOR = "no_coordinator"
    NO_MISSION_LEAD = "no_mission_lead"
    UNREACHABLE_DEPENDENCY = "unreachable_dependency"


class AllocationFailure(StrEnum):
    """Machine-readable reasons an allocation is infeasible."""

    NO_CAPABLE_AGENT = "no_capable_agent"
    NO_PERMITTED_PATH = "no_permitted_path"
    CAPACITY_EXCEEDED = "capacity_exceeded"
    SOLVER_INFEASIBLE = "solver_infeasible"
    SOLVER_TIMEOUT = "solver_timeout"
    TOPOLOGY_INELIGIBLE = "topology_ineligible"


# --- Dev B: event / episode / report enums go below this line --------------
