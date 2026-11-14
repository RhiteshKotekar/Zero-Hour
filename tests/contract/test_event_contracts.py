"""G0 contract tests for Dev B's domain payloads, canonical bytes and fixtures."""

from __future__ import annotations

import base64
import importlib.util
import json
import math
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path

import pytest
from pydantic import ValidationError

from samg.assurance.identity import Identity, IdentityRegistry
from samg.assurance.signatures import verify_event
from samg.domain import (
    AgentEvent,
    CanonicalisationError,
    EpisodeRecord,
    EpisodeStatus,
    EventDecision,
    EventStatus,
    EventType,
    IneligibleLearningEvent,
    LearningEvent,
    ReasonCode,
    RewardSource,
    TaskState,
    TopologyName,
    WitnessEvent,
    canonical_bytes,
    canonical_json,
)

FIXTURES = Path(__file__).parent / "fixtures"

# Golden values for fixture 03's claim. If these change, canonicalisation or the
# signed field set changed: that is a DECISIONS-level contract change.
GOLDEN_PAYLOAD_B64 = (
    "eyJhZ2VudF9pZCI6IkExIiwiZXBvY2giOjEsImV2ZW50X2lkIjoiYTEtY2xhaW0tMCIsImV2ZW50X3R5cGUiOiJU"
    "QVNLX0NPTVBMRVRFX0NMQUlNIiwiaXNzdWVkX2F0IjoiMjAyNi0wMS0wMVQwMDowMDowMi42MDAwMDArMDA6MDAi"
    "LCJrZXlfaWQiOiJBMSNhNjllYjk5YjBkMDQiLCJraW5kIjoiQUdFTlRfRVZFTlQiLCJtaXNzaW9uX2lkIjoiZngt"
    "bWlzc2lvbi0xIiwicGF5bG9hZCI6e30sInNjaGVtYV92ZXJzaW9uIjoiZXZ0LXYxIiwic2VxIjowLCJ0YXNrX2lk"
    "IjoiVDIifQ=="
)
GOLDEN_SIGNATURE = (
    "MoSLpA-JybvtnX5Q-XpovqGCtOWHdy3L_mj-SJ5f0pqGGTBn_RXD-AmnIpDp6vvlrjaehnLkEiGwD9l_VDacDg=="
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _registry(fixture: dict) -> IdentityRegistry:
    return IdentityRegistry(Identity.model_validate(i) for i in fixture["identities"])


# --- fixtures --------------------------------------------------------------


def test_fixtures_are_current() -> None:
    spec = importlib.util.spec_from_file_location("make_fixtures", Path(__file__).parent / "make_fixtures.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, data in module.build_all().items():
        assert (FIXTURES / name).read_text(encoding="utf-8") == module.render(data), name


@pytest.mark.parametrize(
    "name", ["03_honest_claim.json", "04_false_signed_claim.json", "05_replayed_event.json"]
)
def test_event_fixtures_load_and_verify(name: str) -> None:
    fixture = _load(name)
    registry = _registry(fixture)
    events = [AgentEvent.model_validate(e) for e in fixture["agent_events"]] + [
        WitnessEvent.model_validate(e) for e in fixture["witness_events"]
    ]
    assert events
    for event in events:
        assert verify_event(event, registry) is None, event.event_id


@pytest.mark.parametrize("name", ["01_reachable_mission.json", "02_unreachable_mission.json"])
def test_mission_fixtures_load(name: str) -> None:
    mission_mod = pytest.importorskip("samg.domain.mission", reason="Dev A's mission.py not merged yet")
    fixture = _load(name)
    mission_mod.MissionSpec.model_validate(fixture["mission"])
    for agent in fixture["agents"]:
        mission_mod.AgentProfile.model_validate(agent)


def test_mission_fixture_key_ids_match_registry() -> None:
    registry = _registry(_load("03_honest_claim.json"))
    for agent in _load("01_reachable_mission.json")["agents"]:
        identity = registry.by_identity_id(agent["agent_id"])
        assert identity is not None and identity.key_id == agent["public_key_id"]


# --- golden signature ------------------------------------------------------


def test_golden_signed_payload_and_signature() -> None:
    fixture = _load("03_honest_claim.json")
    claim = AgentEvent.model_validate(fixture["agent_events"][0])
    assert base64.urlsafe_b64encode(claim.signed_payload_bytes()).decode() == GOLDEN_PAYLOAD_B64
    assert claim.signature == GOLDEN_SIGNATURE
    assert verify_event(claim, _registry(fixture)) is None


def test_signature_excluded_from_payload() -> None:
    claim = AgentEvent.model_validate(_load("03_honest_claim.json")["agent_events"][0])
    assert claim.signed_payload_bytes() == claim.with_signature("x").signed_payload_bytes()
    assert b"signature" not in claim.signed_payload_bytes()


def test_agent_and_witness_payloads_cannot_be_confused() -> None:
    w = WitnessEvent.model_validate(_load("03_honest_claim.json")["witness_events"][0])
    assert b'"kind":"WITNESS_EVENT"' in w.signed_payload_bytes()


# --- enum values are frozen ------------------------------------------------


@pytest.mark.parametrize(
    ("enum", "values"),
    [
        (TopologyName, {"HIERARCHICAL", "FUNCTIONAL_CELL", "DISTRIBUTED"}),
        (EventType, {"TASK_STARTED", "TASK_COMPLETE_CLAIM", "REWARD_CLAIM", "WITNESS_TRANSITION", "GRAPH_PATCH"}),
        (EventStatus, {"AUTHENTICATED", "REJECTED", "STALE", "DUPLICATE", "PROVISIONAL", "DISPUTED", "CORROBORATED"}),
        (EpisodeStatus, {"ADMITTED", "PROVISIONAL", "REJECTED"}),
        (
            TaskState,
            {"OPEN", "ASSIGNED", "EXECUTING", "REPORTED_COMPLETE", "VERIFIED_COMPLETE", "BLOCKED", "FAILED"},
        ),
        (RewardSource, {"ACP_RECOMPUTED", "AGENT_CLAIM"}),
    ],
)
def test_enum_values_frozen(enum: type[StrEnum], values: set[str]) -> None:
    assert {m.value for m in enum} == values
    assert all(m.name == m.value for m in enum)


# --- canonical encoding rules ---------------------------------------------


def test_canonical_sorted_compact_utf8() -> None:
    assert canonical_bytes({"b": 1, "a": "é"}) == '{"a":"é","b":1}'.encode()


def test_canonical_datetime_normalised_to_utc() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    a = datetime(2026, 1, 1, 5, 30, tzinfo=ist)
    b = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert canonical_json(a) == canonical_json(b) == '"2026-01-01T00:00:00.000000+00:00"'


@pytest.mark.parametrize("bad", [datetime(2026, 1, 1), math.nan, math.inf, {1: "x"}, object()])
def test_canonical_rejects_ambiguous(bad: object) -> None:
    with pytest.raises(CanonicalisationError):
        canonical_bytes(bad)


def test_canonical_floats() -> None:
    assert canonical_json(-0.0) == "0.0"
    assert canonical_json(0.1 + 0.2) == "0.3"
    assert canonical_json(1.0000000004) == "1.0"
    assert canonical_json(True) == "true" and canonical_json(3) == "3"


def test_canonical_enums_tuples_sets() -> None:
    assert canonical_json({"t": TopologyName.DISTRIBUTED, "x": (1, 2), "s": {"b", "a"}}) == (
        '{"s":["a","b"],"t":"DISTRIBUTED","x":[1,2]}'
    )


# --- model rules -----------------------------------------------------------


def _claim(**overrides: object) -> AgentEvent:
    base = dict(
        event_id="e", mission_id="m", epoch=1, seq=0, event_type=EventType.TASK_COMPLETE_CLAIM,
        task_id="T1", issued_at=datetime(2026, 1, 1, tzinfo=UTC), key_id="k", agent_id="A1",
    )
    return AgentEvent(**{**base, **overrides})


def test_event_rules() -> None:
    with pytest.raises(ValidationError):
        _claim(task_id=None)
    with pytest.raises(ValidationError):
        _claim(issued_at=datetime(2026, 1, 1))  # naive
    with pytest.raises(ValidationError):
        _claim(payload={"x": math.nan})
    with pytest.raises(ValidationError):
        _claim(unexpected="field")
    assert _claim().dedupe_key == ("m", 1, "A1", 0)
    with pytest.raises(ValidationError):
        _claim().seq = 2  # frozen


def test_decision_rules() -> None:
    kw = dict(decision_id="d", event_id="e", mission_id="m", epoch=1, signer_id="A1",
              event_type=EventType.TASK_COMPLETE_CLAIM)
    with pytest.raises(ValidationError):
        EventDecision(**kw, status=EventStatus.REJECTED)
    with pytest.raises(ValidationError):
        EventDecision(**kw, status=EventStatus.CORROBORATED)
    EventDecision(**kw, status=EventStatus.CORROBORATED, corroborating_event_ids=("w-1",))


def _episode(**overrides: object) -> EpisodeRecord:
    base = dict(episode_id="ep", mission_id="m", epoch=1, topology_decision_id="td",
                topology=TopologyName.HIERARCHICAL, plan_id="p", status=EpisodeStatus.ADMITTED,
                reward=0.5, reward_schema_version="rew-v1")
    return EpisodeRecord(**{**base, **overrides})


def test_episode_reward_iff_admitted() -> None:
    _episode()
    with pytest.raises(ValidationError):
        _episode(reward=None)
    with pytest.raises(ValidationError):
        _episode(reward=1.5)
    with pytest.raises(ValidationError):
        _episode(status=EpisodeStatus.PROVISIONAL, reason_codes=(ReasonCode.NO_WITNESS_EVIDENCE,))
    _episode(status=EpisodeStatus.PROVISIONAL, reward=None, reward_schema_version=None,
             reason_codes=(ReasonCode.NO_WITNESS_EVIDENCE,))
    with pytest.raises(ValidationError):
        _episode(status=EpisodeStatus.REJECTED, reward=None)  # needs a reason


def _learning(**overrides: object) -> LearningEvent:
    base = dict(event_id="le", episode_id="ep", decision_id="td", topology=TopologyName.DISTRIBUTED,
                feature_schema_version="ctx-v1", context=(1.0, 0.25, 0.5, 0.1, 1.0), reward=0.7,
                reward_source=RewardSource.ACP_RECOMPUTED, status=EpisodeStatus.ADMITTED)
    return LearningEvent(**{**base, **overrides})


def test_learning_gate() -> None:
    assert _learning().require_protected_eligible() == 0.7
    for status in (EpisodeStatus.PROVISIONAL, EpisodeStatus.REJECTED):
        with pytest.raises(IneligibleLearningEvent) as exc:
            _learning(status=status).require_protected_eligible()
        assert exc.value.reason is ReasonCode.INELIGIBLE_STATUS
    with pytest.raises(IneligibleLearningEvent) as exc:
        _learning(reward_source=RewardSource.AGENT_CLAIM).require_protected_eligible()
    assert exc.value.reason is ReasonCode.UNTRUSTED_REWARD_SOURCE
    with pytest.raises(ValidationError):
        _learning(reward=None)
    with pytest.raises(ValidationError):
        _learning(context=(1.0, math.inf))
