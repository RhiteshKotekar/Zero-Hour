"""Generate the shared contract fixtures under ``tests/contract/fixtures/``.

Run deliberately (``python tests/contract/make_fixtures.py``) only after a
DECISIONS-level contract change. ``test_fixtures_are_current`` fails if the
committed files drift from what this script would produce.
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from samg.assurance.identity import IdentityRegistry, KeyRing, build_identities
from samg.assurance.signatures import sign_with_ring
from samg.domain import AgentEvent, EventType, IdentityRole, TaskState, WitnessEvent

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_SEED = 7
MISSION_ID = "fx-mission-1"
EPOCH = 1
T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
ROLES = {
    "A0": IdentityRole.COORDINATOR,
    "A1": IdentityRole.AGENT,
    "WITNESS-0": IdentityRole.WITNESS,
}


def _keys() -> tuple[IdentityRegistry, KeyRing]:
    return build_identities(FIXTURE_SEED, ROLES)


def _key(registry: IdentityRegistry, identity_id: str) -> str:
    identity = registry.by_identity_id(identity_id)
    assert identity is not None
    return identity.key_id


def _at(ms: int) -> datetime:
    return T0 + timedelta(milliseconds=ms)


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _mission(registry: IdentityRegistry, *, reachable: bool) -> dict[str, Any]:
    """Two agents, T1 -> T2, assigned to different agents so a handoff path is needed.

    Field names follow docs/THREE_PERSON_PLAN.md Phase 0 A3. Dev A's
    ``MissionSpec``/``AgentProfile`` must load ``mission`` / ``agents``.
    """
    return {
        "mission": {
            "mission_id": MISSION_ID if reachable else "fx-mission-2",
            "epoch": EPOCH,
            "deadline_ms": 10_000,
            "generator_version": "fixture-v1",
            "generator_params": {},
            "family": "fixture",
            "tasks": [
                {
                    "task_id": "T1",
                    "required_capabilities": ["sense"],
                    "duration_ms": 1_000,
                    "resource_demand": 1.0,
                    "priority_weight": 1.0,
                    "reward_critical": True,
                    "dependencies": [],
                },
                {
                    "task_id": "T2",
                    "required_capabilities": ["act"],
                    "duration_ms": 1_500,
                    "resource_demand": 1.0,
                    "priority_weight": 1.0,
                    "reward_critical": True,
                    "dependencies": ["T1"],
                },
            ],
        },
        "agents": [
            {
                "agent_id": "A0",
                "capabilities": ["sense"],
                "capacity": 2,
                "resource_budget": 5.0,
                "role": "sensing",
                "can_coordinate": reachable,
                "available": True,
                "public_key_id": _key(registry, "A0"),
            },
            {
                "agent_id": "A1",
                "capabilities": ["act"],
                "capacity": 2,
                "resource_budget": 5.0,
                "role": "action",
                "can_coordinate": False,
                "available": True,
                "public_key_id": _key(registry, "A1"),
            },
        ],
        # Physical/policy links available to any template. Fixture 2 has none and no
        # coordinator, so no topology can route the cross-agent T1 -> T2 handoff.
        "permitted_links": [["A0", "A1"], ["A1", "A0"]] if reachable else [],
        "expected": {
            "eligible_topologies": (
                ["DISTRIBUTED", "FUNCTIONAL_CELL", "HIERARCHICAL"] if reachable else []
            ),
            "cross_agent_dependency": ["T1", "T2"],
        },
    }


def _witness(
    registry: IdentityRegistry, ring: KeyRing, seq: int, task: str, frm: TaskState,
    to: TaskState, ms: int,
) -> WitnessEvent:
    return sign_with_ring(
        WitnessEvent(
            event_id=f"w-{seq}",
            mission_id=MISSION_ID,
            epoch=EPOCH,
            seq=seq,
            task_id=task,
            issued_at=_at(ms),
            key_id=_key(registry, "WITNESS-0"),
            witness_id="WITNESS-0",
            from_state=frm,
            to_state=to,
            sim_time_ms=ms,
        ),
        ring,
    )


def _claim(
    registry: IdentityRegistry, ring: KeyRing, *, event_id: str, seq: int,
    event_type: EventType = EventType.TASK_COMPLETE_CLAIM, task_id: str | None = "T2",
    payload: dict[str, Any] | None = None, ms: int = 2_600, epoch: int = EPOCH,
) -> AgentEvent:
    return sign_with_ring(
        AgentEvent(
            event_id=event_id,
            mission_id=MISSION_ID,
            epoch=epoch,
            seq=seq,
            event_type=event_type,
            task_id=task_id,
            issued_at=_at(ms),
            payload=payload or {},
            key_id=_key(registry, "A1"),
            agent_id="A1",
        ),
        ring,
    )


def _identities(registry: IdentityRegistry) -> list[dict[str, Any]]:
    return [_dump(i) for i in registry.identities()]


def build_all() -> dict[str, dict[str, Any]]:
    registry, ring = _keys()
    common = {"seed": FIXTURE_SEED, "active_epoch": EPOCH, "identities": _identities(registry)}
    S = TaskState

    honest_claim = _claim(registry, ring, event_id="a1-claim-0", seq=0)
    honest = {
        **common,
        "description": "Honest signed completion claim for T2 with matching witness events.",
        "witness_events": [
            _dump(_witness(registry, ring, 0, "T2", S.ASSIGNED, S.EXECUTING, 1_000)),
            _dump(_witness(registry, ring, 1, "T2", S.EXECUTING, S.VERIFIED_COMPLETE, 2_500)),
        ],
        "agent_events": [_dump(honest_claim)],
        "expected": {"a1-claim-0": {"auth": "AUTHENTICATED", "corroboration": "CORROBORATED"}},
        "golden": {
            "event_id": honest_claim.event_id,
            "signed_payload_b64": base64.urlsafe_b64encode(
                honest_claim.signed_payload_bytes()
            ).decode(),
            "signature": honest_claim.signature,
        },
    }

    false_claim = {
        **common,
        "description": (
            "A1 is authorised and signs correctly, but claims T2 complete and an inflated "
            "reward while the witness observed T2 FAILED."
        ),
        "witness_events": [
            _dump(_witness(registry, ring, 0, "T2", S.ASSIGNED, S.EXECUTING, 1_000)),
            _dump(_witness(registry, ring, 1, "T2", S.EXECUTING, S.FAILED, 2_000)),
        ],
        "agent_events": [
            _dump(_claim(registry, ring, event_id="a1-claim-0", seq=0)),
            _dump(
                _claim(
                    registry, ring, event_id="a1-reward-1", seq=1,
                    event_type=EventType.REWARD_CLAIM, task_id=None,
                    payload={"claimed_reward": 0.98, "attacker_preferred_topology": "DISTRIBUTED"},
                )
            ),
        ],
        "expected": {
            "a1-claim-0": {"auth": "AUTHENTICATED", "corroboration": "DISPUTED"},
            "a1-reward-1": {"auth": "AUTHENTICATED", "corroboration": "DISPUTED"},
        },
    }

    original = _claim(registry, ring, event_id="a1-claim-0", seq=0)
    replay = {
        **common,
        "description": (
            "Replay cases, processed in order: original, exact resend, new event id reusing "
            "seq 0, and a correctly signed event from an obsolete epoch."
        ),
        "witness_events": [],
        "agent_events": [
            _dump(original),
            _dump(original),
            _dump(_claim(registry, ring, event_id="a1-claim-0b", seq=0, task_id="T1")),
            _dump(_claim(registry, ring, event_id="a1-old-epoch", seq=5, epoch=EPOCH - 1)),
        ],
        "expected_in_order": [
            {"event_id": "a1-claim-0", "status": "AUTHENTICATED", "reason": None},
            {"event_id": "a1-claim-0", "status": "DUPLICATE", "reason": "DUPLICATE_EVENT_ID"},
            {"event_id": "a1-claim-0b", "status": "DUPLICATE", "reason": "DUPLICATE_SEQUENCE"},
            {"event_id": "a1-old-epoch", "status": "STALE", "reason": "OBSOLETE_EPOCH"},
        ],
    }

    return {
        "01_reachable_mission.json": _mission(registry, reachable=True),
        "02_unreachable_mission.json": _mission(registry, reachable=False),
        "03_honest_claim.json": honest,
        "04_false_signed_claim.json": false_claim,
        "05_replayed_event.json": replay,
    }


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in build_all().items():
        (FIXTURE_DIR / name).write_text(render(data), encoding="utf-8")
        print(f"wrote {FIXTURE_DIR / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
