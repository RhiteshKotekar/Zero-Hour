"""Signed events, ACP decisions, episodes and learning events (Dev B).

Trust chain:

    AgentEvent / WitnessEvent  (signed claims / signed observations)
        -> EventDecision         (per-event ACP result)
        -> EpisodeRecord         (per-mission admission; reward recomputed by ACP)
        -> LearningEvent         (what a policy may observe)

A signature proves that a registered key signed ``signed_payload_bytes()``.
It never proves the claim is true. Only an ``EpisodeStatus.ADMITTED`` episode
with an ``ACP_RECOMPUTED`` reward may update a protected policy.
"""

from __future__ import annotations

import math
from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from samg.domain.canonical import CanonicalisationError, canonical_bytes, canonical_json
from samg.domain.enums import (
    EpisodeStatus,
    EventStatus,
    EventType,
    ReasonCode,
    RewardSource,
    TaskState,
    TopologyName,
)

EVENT_SCHEMA_VERSION = "evt-v1"

_Id = Field(min_length=1, max_length=128)

_TASK_EVENT_TYPES = frozenset(
    {EventType.TASK_STARTED, EventType.TASK_COMPLETE_CLAIM, EventType.WITNESS_TRANSITION}
)


class IneligibleLearningEvent(Exception):
    """Raised when a protected policy is offered an event it must not learn from."""

    def __init__(self, reason: ReasonCode, detail: str = "") -> None:
        self.reason = reason
        super().__init__(f"{reason.value}: {detail}" if detail else reason.value)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _SignedEvent(_Frozen):
    """Fields and signing behaviour shared by agent and witness events."""

    schema_version: Literal["evt-v1"] = EVENT_SCHEMA_VERSION
    event_id: str = _Id
    mission_id: str = _Id
    epoch: int = Field(ge=0)
    seq: int = Field(ge=0, description="Per-signer, per-epoch monotonically increasing")
    event_type: EventType
    task_id: str | None = Field(default=None, min_length=1, max_length=128)
    issued_at: AwareDatetime = Field(description="Secondary freshness check only (D016)")
    payload: dict[str, Any] = Field(default_factory=dict)
    key_id: str = _Id
    signature: str | None = Field(default=None, description="URL-safe base64 Ed25519")

    @field_validator("payload")
    @classmethod
    def _payload_is_canonical(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            canonical_json(value)
        except CanonicalisationError as exc:
            raise ValueError(f"payload is not canonicalisable: {exc}") from exc
        return value

    @property
    def signer_id(self) -> str:
        raise NotImplementedError

    @property
    def dedupe_key(self) -> tuple[str, int, str, int]:
        """Replay key ``(mission_id, epoch, signer_id, seq)`` (D016)."""
        return (self.mission_id, self.epoch, self.signer_id, self.seq)

    def signed_payload_bytes(self) -> bytes:
        """Exact bytes covered by the signature: every field except ``signature``."""
        return canonical_bytes(self.model_dump(mode="python", exclude={"signature"}))

    def with_signature(self, signature: str) -> Self:
        return self.model_copy(update={"signature": signature})


class AgentEvent(_SignedEvent):
    """A signed claim made by a simulated agent. Untrusted until corroborated.

    Payload conventions (``evt-v1``):

    * ``TASK_STARTED`` / ``TASK_COMPLETE_CLAIM``: ``task_id`` required; payload optional.
    * ``REWARD_CLAIM``: ``{"claimed_reward": float, "claimed_metrics": {...}}``.
      Recorded for audit; ACP never copies it into a protected reward.
    * ``GRAPH_PATCH``: ``{"add_edges": [[a, b], ...], "remove_edges": [...]}``.
    """

    kind: Literal["AGENT_EVENT"] = "AGENT_EVENT"
    agent_id: str = _Id

    @property
    def signer_id(self) -> str:
        return self.agent_id

    @model_validator(mode="after")
    def _task_id_required(self) -> Self:
        if self.event_type in _TASK_EVENT_TYPES and self.task_id is None:
            raise ValueError(f"{self.event_type.value} requires task_id")
        return self


class WitnessEvent(_SignedEvent):
    """A task transition observed by the independent witness and signed with its own key."""

    kind: Literal["WITNESS_EVENT"] = "WITNESS_EVENT"
    witness_id: str = _Id
    event_type: Literal[EventType.WITNESS_TRANSITION] = EventType.WITNESS_TRANSITION
    task_id: str = _Id
    from_state: TaskState
    to_state: TaskState
    sim_time_ms: int = Field(ge=0)

    @property
    def signer_id(self) -> str:
        return self.witness_id


class EventDecision(_Frozen):
    """ACP decision for a single received event."""

    decision_id: str = _Id
    event_id: str = _Id
    mission_id: str = _Id
    epoch: int = Field(ge=0)
    signer_id: str = _Id
    event_type: EventType
    task_id: str | None = None
    status: EventStatus
    reason_codes: tuple[ReasonCode, ...] = ()
    corroborating_event_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _negative_needs_reason(self) -> Self:
        negative = {
            EventStatus.REJECTED,
            EventStatus.STALE,
            EventStatus.DUPLICATE,
            EventStatus.DISPUTED,
            EventStatus.PROVISIONAL,
        }
        if self.status in negative and not self.reason_codes:
            raise ValueError(f"{self.status.value} decision needs at least one reason code")
        if self.status is EventStatus.CORROBORATED and not self.corroborating_event_ids:
            raise ValueError("CORROBORATED decision must cite witness event ids")
        return self


def _check_reward(value: float | None) -> float | None:
    if value is not None and (not math.isfinite(value) or not 0.0 <= value <= 1.0):
        raise ValueError("reward must be finite and in [0, 1]")
    return value


class EpisodeRecord(_Frozen):
    """ACP admission result for one mission run.

    ``reward`` is recomputed by the ACP from admitted (witness-verified)
    outcomes via the reward schema; it is present iff ``status is ADMITTED``.
    """

    episode_id: str = _Id
    mission_id: str = _Id
    epoch: int = Field(ge=0)
    topology_decision_id: str = _Id
    topology: TopologyName
    plan_id: str = _Id
    event_decisions: tuple[EventDecision, ...] = ()
    admitted_task_states: dict[str, TaskState] = Field(default_factory=dict)
    reward: float | None = None
    reward_terms: dict[str, float] = Field(default_factory=dict)
    reward_schema_version: str | None = None
    status: EpisodeStatus
    reason_codes: tuple[ReasonCode, ...] = ()

    @field_validator("reward")
    @classmethod
    def _reward_range(cls, value: float | None) -> float | None:
        return _check_reward(value)

    @model_validator(mode="after")
    def _reward_iff_admitted(self) -> Self:
        if self.status is EpisodeStatus.ADMITTED:
            if self.reward is None or self.reward_schema_version is None:
                raise ValueError("ADMITTED episode requires reward and reward_schema_version")
        elif self.reward is not None:
            raise ValueError(f"{self.status.value} episode must not carry a reward")
        if self.status is not EpisodeStatus.ADMITTED and not self.reason_codes:
            raise ValueError(f"{self.status.value} episode needs at least one reason code")
        return self


class LearningEvent(_Frozen):
    """What a topology policy observes. Preserves the decision-time context.

    Protected policies must call ``require_protected_eligible()`` before
    touching their state. ``VulnerableLinUCB`` (Experiment C only) accepts
    ``AGENT_CLAIM`` rewards from authenticated events.
    """

    event_id: str = _Id
    episode_id: str = _Id
    decision_id: str = _Id
    topology: TopologyName
    feature_schema_version: str = _Id
    context: tuple[float, ...] = Field(min_length=1)
    reward: float | None = None
    reward_source: RewardSource
    status: EpisodeStatus

    @field_validator("reward")
    @classmethod
    def _reward_range(cls, value: float | None) -> float | None:
        return _check_reward(value)

    @field_validator("context")
    @classmethod
    def _finite_context(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not all(math.isfinite(x) for x in value):
            raise ValueError("context features must be finite")
        return value

    @model_validator(mode="after")
    def _admitted_needs_reward(self) -> Self:
        if self.status is EpisodeStatus.ADMITTED and self.reward is None:
            raise ValueError("ADMITTED learning event requires a reward")
        return self

    @property
    def is_protected_eligible(self) -> bool:
        return (
            self.status is EpisodeStatus.ADMITTED
            and self.reward_source is RewardSource.ACP_RECOMPUTED
            and self.reward is not None
        )

    def require_protected_eligible(self) -> float:
        """Return the reward, or raise ``IneligibleLearningEvent`` (INV-05)."""
        if self.status is not EpisodeStatus.ADMITTED:
            raise IneligibleLearningEvent(ReasonCode.INELIGIBLE_STATUS, self.status.value)
        if self.reward_source is not RewardSource.ACP_RECOMPUTED:
            raise IneligibleLearningEvent(
                ReasonCode.UNTRUSTED_REWARD_SOURCE, self.reward_source.value
            )
        assert self.reward is not None  # guaranteed by validator
        return self.reward
