"""Fixed-topology baselines (P0-H/F/D) and the best-fixed-on-training helper (P1)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import fmean
from typing import Any, Self

from samg.domain.enums import ReasonCode, TopologyName
from samg.domain.events import LearningEvent
from samg.learning.base import ARM_ORDER, PolicyDecision, ProtectedGate, ordered_eligible

POLICY_VERSION = "fixed-v1"


class FixedTopologyPolicy:
    """Always picks ``topology``; reports TOPOLOGY_NOT_ELIGIBLE rather than substituting."""

    def __init__(self, topology: TopologyName, *, kind: str | None = None) -> None:
        self.topology = topology
        self.kind = kind or f"P0-{topology.value}"
        self.gate = ProtectedGate()

    def select(
        self,
        context: Sequence[float],
        eligible: Sequence[TopologyName],
        feature_schema_version: str,
    ) -> PolicyDecision:
        arms = ordered_eligible(eligible)
        ok = self.topology in arms
        return PolicyDecision(
            policy_kind=self.kind, policy_version=POLICY_VERSION,
            topology=self.topology if ok else None, eligible=arms,
            feature_schema_version=feature_schema_version,
            context=tuple(float(v) for v in context),
            scores={self.topology: 1.0},
            reason_codes=() if ok else (ReasonCode.TOPOLOGY_NOT_ELIGIBLE,),
        )

    def observe(self, event: LearningEvent) -> None:
        """No state to update, but the gate is still enforced so misuse is visible."""
        self.gate.admit(event)
        self.gate.mark_applied(event)

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "policy_version": POLICY_VERSION,
            "topology": self.topology.value,
            "applied_episodes": sorted(self.gate.applied_episodes),
        }

    @classmethod
    def from_snapshot(cls, state: dict[str, Any]) -> Self:
        policy = cls(TopologyName(state["topology"]), kind=state["kind"])
        policy.gate = ProtectedGate(state["applied_episodes"])
        return policy


def best_fixed_from_training(rewards: Mapping[TopologyName, Sequence[float]]) -> TopologyName:
    """P1: the topology with the highest mean training reward (ties → ``ARM_ORDER``)."""
    means = {arm: fmean(rewards[arm]) for arm in ARM_ORDER if rewards.get(arm)}
    if not means:
        raise ValueError("no training rewards supplied")
    best = max(means.values())
    return next(arm for arm in ARM_ORDER if arm in means and means[arm] == best)
