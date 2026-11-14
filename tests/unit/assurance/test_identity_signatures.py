"""Unit tests for deterministic identities, Ed25519 signing and the security policy."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from samg.assurance.identity import (
    Identity,
    IdentityRegistry,
    KeyRing,
    build_identities,
    derive_private_key,
)
from samg.assurance.signatures import decode_signature, sign_with_ring, verify_event
from samg.domain import AgentEvent, EventType, IdentityRole, ReasonCode, TaskState, WitnessEvent

ROLES = {"A0": IdentityRole.COORDINATOR, "A1": IdentityRole.AGENT, "W": IdentityRole.WITNESS}


def _setup(seed: int = 7) -> tuple[IdentityRegistry, KeyRing]:
    return build_identities(seed, ROLES)


def _claim(registry: IdentityRegistry, agent: str = "A1", **kw: object) -> AgentEvent:
    identity = registry.by_identity_id(agent)
    assert identity
    base = dict(event_id="e1", mission_id="m", epoch=1, seq=0, event_type=EventType.TASK_COMPLETE_CLAIM,
                task_id="T1", issued_at=datetime(2026, 1, 1, tzinfo=UTC), key_id=identity.key_id, agent_id=agent)
    return AgentEvent(**{**base, **kw})


def test_key_derivation_deterministic_and_seed_sensitive() -> None:
    raw = lambda k: k.private_bytes_raw()  # noqa: E731
    assert raw(derive_private_key(7, "A1")) == raw(derive_private_key(7, "A1"))
    assert raw(derive_private_key(7, "A1")) != raw(derive_private_key(8, "A1"))
    assert raw(derive_private_key(7, "A1")) != raw(derive_private_key(7, "A0"))


def test_build_identities_order_independent() -> None:
    r1, _ = build_identities(7, ROLES)
    r2, _ = build_identities(7, dict(reversed(list(ROLES.items()))))
    assert r1.identities() == r2.identities()


def test_identity_has_no_private_material() -> None:
    registry, ring = _setup()
    assert set(Identity.model_fields) == {"identity_id", "key_id", "role", "public_key_b64", "active"}
    assert repr(ring) == "KeyRing(<3 keys>)"  # never exposes key material
    assert "private" not in " ".join(i.model_dump_json() for i in registry.identities()).lower()


def test_registry_rejects_duplicates() -> None:
    registry, _ = _setup()
    with pytest.raises(ValueError):
        registry.register(registry.identities()[0])


def test_sign_and_verify_roundtrip() -> None:
    registry, ring = _setup()
    claim = sign_with_ring(_claim(registry), ring)
    assert verify_event(claim, registry) is None
    witness_id = registry.by_identity_id("W")
    assert witness_id
    w = sign_with_ring(
        WitnessEvent(event_id="w0", mission_id="m", epoch=1, seq=0, task_id="T1",
                     issued_at=datetime(2026, 1, 1, tzinfo=UTC), key_id=witness_id.key_id, witness_id="W",
                     from_state=TaskState.EXECUTING, to_state=TaskState.VERIFIED_COMPLETE, sim_time_ms=10),
        ring,
    )
    assert verify_event(w, registry) is None


def test_tampered_payload_fails() -> None:
    registry, ring = _setup()
    signed = sign_with_ring(_claim(registry), ring)
    tampered = signed.model_copy(update={"task_id": "T9"})
    assert verify_event(tampered, registry) is ReasonCode.BAD_SIGNATURE


def test_unsigned_and_malformed_signatures() -> None:
    registry, ring = _setup()
    assert verify_event(_claim(registry), registry) is ReasonCode.MALFORMED
    signed = sign_with_ring(_claim(registry), ring)
    for bad in ["", "not base64!!", signed.signature[:-4], "A" * 88]:  # type: ignore[index]
        result = verify_event(signed.with_signature(bad), registry)
        assert result in {ReasonCode.MALFORMED, ReasonCode.BAD_SIGNATURE}, bad
    assert decode_signature("not base64!!") is None


def test_unknown_key_and_key_agent_mismatch() -> None:
    registry, ring = _setup()
    other_registry, other_ring = build_identities(99, ROLES)
    foreign = sign_with_ring(_claim(other_registry), other_ring)
    assert verify_event(foreign, registry) is ReasonCode.UNKNOWN_KEY

    # A0 signs with its own key but claims to be A1.
    a0 = registry.by_identity_id("A0")
    assert a0
    impersonation = sign_with_ring(_claim(registry, key_id=a0.key_id), ring)
    assert verify_event(impersonation, registry) is ReasonCode.KEY_AGENT_MISMATCH


def test_inactive_identity_rejected() -> None:
    registry, ring = _setup()
    signed = sign_with_ring(_claim(registry), ring)
    a1 = registry.by_identity_id("A1")
    assert a1
    inactive = IdentityRegistry(
        [i if i.identity_id != "A1" else i.model_copy(update={"active": False}) for i in registry.identities()]
    )
    assert verify_event(signed, inactive) is ReasonCode.INACTIVE_IDENTITY


def test_security_policy_loads() -> None:
    pytest.importorskip("yaml")
    from samg.assurance.policy import load_security_policy

    policy = load_security_policy()
    assert policy.witness.identity_id == "WITNESS-0"
    assert policy.allows(IdentityRole.WITNESS, EventType.WITNESS_TRANSITION)
    assert not policy.allows(IdentityRole.AGENT, EventType.WITNESS_TRANSITION)
    assert not policy.allows(IdentityRole.AGENT, EventType.GRAPH_PATCH)
    assert policy.allows(IdentityRole.COORDINATOR, EventType.GRAPH_PATCH)
    assert policy.freshness.dedupe_key == ("mission_id", "epoch", "signer_id", "seq")
