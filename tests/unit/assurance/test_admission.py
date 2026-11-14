"""ACP admission against the shared contract fixtures (integration version)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from samg.allocation import allocate
from samg.assurance.admission import admit_episode, open_session, validate_event
from samg.assurance.freshness import InMemorySeenStore
from samg.assurance.identity import Identity, IdentityRegistry, build_identities
from samg.assurance.policy import load_security_policy
from samg.assurance.signatures import sign_with_ring
from samg.domain import (
    AgentEvent,
    AgentProfile,
    EpisodeStatus,
    EventStatus,
    IdentityRole,
    MissionSpec,
    ReasonCode,
    RewardConfig,
    Scenario,
    TaskState,
    TopologyCostConfig,
    TopologyName,
    WitnessEvent,
)
from samg.topology import build_graph

FIXTURES = Path(__file__).resolve().parents[2] / "contract" / "fixtures"
POLICY = load_security_policy()


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _setup():
    fx = _load("01_reachable_mission.json")
    mission = MissionSpec.model_validate(fx["mission"])
    scenario = Scenario(scenario_id="fx", seed=7, mission=mission,
                        agents=tuple(AgentProfile.model_validate(a) for a in fx["agents"]),
                        permitted_links=tuple(tuple(x) for x in fx["permitted_links"]))
    _, graph = build_graph(scenario, TopologyName.DISTRIBUTED)
    plan = allocate(scenario, graph)
    assert plan.assignee("T1") == "A0" and plan.assignee("T2") == "A1"
    return scenario, graph, plan


def _registry(fixture: dict) -> IdentityRegistry:
    return IdentityRegistry(Identity.model_validate(i) for i in fixture["identities"])


def _assigned_prefix(fixture: dict) -> WitnessEvent:
    """Fixtures start at ASSIGNED; add the witness OPEN -> ASSIGNED for T2 with the fixture witness key."""
    registry, ring = build_identities(7, {"A0": IdentityRole.COORDINATOR, "A1": IdentityRole.AGENT,
                                          "WITNESS-0": IdentityRole.WITNESS})
    assert registry.by_identity_id("WITNESS-0").key_id == _registry(fixture).by_identity_id("WITNESS-0").key_id
    first = WitnessEvent.model_validate(fixture["witness_events"][0])
    return sign_with_ring(WitnessEvent(
        event_id="w-pre", mission_id=first.mission_id, epoch=first.epoch, seq=99, task_id="T2",
        issued_at=first.issued_at - timedelta(milliseconds=500), key_id=first.key_id, witness_id="WITNESS-0",
        from_state=TaskState.OPEN, to_state=TaskState.ASSIGNED, sim_time_ms=500), ring)


def _run(fixture_name: str):
    fixture = _load(fixture_name)
    scenario, graph, plan = _setup()
    session = open_session(scenario, plan, _registry(fixture), POLICY, InMemorySeenStore())
    events = [_assigned_prefix(fixture)] + [WitnessEvent.model_validate(w) for w in fixture["witness_events"]]
    events += [AgentEvent.model_validate(a) for a in fixture["agent_events"]]
    received = [(e, validate_event(session, e, now=e.issued_at)) for e in events]
    admission = admit_episode(session, received, graph=graph, episode_id="ep", topology_decision_id="dec",
                              reward_config=RewardConfig(), costs=TopologyCostConfig())
    auth = {e.event_id: d for e, d in received}
    final = {d.event_id: d for d in admission.final_decisions}
    return fixture, auth, final, admission


@pytest.mark.parametrize("name", ["03_honest_claim.json", "04_false_signed_claim.json"])
def test_fixture_expectations(name: str) -> None:
    fixture, auth, final, _ = _run(name)
    for event_id, expected in fixture["expected"].items():
        assert auth[event_id].status.value == expected["auth"]
        assert final[event_id].status.value == expected["corroboration"], final[event_id]


def test_false_claim_cites_contradicting_witness() -> None:
    _, _, final, admission = _run("04_false_signed_claim.json")
    assert ReasonCode.WITNESS_CONTRADICTS in final["a1-claim-0"].reason_codes
    assert ReasonCode.REWARD_CLAIM_NOT_TRUSTED in final["a1-reward-1"].reason_codes
    # T1 has no witness evidence, so the episode cannot be admitted and carries no reward.
    assert admission.episode.status is EpisodeStatus.PROVISIONAL
    assert admission.episode.reward is None
    assert ReasonCode.DISPUTED_CLAIM_QUARANTINED in admission.episode.reason_codes


def test_replay_fixture_order() -> None:
    fixture = _load("05_replayed_event.json")
    scenario, _, plan = _setup()
    session = open_session(scenario, plan, _registry(fixture), POLICY, InMemorySeenStore())
    got = []
    for raw in fixture["agent_events"]:
        e = AgentEvent.model_validate(raw)
        d = validate_event(session, e, now=e.issued_at)
        got.append({"event_id": e.event_id, "status": d.status.value,
                    "reason": d.reason_codes[0].value if d.reason_codes else None})
    assert got == fixture["expected_in_order"]


def test_tampered_and_unauthorised_events_rejected() -> None:
    fixture = _load("03_honest_claim.json")
    scenario, _, plan = _setup()
    session = open_session(scenario, plan, _registry(fixture), POLICY, InMemorySeenStore())
    claim = AgentEvent.model_validate(fixture["agent_events"][0])
    tampered = claim.model_copy(update={"task_id": "T1"})
    assert validate_event(session, tampered, now=claim.issued_at).reason_codes == (ReasonCode.BAD_SIGNATURE,)
    # A witness-only event type signed by an agent key: authentic but unauthorised.
    registry, ring = build_identities(7, {"A0": IdentityRole.COORDINATOR, "A1": IdentityRole.AGENT,
                                          "WITNESS-0": IdentityRole.WITNESS})
    forged = sign_with_ring(WitnessEvent(
        event_id="fake-w", mission_id=claim.mission_id, epoch=claim.epoch, seq=0, task_id="T2",
        issued_at=claim.issued_at, key_id=registry.by_identity_id("A1").key_id, witness_id="A1",
        from_state=TaskState.EXECUTING, to_state=TaskState.VERIFIED_COMPLETE, sim_time_ms=2600), ring)
    d = validate_event(session, forged, now=claim.issued_at)
    assert d.status is EventStatus.REJECTED and d.reason_codes == (ReasonCode.UNAUTHORISED_EVENT_TYPE,)
    # Neither attempt burned a sequence number: the genuine claim is still fresh.
    assert validate_event(session, claim, now=claim.issued_at).status is EventStatus.AUTHENTICATED
