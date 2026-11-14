"""Ed25519 signing and verification over ``signed_payload_bytes()``.

Verification answers only "did the registered key for this signer sign these
exact bytes?" It says nothing about whether the claim is true.
"""

from __future__ import annotations

import base64
import binascii
from typing import TypeVar

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from samg.assurance.identity import IdentityRegistry, KeyRing
from samg.domain.enums import ReasonCode
from samg.domain.events import AgentEvent, WitnessEvent

SignedEvent = AgentEvent | WitnessEvent
E = TypeVar("E", AgentEvent, WitnessEvent)

_SIGNATURE_LEN = 64


def encode_signature(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_signature(text: str) -> bytes | None:
    """Strictly decode URL-safe base64; return ``None`` if malformed or wrong length."""
    try:
        raw = base64.b64decode(text.encode("ascii"), altchars=b"-_", validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError):
        return None
    return raw if len(raw) == _SIGNATURE_LEN else None


def sign_event(event: E, private_key: Ed25519PrivateKey) -> E:
    """Return a copy of ``event`` carrying an Ed25519 signature of its payload bytes."""
    return event.with_signature(encode_signature(private_key.sign(event.signed_payload_bytes())))


def sign_with_ring(event: E, ring: KeyRing) -> E:
    """Sign ``event`` with the private key registered under ``event.key_id``."""
    return sign_event(event, ring.private_key(event.key_id))


def verify_event(event: SignedEvent, registry: IdentityRegistry) -> ReasonCode | None:
    """Return ``None`` if authentic, else the ``ReasonCode`` explaining the rejection.

    Checks, in order: signature present/decodable, key registered, key belongs
    to the claimed signer, identity active, Ed25519 verification.
    """
    if event.signature is None:
        return ReasonCode.MALFORMED
    raw = decode_signature(event.signature)
    if raw is None:
        return ReasonCode.MALFORMED
    identity = registry.by_key_id(event.key_id)
    if identity is None:
        return ReasonCode.UNKNOWN_KEY
    if identity.identity_id != event.signer_id:
        return ReasonCode.KEY_AGENT_MISMATCH
    if not identity.active:
        return ReasonCode.INACTIVE_IDENTITY
    try:
        identity.public_key().verify(raw, event.signed_payload_bytes())
    except InvalidSignature:
        return ReasonCode.BAD_SIGNATURE
    return None
