"""Shared, implementation-independent SAMG domain contracts.

Frozen after gate G0 (H2). Changes need a ``docs/DECISIONS.md`` entry.
"""

from samg.domain.canonical import (
    CANONICAL_VERSION,
    CanonicalisationError,
    canonical_bytes,
    canonical_hash,
    canonical_json,
)
from samg.domain.enums import (
    EpisodeStatus,
    EventStatus,
    EventType,
    IdentityRole,
    PolicyMode,
    ReasonCode,
    RewardSource,
    TaskState,
    TopologyName,
)
from samg.domain.events import (
    EVENT_SCHEMA_VERSION,
    AgentEvent,
    EpisodeRecord,
    EventDecision,
    IneligibleLearningEvent,
    LearningEvent,
    WitnessEvent,
)

# Dev A: re-export mission.py / graph.py models below once they land.

__all__ = [
    "CANONICAL_VERSION",
    "EVENT_SCHEMA_VERSION",
    "AgentEvent",
    "CanonicalisationError",
    "EpisodeRecord",
    "EpisodeStatus",
    "EventDecision",
    "EventStatus",
    "EventType",
    "IdentityRole",
    "IneligibleLearningEvent",
    "LearningEvent",
    "PolicyMode",
    "ReasonCode",
    "RewardSource",
    "TaskState",
    "TopologyName",
    "WitnessEvent",
    "canonical_bytes",
    "canonical_hash",
    "canonical_json",
]
