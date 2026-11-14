"""Freshness and replay checks (D016).

Primary barrier: the event must belong to the mission's active epoch, and its
``event_id`` and dedupe key ``(mission_id, epoch, signer_id, seq)`` must be new.
Secondary: ``issued_at`` within clock-skew / max-age bounds of simulation ``now``.

``check`` is pure. Call ``record`` only after the event has also passed
signature verification, so forged events cannot burn a signer's sequence numbers.
The SQLite UNIQUE index is the durable barrier; ``SeenStore`` here is the
in-memory view (persistence provides a DB-backed implementation).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from samg.domain.enums import EventStatus, ReasonCode
from samg.domain.events import AgentEvent, WitnessEvent

DedupeKey = tuple[str, int, str, int]


class SeenStore(Protocol):
    def has_event_id(self, event_id: str) -> bool: ...
    def has_dedupe_key(self, key: DedupeKey) -> bool: ...
    def add(self, event: AgentEvent | WitnessEvent) -> None: ...


@dataclass
class InMemorySeenStore:
    event_ids: set[str] = field(default_factory=set)
    dedupe_keys: set[DedupeKey] = field(default_factory=set)

    def has_event_id(self, event_id: str) -> bool:
        return event_id in self.event_ids

    def has_dedupe_key(self, key: DedupeKey) -> bool:
        return key in self.dedupe_keys

    def add(self, event: AgentEvent | WitnessEvent) -> None:
        self.event_ids.add(event.event_id)
        self.dedupe_keys.add(event.dedupe_key)


@dataclass(frozen=True)
class FreshnessVerdict:
    status: EventStatus
    reason: ReasonCode


@dataclass
class FreshnessGuard:
    """Checks events against active mission epochs and previously seen events."""

    active_epochs: Mapping[str, int]
    max_clock_skew: timedelta
    max_event_age: timedelta
    seen: SeenStore = field(default_factory=InMemorySeenStore)

    def check(self, event: AgentEvent | WitnessEvent, now: datetime) -> FreshnessVerdict | None:
        """Return ``None`` if fresh, else a STALE / DUPLICATE / REJECTED verdict."""
        active = self.active_epochs.get(event.mission_id)
        if active is None:
            return FreshnessVerdict(EventStatus.REJECTED, ReasonCode.WRONG_MISSION)
        if event.epoch != active:
            return FreshnessVerdict(EventStatus.STALE, ReasonCode.OBSOLETE_EPOCH)
        if self.seen.has_event_id(event.event_id):
            return FreshnessVerdict(EventStatus.DUPLICATE, ReasonCode.DUPLICATE_EVENT_ID)
        if self.seen.has_dedupe_key(event.dedupe_key):
            return FreshnessVerdict(EventStatus.DUPLICATE, ReasonCode.DUPLICATE_SEQUENCE)
        if event.issued_at > now + self.max_clock_skew:
            return FreshnessVerdict(EventStatus.REJECTED, ReasonCode.CLOCK_SKEW)
        if now - event.issued_at > self.max_event_age:
            return FreshnessVerdict(EventStatus.STALE, ReasonCode.EVENT_TOO_OLD)
        return None

    def record(self, event: AgentEvent | WitnessEvent) -> None:
        self.seen.add(event)
