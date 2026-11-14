"""Simulated execution and reward contracts (owner: Dev A).

``ExecutionTrace`` is the simulator's ground truth. Dev B's witness service turns
its ``transitions`` into signed evidence; agent reports are derived from it too
(honestly or, under attack, falsely). The protected learner never sees this
object directly; it sees only the ACP-recomputed reward.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from samg.domain.enums import TaskState, TopologyName
from samg.domain.mission import SamgModel

TRACE_SCHEMA_VERSION = "trace-v1"
REWARD_SCHEMA_VERSION = "reward-v1"


class TaskTransition(SamgModel):
    task_id: str
    agent_id: str | None
    from_state: TaskState
    to_state: TaskState
    sim_time: float = Field(ge=0)


class TaskOutcome(SamgModel):
    task_id: str
    agent_id: str | None
    completed: bool
    start: float | None = None
    end: float | None = None
    failure_reason: str | None = None


class GroundTruthMetrics(SamgModel):
    """Raw metrics and their ``[0, 1]`` normalisations (brief §7.2).

    C: weighted completion fraction (higher is better).
    T, R, H: normalised duration, resource use and coordination overhead (lower is better).
    """

    weighted_completion: float = Field(ge=0, le=1, description="C")
    makespan: float = Field(ge=0)
    duration_norm: float = Field(ge=0, le=1, description="T")
    resource_used: float = Field(ge=0)
    resource_norm: float = Field(ge=0, le=1, description="R")
    coordination_cost: float = Field(ge=0, description="Handoff cost + link-maintenance cost.")
    coordination_norm: float = Field(ge=0, le=1, description="H")
    mandatory_completed: bool
    communication_failures: int = Field(default=0, ge=0)


class ExecutionTrace(SamgModel):
    schema_version: str = TRACE_SCHEMA_VERSION
    mission_id: str
    epoch: int
    plan_id: str
    topology: TopologyName
    graph_version: str
    seed: int
    transitions: tuple[TaskTransition, ...]
    outcomes: tuple[TaskOutcome, ...]
    metrics: GroundTruthMetrics


class RewardBreakdown(SamgModel):
    """Scalar reward plus every component and weighted contribution, for reporting."""

    reward_schema_version: str = REWARD_SCHEMA_VERSION
    weights: dict[str, float]
    components: dict[str, float] = Field(description="Normalised term values entering the formula.")
    contributions: dict[str, float] = Field(description="weight * term value.")
    reward: float = Field(ge=0, le=1)
    failure_outcome: bool = False
    failure_label: str | None = None

    @model_validator(mode="after")
    def _failure_has_label(self) -> RewardBreakdown:
        if self.failure_outcome and not self.failure_label:
            raise ValueError("a failure outcome needs a label")
        return self
