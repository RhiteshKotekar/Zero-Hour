"""Disjoint LinUCB over topology arms (P3), with a protected update gate.

    A[a] = lambda * I,  b[a] = 0
    theta[a] = solve(A[a], b[a])
    score[a] = theta[a]^T x + alpha * sqrt(x^T solve(A[a], x))
    on an admitted reward r for arm a:  A[a] += x x^T,  b[a] += r x
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Self

import numpy as np

from samg.domain.enums import ReasonCode, TopologyName
from samg.domain.events import IneligibleLearningEvent, LearningEvent
from samg.learning.base import (
    ARM_ORDER,
    PolicyDecision,
    ProtectedGate,
    argmax_by_arm_order,
    ordered_eligible,
)

POLICY_VERSION = "linucb-v1"


class LinUCBPolicy:
    """Protected LinUCB. ``observe`` accepts only ADMITTED, ACP-recomputed episodes."""

    kind = "P3-LinUCB"

    def __init__(
        self,
        *,
        dim: int = 5,
        alpha: float = 1.0,
        lam: float = 1.0,
        seed: int = 0,
        warmup_per_arm: int = 1,
        feature_schema_version: str = "ctx-v1",
    ) -> None:
        if dim < 1 or alpha < 0 or lam <= 0 or warmup_per_arm < 0:
            raise ValueError("invalid LinUCB hyperparameters")
        self.dim = dim
        self.alpha = float(alpha)
        self.lam = float(lam)
        self.seed = seed
        self.warmup_per_arm = warmup_per_arm
        self.feature_schema_version = feature_schema_version
        perm = np.random.default_rng(seed).permutation(len(ARM_ORDER))
        self.warmup_order: tuple[TopologyName, ...] = tuple(ARM_ORDER[i] for i in perm)
        self.A: dict[TopologyName, np.ndarray] = {a: self.lam * np.eye(dim) for a in ARM_ORDER}
        self.b: dict[TopologyName, np.ndarray] = {a: np.zeros(dim) for a in ARM_ORDER}
        self.selections: dict[TopologyName, int] = {a: 0 for a in ARM_ORDER}
        self.updates: dict[TopologyName, int] = {a: 0 for a in ARM_ORDER}
        self.gate = ProtectedGate()

    # --- selection ---------------------------------------------------------

    def _vector(self, context: Sequence[float], schema: str) -> np.ndarray:
        if schema != self.feature_schema_version:
            raise ValueError(
                f"{ReasonCode.CONTEXT_SCHEMA_MISMATCH.value}: {schema} != {self.feature_schema_version}"
            )
        x = np.asarray(context, dtype=float)
        if x.shape != (self.dim,) or not np.all(np.isfinite(x)):
            raise ValueError(f"{ReasonCode.CONTEXT_SCHEMA_MISMATCH.value}: bad context shape/values")
        return x

    def theta(self, arm: TopologyName) -> np.ndarray:
        return np.linalg.solve(self.A[arm], self.b[arm])

    def arm_scores(self, x: np.ndarray) -> tuple[dict, dict, dict]:
        means, bonuses, scores = {}, {}, {}
        for arm in ARM_ORDER:
            mean = float(self.theta(arm) @ x)
            bonus = self.alpha * math.sqrt(max(float(x @ np.linalg.solve(self.A[arm], x)), 0.0))
            means[arm], bonuses[arm], scores[arm] = mean, bonus, mean + bonus
        return means, bonuses, scores

    def select(
        self,
        context: Sequence[float],
        eligible: Sequence[TopologyName],
        feature_schema_version: str,
    ) -> PolicyDecision:
        x = self._vector(context, feature_schema_version)
        arms = ordered_eligible(eligible)
        means, bonuses, scores = self.arm_scores(x)
        common = dict(
            policy_kind=self.kind, policy_version=POLICY_VERSION, eligible=arms,
            feature_schema_version=feature_schema_version, context=tuple(float(v) for v in x),
            scores=scores, means=means, bonuses=bonuses,
        )
        if not arms:
            return PolicyDecision(**common, topology=None, reason_codes=(ReasonCode.NO_ELIGIBLE_TOPOLOGY,))
        under = [a for a in self.warmup_order if a in arms and self.selections[a] < self.warmup_per_arm]
        if under:
            chosen, warmup = under[0], True
        else:
            chosen, warmup = argmax_by_arm_order({a: scores[a] for a in arms}), False
        self.selections[chosen] += 1
        return PolicyDecision(**common, topology=chosen, warmup=warmup)

    # --- learning ----------------------------------------------------------

    def _apply(self, event: LearningEvent, reward: float) -> None:
        x = self._vector(event.context, event.feature_schema_version)
        self.A[event.topology] = self.A[event.topology] + np.outer(x, x)
        self.b[event.topology] = self.b[event.topology] + reward * x
        self.updates[event.topology] += 1

    def observe(self, event: LearningEvent) -> None:
        """Update from an ADMITTED episode; raise ``IneligibleLearningEvent`` otherwise."""
        reward = self.gate.admit(event)
        self._apply(event, reward)
        self.gate.mark_applied(event)

    # --- state -------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """JSON-safe state for persistence and for cloning S1/S2 from one start state."""
        return {
            "kind": self.kind,
            "policy_version": POLICY_VERSION,
            "hyperparameters": {
                "dim": self.dim, "alpha": self.alpha, "lam": self.lam, "seed": self.seed,
                "warmup_per_arm": self.warmup_per_arm,
                "feature_schema_version": self.feature_schema_version,
            },
            "A": {a.value: self.A[a].tolist() for a in ARM_ORDER},
            "b": {a.value: self.b[a].tolist() for a in ARM_ORDER},
            "selections": {a.value: self.selections[a] for a in ARM_ORDER},
            "updates": {a.value: self.updates[a] for a in ARM_ORDER},
            "applied_episodes": sorted(self.gate.applied_episodes),
        }

    @classmethod
    def from_snapshot(cls, state: dict[str, Any]) -> Self:
        """Restore state. Restoring into a different LinUCB subclass is allowed (S1/S2 cloning)."""
        policy = cls(**state["hyperparameters"])
        for arm in ARM_ORDER:
            policy.A[arm] = np.array(state["A"][arm.value], dtype=float)
            policy.b[arm] = np.array(state["b"][arm.value], dtype=float)
            policy.selections[arm] = int(state["selections"][arm.value])
            policy.updates[arm] = int(state["updates"][arm.value])
        policy.gate = ProtectedGate(state["applied_episodes"])
        return policy

    def clone(self) -> Self:
        return type(self).from_snapshot(self.snapshot())


__all__ = ["LinUCBPolicy", "IneligibleLearningEvent", "POLICY_VERSION"]
