"""Freshness/replay guard and task-state machine tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from samg.assurance.freshness import FreshnessGuard
from samg.assurance.state_machine import (
    TERMINAL_STATES,
    TRANSITIONS,
    Actor,
    TaskLedger,
    transition_allowed,
)
from samg.domain import AgentEvent, EventStatus, EventType, ReasonCode, TaskState, WitnessEvent

FIXTURES = Path(__file__).parents[2] / "contract" / "fixtures"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
S = TaskState


def _guard(**kw: object) -> FreshnessGuard:
    return FreshnessGuard(
        active_epochs={"fx-mission-1": 1, "m": 1},
        max_clock_skew=timedelta(seconds=5),
        max_event_age=timedelta(seconds=300),
        **kw,  # type: ignore[arg-type]
    )


def _claim(**kw: object) -> AgentEvent:
    base = dict(event_id="e", mission_id="m", epoch=1, seq=0, event_type=EventType.TASK_COMPLETE_CLAIM,
                task_id="T1", issued_at=T0, key_id="k", agent_id="A1")
    return AgentEvent(**{**base, **kw})


def test_replay_fixture_expected_order() -> None:
    fixture = json.loads((FIXTURES / "05_replayed_event.json").read_text())
    guard = _guard()
    now = T0 + timedelta(seconds=10)
    for raw, expected in zip(fixture["agent_events"], fixture["expected_in_order"], strict=True):
        event = AgentEvent.model_validate(raw)
        verdict = guard.check(event, now)
        if expected["status"] == "AUTHENTICATED":
            assert verdict is None
            guard.record(event)
        else:
            assert verdict is not None
            assert (verdict.status.value, verdict.reason.value) == (expected["status"], expected["reason"])


@pytest.mark.parametrize(
    ("event", "now", "status", "reason"),
    [
        (_claim(mission_id="other"), T0, EventStatus.REJECTED, ReasonCode.WRONG_MISSION),
        (_claim(epoch=2), T0, EventStatus.STALE, ReasonCode.OBSOLETE_EPOCH),
        (_claim(issued_at=T0 + timedelta(seconds=6)), T0, EventStatus.REJECTED, ReasonCode.CLOCK_SKEW),
        (_claim(), T0 + timedelta(seconds=301), EventStatus.STALE, ReasonCode.EVENT_TOO_OLD),
    ],
)
def test_freshness_rejections(event: AgentEvent, now: datetime, status: EventStatus, reason: ReasonCode) -> None:
    verdict = _guard().check(event, now)
    assert verdict is not None and (verdict.status, verdict.reason) == (status, reason)


def test_within_skew_and_age_is_fresh() -> None:
    guard = _guard()
    assert guard.check(_claim(issued_at=T0 + timedelta(seconds=5)), T0) is None
    assert guard.check(_claim(), T0 + timedelta(seconds=300)) is None


def test_check_does_not_record() -> None:
    guard = _guard()
    guard.check(_claim(), T0)
    assert guard.check(_claim(), T0) is None  # only record() burns the id/seq


def test_witness_and_agent_sequences_are_independent() -> None:
    guard = _guard()
    guard.record(_claim(seq=0))
    w = WitnessEvent(event_id="w", mission_id="m", epoch=1, seq=0, task_id="T1", issued_at=T0,
                     key_id="wk", witness_id="W", from_state=S.EXECUTING, to_state=S.FAILED, sim_time_ms=0)
    assert guard.check(w, T0) is None


# --- state machine ---------------------------------------------------------


def _w(task: str, frm: TaskState, to: TaskState, seq: int = 0) -> WitnessEvent:
    return WitnessEvent(event_id=f"w{seq}", mission_id="m", epoch=1, seq=seq, task_id=task, issued_at=T0,
                        key_id="wk", witness_id="W", from_state=frm, to_state=to, sim_time_ms=seq)


def test_structural_rules() -> None:
    assert not any(Actor.AGENT in actors for (_, to), actors in TRANSITIONS.items() if to is S.VERIFIED_COMPLETE)
    assert not transition_allowed(S.ASSIGNED, S.VERIFIED_COMPLETE, Actor.WITNESS)
    assert transition_allowed(S.EXECUTING, S.REPORTED_COMPLETE, Actor.AGENT)
    assert not transition_allowed(S.EXECUTING, S.FAILED, Actor.AGENT)
    for terminal in TERMINAL_STATES:
        assert not any(frm is terminal for frm, _ in TRANSITIONS)


def test_ledger_happy_path_and_illegal_jump() -> None:
    ledger = TaskLedger({"T1": "A0", "T2": "A1"})
    for i, (frm, to) in enumerate([(S.OPEN, S.ASSIGNED), (S.ASSIGNED, S.EXECUTING), (S.EXECUTING, S.VERIFIED_COMPLETE)]):
        assert ledger.apply_witness(_w("T1", frm, to, i)) is None
    assert ledger.state("T1") is S.VERIFIED_COMPLETE
    assert ledger.apply_witness(_w("T2", S.OPEN, S.ASSIGNED, 9)) is None
    assert ledger.apply_witness(_w("T2", S.ASSIGNED, S.VERIFIED_COMPLETE, 10)) is ReasonCode.ILLEGAL_TRANSITION
    assert ledger.apply_witness(_w("T2", S.EXECUTING, S.FAILED, 11)) is ReasonCode.ILLEGAL_TRANSITION  # wrong from
    assert ledger.apply_witness(_w("T9", S.OPEN, S.ASSIGNED, 12)) is ReasonCode.UNKNOWN_TASK
    assert ledger.state("T2") is S.ASSIGNED


def test_agent_claims_only_on_own_tasks() -> None:
    ledger = TaskLedger({"T1": "A0", "T2": "A1"})
    assert ledger.check_agent_claim(_claim(task_id="T2")) is None
    assert ledger.check_agent_claim(_claim(task_id="T1")) is ReasonCode.NOT_TASK_ASSIGNEE
    assert ledger.check_agent_claim(_claim(task_id="T7")) is ReasonCode.UNKNOWN_TASK
    reward = _claim(event_type=EventType.REWARD_CLAIM, task_id=None, payload={"claimed_reward": 1.0})
    assert ledger.check_agent_claim(reward) is None


@settings(max_examples=300, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(list(Actor)), st.sampled_from(list(TaskState))), max_size=25))
def test_random_transition_sequences_respect_invariants(steps: list[tuple[Actor, TaskState]]) -> None:
    state = S.OPEN
    history = [state]
    for actor, target in steps:
        if transition_allowed(state, target, actor):
            if target is S.VERIFIED_COMPLETE:
                assert actor is Actor.WITNESS
                assert state in {S.EXECUTING, S.REPORTED_COMPLETE}
            if actor is Actor.AGENT:
                assert target in {S.EXECUTING, S.REPORTED_COMPLETE}
            assert state not in TERMINAL_STATES
            state = target
            history.append(state)
    if S.VERIFIED_COMPLETE in history:
        assert S.EXECUTING in history[: history.index(S.VERIFIED_COMPLETE)]
