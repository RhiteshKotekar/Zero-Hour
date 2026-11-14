"""Shared policy types: the decision record and the protected learning gate."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from samg.domain.enums import ReasonCode, TopologyName
from samg.domain.events import IneligibleLearningEvent, LearningEvent

ARM_ORDER: tuple[TopologyName, ...] = tuple(sorted(TopologyName, key=lambda t: t.value))
"""Deterministic arm order; ties are broken toward the earliest arm in this order."""


class PolicyDecision(BaseModel):
    """A policy's choice plus everything needed to audit and replay it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_kind: str
    policy_version: str
    topology: TopologyName | None
    eligible: tuple[TopologyName, ...]
    feature_schema_version: str
    context: tuple[float, ...]
    scores: dict[TopologyName, float] = Field(default_factory=dict)
    means: dict[TopologyName, float] = Field(default_factory=dict)
    bonuses: dict[TopologyName, float] = Field(default_factory=dict)
    warmup: bool = False
    reason_codes: tuple[ReasonCode, ...] = ()


class TopologyPolicy(Protocol):
    kind: str

    def select(
        self,
        context: Sequence[float],
        eligible: Sequence[TopologyName],
        feature_schema_version: str,
    ) -> PolicyDecision: ...

    def observe(self, event: LearningEvent) -> None: ...

    def snapshot(self) -> dict[str, Any]: ...


def ordered_eligible(eligible: Sequence[TopologyName]) -> tuple[TopologyName, ...]:
    chosen = set(eligible)
    return tuple(arm for arm in ARM_ORDER if arm in chosen)


def argmax_by_arm_order(scores: dict[TopologyName, float], tol: float = 1e-12) -> TopologyName:
    """Highest score; ties within ``tol`` go to the earliest arm in ``ARM_ORDER``."""
    best = max(scores.values())
    return next(arm for arm in ARM_ORDER if arm in scores and scores[arm] >= best - tol)


class ProtectedGate:
    """INV-05 / INV-08: only ADMITTED, ACP-recomputed, not-yet-applied episodes pass."""

    def __init__(self, applied: Sequence[str] = ()) -> None:
        self.applied_episodes: set[str] = set(applied)
        self.rejected_attempts: list[tuple[str, ReasonCode]] = []

    def admit(self, event: LearningEvent) -> float:
        """Return the reward to learn from, or log and raise ``IneligibleLearningEvent``."""
        try:
            reward = event.require_protected_eligible()
            if event.episode_id in self.applied_episodes:
                raise IneligibleLearningEvent(ReasonCode.DUPLICATE_EPISODE, event.episode_id)
        except IneligibleLearningEvent as exc:
            self.rejected_attempts.append((event.event_id, exc.reason))
            raise
        return reward

    def mark_applied(self, event: LearningEvent) -> None:
        self.applied_episodes.add(event.episode_id)
