"""Task-state machine (brief §8.8) and the witness-driven task ledger.

Rules enforced:

* Agents may only move their own tasks ``ASSIGNED -> EXECUTING`` (``TASK_STARTED``)
  and ``EXECUTING -> REPORTED_COMPLETE`` (``TASK_COMPLETE_CLAIM``).
* Only the witness can set ``VERIFIED_COMPLETE``, ``FAILED``, ``ASSIGNED`` or ``BLOCKED``.
* ``VERIFIED_COMPLETE`` is reachable only from ``EXECUTING`` or ``REPORTED_COMPLETE``
  (no ``ASSIGNED -> VERIFIED_COMPLETE`` jump).
* ``VERIFIED_COMPLETE`` and ``FAILED`` are terminal.

The ``TaskLedger`` is the authoritative timeline built from witness transitions.
Agent claims are checked for structural legality here and compared against the
ledger by corroboration (``admission.py``); they never advance the ledger.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum

from samg.domain.enums import EventType, ReasonCode, TaskState
from samg.domain.events import AgentEvent, WitnessEvent


class Actor(StrEnum):
    AGENT = "AGENT"
    WITNESS = "WITNESS"


S = TaskState
_A, _W = frozenset({Actor.AGENT}), frozenset({Actor.WITNESS})
_AW = _A | _W

TRANSITIONS: Mapping[tuple[TaskState, TaskState], frozenset[Actor]] = {
    (S.OPEN, S.ASSIGNED): _W,
    (S.OPEN, S.BLOCKED): _W,
    (S.ASSIGNED, S.EXECUTING): _AW,
    (S.ASSIGNED, S.BLOCKED): _W,
    (S.ASSIGNED, S.FAILED): _W,
    (S.BLOCKED, S.ASSIGNED): _W,
    (S.BLOCKED, S.FAILED): _W,
    (S.EXECUTING, S.REPORTED_COMPLETE): _A,
    (S.EXECUTING, S.VERIFIED_COMPLETE): _W,
    (S.EXECUTING, S.FAILED): _W,
    (S.REPORTED_COMPLETE, S.VERIFIED_COMPLETE): _W,
    (S.REPORTED_COMPLETE, S.FAILED): _W,
}

TERMINAL_STATES = frozenset({S.VERIFIED_COMPLETE, S.FAILED})

CLAIM_TARGET: Mapping[EventType, TaskState] = {
    EventType.TASK_STARTED: S.EXECUTING,
    EventType.TASK_COMPLETE_CLAIM: S.REPORTED_COMPLETE,
}


def transition_allowed(current: TaskState, target: TaskState, actor: Actor) -> bool:
    return actor in TRANSITIONS.get((current, target), frozenset())


class TaskLedger:
    """Witness-observed task states for one mission run."""

    def __init__(self, assignments: Mapping[str, str], task_ids: Iterable[str] | None = None) -> None:
        self._assignee = dict(assignments)
        ids = set(task_ids) if task_ids is not None else set(assignments)
        self._state: dict[str, TaskState] = {t: S.OPEN for t in sorted(ids)}
        self._witness_events: dict[str, list[WitnessEvent]] = {t: [] for t in self._state}

    @property
    def states(self) -> dict[str, TaskState]:
        return dict(self._state)

    def state(self, task_id: str) -> TaskState | None:
        return self._state.get(task_id)

    def assignee(self, task_id: str) -> str | None:
        return self._assignee.get(task_id)

    def witness_events(self, task_id: str) -> list[WitnessEvent]:
        return list(self._witness_events.get(task_id, []))

    def apply_witness(self, event: WitnessEvent) -> ReasonCode | None:
        """Advance the ledger, or return why the witness transition is illegal."""
        current = self._state.get(event.task_id)
        if current is None:
            return ReasonCode.UNKNOWN_TASK
        if event.from_state is not current or not transition_allowed(
            current, event.to_state, Actor.WITNESS
        ):
            return ReasonCode.ILLEGAL_TRANSITION
        self._state[event.task_id] = event.to_state
        self._witness_events[event.task_id].append(event)
        return None

    def check_agent_claim(self, event: AgentEvent) -> ReasonCode | None:
        """Structural legality of an agent's task claim (not its truth)."""
        if event.event_type not in CLAIM_TARGET:
            return None  # REWARD_CLAIM / GRAPH_PATCH are not task transitions
        assert event.task_id is not None  # AgentEvent validator guarantees this
        if event.task_id not in self._state:
            return ReasonCode.UNKNOWN_TASK
        if self._assignee.get(event.task_id) != event.agent_id:
            return ReasonCode.NOT_TASK_ASSIGNEE
        return None
