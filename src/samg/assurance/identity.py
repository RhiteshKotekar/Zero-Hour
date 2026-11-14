"""Simulated identities: deterministic Ed25519 keys and a public-key registry.

Private keys live only in a ``KeyRing`` held in simulation memory. The
``IdentityRegistry`` (which may be persisted) holds public material only.

Key derivation (``sha256-seed-v1``): the 32-byte Ed25519 seed for identity
``i`` under scenario seed ``s`` is ``SHA-256("samg-ed25519-v1|{s}|{i}")``.
It is order-independent, so adding an agent never changes other agents' keys.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterable, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import BaseModel, ConfigDict, Field

from samg.domain.enums import IdentityRole

KEY_DERIVATION_VERSION = "sha256-seed-v1"


def derive_private_key(seed: int, identity_id: str) -> Ed25519PrivateKey:
    """Derive the simulation private key for ``identity_id`` from a scenario ``seed``."""
    material = hashlib.sha256(f"samg-ed25519-v1|{seed}|{identity_id}".encode()).digest()
    return Ed25519PrivateKey.from_private_bytes(material)


def public_key_bytes(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def key_id_for(identity_id: str, public_key: Ed25519PublicKey) -> str:
    """Stable key id: identity id plus a 12-hex-digit public-key fingerprint."""
    fingerprint = hashlib.sha256(public_key_bytes(public_key)).hexdigest()[:12]
    return f"{identity_id}#{fingerprint}"


class Identity(BaseModel):
    """Public, persistable identity record. Never contains private key material."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    identity_id: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    role: IdentityRole
    public_key_b64: str = Field(min_length=1, description="URL-safe base64 raw Ed25519 key")
    active: bool = True

    def public_key(self) -> Ed25519PublicKey:
        return Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(self.public_key_b64))


class IdentityRegistry:
    """Lookup of registered public keys by ``key_id`` and by identity id."""

    def __init__(self, identities: Iterable[Identity] = ()) -> None:
        self._by_key: dict[str, Identity] = {}
        self._by_identity: dict[str, Identity] = {}
        for identity in identities:
            self.register(identity)

    def register(self, identity: Identity) -> None:
        if identity.key_id in self._by_key:
            raise ValueError(f"duplicate key_id {identity.key_id}")
        if identity.identity_id in self._by_identity:
            raise ValueError(f"identity {identity.identity_id} already registered")
        self._by_key[identity.key_id] = identity
        self._by_identity[identity.identity_id] = identity

    def by_key_id(self, key_id: str) -> Identity | None:
        return self._by_key.get(key_id)

    def by_identity_id(self, identity_id: str) -> Identity | None:
        return self._by_identity.get(identity_id)

    def identities(self) -> list[Identity]:
        return sorted(self._by_identity.values(), key=lambda i: i.identity_id)


class KeyRing:
    """In-memory private keys for simulated signers. Must never be persisted or logged."""

    def __init__(self) -> None:
        self._keys: dict[str, Ed25519PrivateKey] = {}

    def add(self, key_id: str, private_key: Ed25519PrivateKey) -> None:
        self._keys[key_id] = private_key

    def private_key(self, key_id: str) -> Ed25519PrivateKey:
        return self._keys[key_id]

    def __contains__(self, key_id: object) -> bool:
        return key_id in self._keys

    def __repr__(self) -> str:  # avoid leaking key material in logs/tracebacks
        return f"KeyRing(<{len(self._keys)} keys>)"


def build_identities(
    seed: int, roles: Mapping[str, IdentityRole]
) -> tuple[IdentityRegistry, KeyRing]:
    """Create a registry and key ring for ``{identity_id: role}`` under ``seed``.

    Identities are processed in sorted id order, so output is deterministic.
    """
    registry = IdentityRegistry()
    ring = KeyRing()
    for identity_id in sorted(roles):
        private = derive_private_key(seed, identity_id)
        public = private.public_key()
        key_id = key_id_for(identity_id, public)
        registry.register(
            Identity(
                identity_id=identity_id,
                key_id=key_id,
                role=roles[identity_id],
                public_key_b64=base64.urlsafe_b64encode(public_key_bytes(public)).decode(),
            )
        )
        ring.add(key_id, private)
    return registry, ring
