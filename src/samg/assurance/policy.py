"""Typed loader for ``config/security_policy.yaml``."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from samg.domain.enums import EventType, IdentityRole, RewardSource

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[3] / "config" / "security_policy.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WitnessConfig(_Strict):
    identity_id: str = Field(min_length=1)


class FreshnessConfig(_Strict):
    dedupe_key: tuple[str, ...]
    max_clock_skew_seconds: float = Field(ge=0)
    max_event_age_seconds: float = Field(gt=0)


class CorroborationConfig(_Strict):
    evidence_tolerance_seconds: float = Field(ge=0)
    metric_relative_tolerance: float = Field(ge=0)


class AdmissionConfig(_Strict):
    require_witness_for_reward_critical: bool
    quarantine_disputed_claims: bool
    reward_source: Literal[RewardSource.ACP_RECOMPUTED]


class SecurityPolicy(_Strict):
    version: str
    key_derivation: str
    witness: WitnessConfig
    roles: dict[IdentityRole, frozenset[EventType]]
    freshness: FreshnessConfig
    corroboration: CorroborationConfig
    admission: AdmissionConfig

    def allows(self, role: IdentityRole, event_type: EventType) -> bool:
        return event_type in self.roles.get(role, frozenset())


def load_security_policy(path: str | Path | None = None) -> SecurityPolicy:
    """Load and validate the security policy YAML (default: repo ``config/``)."""
    import yaml  # local import: only config loading needs PyYAML

    with Path(path or DEFAULT_POLICY_PATH).open(encoding="utf-8") as fh:
        return SecurityPolicy.model_validate(yaml.safe_load(fh))
