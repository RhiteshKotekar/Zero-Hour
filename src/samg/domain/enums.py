"""Shared enumerations for SAMG.

Enum *values* are persisted and signed. Changing a value after the H2 contract
freeze requires a ``docs/DECISIONS.md`` entry and updated fixtures.

Ownership: the first block (topology/task/policy-mode) is Dev A's; the second
block (events, episodes, reason codes) is Dev B's. See ``docs/THREE_PERSON_PLAN.md``.
"""

from __future__ import annotations

from enum import StrEnum

# --- Dev A: mission and topology -------------------------------------------


class TopologyName(StrEnum):
    HIERARCHICAL = "HIERARCHICAL"
    FUNCTIONAL_CELL = "FUNCTIONAL_CELL"
    DISTRIBUTED = "DISTRIBUTED"


class TaskState(StrEnum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    EXECUTING = "EXECUTING"
    REPORTED_COMPLETE = "REPORTED_COMPLETE"
    VERIFIED_COMPLETE = "VERIFIED_COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class PolicyMode(StrEnum):
    PROTECTED = "PROTECTED"
    VULNERABLE = "VULNERABLE"



class CapabilityMatch(StrEnum):
    """How a task's ``required_capabilities`` are matched against an agent."""

    ALL = "ALL"
    ANY = "ANY"


class NodeKind(StrEnum):
    """Node types of the typed mission graph (brief §5.1)."""

    MISSION = "MISSION"
    TASK = "TASK"
    CAPABILITY = "CAPABILITY"
    AGENT = "AGENT"


class EdgeKind(StrEnum):
    """Edge types of the typed mission graph (brief §5.1)."""

    HAS_TASK = "HAS_TASK"
    REQUIRES = "REQUIRES"
    DEPENDS_ON = "DEPENDS_ON"
    CAN_PERFORM = "CAN_PERFORM"
    COORDINATES_WITH = "COORDINATES_WITH"


class SolverName(StrEnum):
    """Allocator that produced a plan."""

    CP_SAT = "CP_SAT"
    GREEDY = "GREEDY"


class IneligibilityReason(StrEnum):
    """Why a topology is excluded before policy selection."""

    NO_AVAILABLE_AGENTS = "NO_AVAILABLE_AGENTS"
    NO_COORDINATOR = "NO_COORDINATOR"
    UNREACHABLE_DEPENDENCY = "UNREACHABLE_DEPENDENCY"
    ALLOCATION_INFEASIBLE = "ALLOCATION_INFEASIBLE"


class AllocationFailure(StrEnum):
    """Why an allocation is infeasible."""

    NO_CAPABLE_AGENT = "NO_CAPABLE_AGENT"
    NO_PERMITTED_PATH = "NO_PERMITTED_PATH"
    CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"
    SOLVER_INFEASIBLE = "SOLVER_INFEASIBLE"
    SOLVER_TIMEOUT = "SOLVER_TIMEOUT"
    TOPOLOGY_INELIGIBLE = "TOPOLOGY_INELIGIBLE"


# --- Dev B: events, assurance and learning ---------------------------------


class EventType(StrEnum):
    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETE_CLAIM = "TASK_COMPLETE_CLAIM"
    REWARD_CLAIM = "REWARD_CLAIM"
    WITNESS_TRANSITION = "WITNESS_TRANSITION"
    GRAPH_PATCH = "GRAPH_PATCH"


class EventStatus(StrEnum):
    """Per-event ACP decision (D015).

    The first four come from authentication/freshness (``validate_event``);
    the last three from corroboration against witness evidence.
    """

    AUTHENTICATED = "AUTHENTICATED"
    REJECTED = "REJECTED"
    STALE = "STALE"
    DUPLICATE = "DUPLICATE"
    PROVISIONAL = "PROVISIONAL"
    DISPUTED = "DISPUTED"
    CORROBORATED = "CORROBORATED"


class EpisodeStatus(StrEnum):
    """Per-episode admission decision. Only ``ADMITTED`` may update a protected policy."""

    ADMITTED = "ADMITTED"
    PROVISIONAL = "PROVISIONAL"
    REJECTED = "REJECTED"


class IdentityRole(StrEnum):
    AGENT = "AGENT"
    COORDINATOR = "COORDINATOR"
    WITNESS = "WITNESS"


class RewardSource(StrEnum):
    """Where a learning reward came from. Protected learners accept only ``ACP_RECOMPUTED``."""

    ACP_RECOMPUTED = "ACP_RECOMPUTED"
    AGENT_CLAIM = "AGENT_CLAIM"


class ReasonCode(StrEnum):
    """Machine-readable reasons attached to event and episode decisions."""

    # schema / authentication
    MALFORMED = "MALFORMED"
    SCHEMA_VERSION_MISMATCH = "SCHEMA_VERSION_MISMATCH"
    UNKNOWN_KEY = "UNKNOWN_KEY"
    KEY_AGENT_MISMATCH = "KEY_AGENT_MISMATCH"
    INACTIVE_IDENTITY = "INACTIVE_IDENTITY"
    BAD_SIGNATURE = "BAD_SIGNATURE"
    # authorisation
    UNAUTHORISED_EVENT_TYPE = "UNAUTHORISED_EVENT_TYPE"
    NOT_TASK_ASSIGNEE = "NOT_TASK_ASSIGNEE"
    UNKNOWN_TASK = "UNKNOWN_TASK"
    ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"
    # freshness
    WRONG_MISSION = "WRONG_MISSION"
    OBSOLETE_EPOCH = "OBSOLETE_EPOCH"
    CLOCK_SKEW = "CLOCK_SKEW"
    EVENT_TOO_OLD = "EVENT_TOO_OLD"
    DUPLICATE_SEQUENCE = "DUPLICATE_SEQUENCE"
    DUPLICATE_EVENT_ID = "DUPLICATE_EVENT_ID"
    # corroboration
    WITNESS_CONFIRMS = "WITNESS_CONFIRMS"
    WITNESS_CONTRADICTS = "WITNESS_CONTRADICTS"
    NO_WITNESS_EVIDENCE = "NO_WITNESS_EVIDENCE"
    REWARD_CLAIM_NOT_TRUSTED = "REWARD_CLAIM_NOT_TRUSTED"
    # episode admission
    ALL_REWARD_CRITICAL_VERIFIED = "ALL_REWARD_CRITICAL_VERIFIED"
    REWARD_CRITICAL_UNVERIFIED = "REWARD_CRITICAL_UNVERIFIED"
    DISPUTED_CLAIM_QUARANTINED = "DISPUTED_CLAIM_QUARANTINED"
    INFEASIBLE_PLAN = "INFEASIBLE_PLAN"
    # topology selection
    TOPOLOGY_NOT_ELIGIBLE = "TOPOLOGY_NOT_ELIGIBLE"
    NO_ELIGIBLE_TOPOLOGY = "NO_ELIGIBLE_TOPOLOGY"
    # learning gate
    CONTEXT_SCHEMA_MISMATCH = "CONTEXT_SCHEMA_MISMATCH"
    INELIGIBLE_STATUS = "INELIGIBLE_STATUS"
    UNTRUSTED_REWARD_SOURCE = "UNTRUSTED_REWARD_SOURCE"
    DUPLICATE_EPISODE = "DUPLICATE_EPISODE"
