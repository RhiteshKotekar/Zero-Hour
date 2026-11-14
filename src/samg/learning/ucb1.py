"""Context-free UCB1 over topology arms (P2): ``mean + c * sqrt(2 ln N / n)``."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Self

from samg.domain.enums import ReasonCode, TopologyName
from samg.domain.events import LearningEvent
from samg.learning.base import ARM_ORDER, PolicyDecision, ProtectedGate, argmax_by_arm_order, ordered_eligible

POLICY_VERSION = "ucb1-v1"


class UCB1Policy:
    kind = "P2-UCB1"

    def __init__(self, *, c: float = 1.0, feature_schema_version: str = "ctx-v1") -> None:
        if c < 0:
            raise ValueError("c must be non-negative")
        self.c = float(c)
        self.feature_schema_version = feature_schema_version
        self.counts: dict[TopologyName, int] = {a: 0 for a in ARM_ORDER}
        self.sums: dict[TopologyName, float] = {a: 0.0 for a in ARM_ORDER}
        self.gate = ProtectedGate()

    def select(
        self,
        context: Sequence[float],
        eligible: Sequence[TopologyName],
        feature_schema_version: str,
    ) -> PolicyDecision:
        arms = ordered_eligible(eligible)
        total = max(sum(self.counts.values()), 1)
        means, bonuses, scores = {}, {}, {}
        for arm in ARM_ORDER:
            n = self.counts[arm]
            # Untried arms are chosen first (warm-up), so their score is never compared.
            means[arm] = self.sums[arm] / n if n else 0.0
            bonuses[arm] = self.c * math.sqrt(2 * math.log(total) / n) if n else 0.0
            scores[arm] = means[arm] + bonuses[arm]
        common = dict(
            policy_kind=self.kind, policy_version=POLICY_VERSION, eligible=arms,
            feature_schema_version=feature_schema_version, context=tuple(float(v) for v in context),
            scores=scores, means=means, bonuses=bonuses,
        )
        if not arms:
            return PolicyDecision(**common, topology=None, reason_codes=(ReasonCode.NO_ELIGIBLE_TOPOLOGY,))
        untried = [a for a in arms if self.counts[a] == 0]
        chosen = untried[0] if untried else argmax_by_arm_order({a: scores[a] for a in arms})
        return PolicyDecision(**common, topology=chosen, warmup=bool(untried))

    def observe(self, event: LearningEvent) -> None:
        reward = self.gate.admit(event)
        self.counts[event.topology] += 1
        self.sums[event.topology] += reward
        self.gate.mark_applied(event)

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "policy_version": POLICY_VERSION,
            "hyperparameters": {"c": self.c, "feature_schema_version": self.feature_schema_version},
            "counts": {a.value: self.counts[a] for a in ARM_ORDER},
            "sums": {a.value: self.sums[a] for a in ARM_ORDER},
            "applied_episodes": sorted(self.gate.applied_episodes),
        }

    @classmethod
    def from_snapshot(cls, state: dict[str, Any]) -> Self:
        policy = cls(**state["hyperparameters"])
        for arm in ARM_ORDER:
            policy.counts[arm] = int(state["counts"][arm.value])
            policy.sums[arm] = float(state["sums"][arm.value])
        policy.gate = ProtectedGate(state["applied_episodes"])
        return policy
