"""Canonical byte encoding for signing and hashing.

``canonical_bytes`` is the single serialisation used for every signature and
payload hash in SAMG. Never reconstruct an "equivalent" dict for verification;
call ``model.signed_payload_bytes()`` instead.

Encoding rules (``canon-v1``, frozen at G0 — changing them breaks the golden
signature test on purpose):

* JSON, UTF-8, keys sorted, ``separators=(",", ":")``, ``ensure_ascii=False``.
* Enums are encoded as their ``.value``.
* Datetimes must be timezone-aware; they are converted to UTC and written as
  ISO-8601 with microsecond precision and a ``+00:00`` offset.
* Floats must be finite. They are rounded to ``FLOAT_DECIMALS`` (9) decimal
  places, ``-0.0`` becomes ``0.0``, then written with Python's shortest
  round-trip ``repr``. Integers and booleans are written unchanged.
* Tuples become lists; sets/frozensets become sorted lists; UUIDs become strings.
* Mapping keys must be strings. Any other type raises ``CanonicalisationError``.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

CANONICAL_VERSION = "canon-v1"
FLOAT_DECIMALS = 9


class CanonicalisationError(ValueError):
    """Raised when a value cannot be encoded deterministically."""


def _normalise(value: Any, path: str) -> Any:
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, Enum):
        return _normalise(value.value, path)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalisationError(f"non-finite float at {path}")
        rounded = round(value, FLOAT_DECIMALS)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalisationError(f"naive datetime at {path}")
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, BaseModel):
        return _normalise(value.model_dump(mode="python"), path)
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, Enum):
                key = key.value
            if not isinstance(key, str):
                raise CanonicalisationError(f"non-string key {key!r} at {path}")
            out[key] = _normalise(item, f"{path}.{key}")
        return out
    if isinstance(value, list | tuple):
        return [_normalise(item, f"{path}[{i}]") for i, item in enumerate(value)]
    if isinstance(value, set | frozenset):
        items = [_normalise(item, f"{path}{{}}") for item in value]
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True))
    raise CanonicalisationError(f"unsupported type {type(value).__name__} at {path}")


def canonical_json(value: Any) -> str:
    """Return the canonical JSON text for a model, mapping, or JSON-like value."""
    return json.dumps(
        _normalise(value, "$"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(value: Any) -> bytes:
    """Return the canonical UTF-8 bytes for a model, mapping, or JSON-like value."""
    return canonical_json(value).encode("utf-8")


def canonical_hash(value: Any) -> str:
    """Return the hex SHA-256 of ``canonical_bytes(value)``."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
