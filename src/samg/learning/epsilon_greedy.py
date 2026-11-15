"""Contextual epsilon-greedy topology selection (P4).

Each topology has the same ridge-linear reward model used by LinUCB. The
selection rule differs: after a balanced warm-up, choose the predicted best
eligible topology with probability ``1 - epsilon`` and sample uniformly from
eligible topologies with probability ``epsilon``.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import Any, Self

import numpy as np

from samg.domain.enums import ReasonCode, TopologyName
from samg.domain.events import LearningEvent
from samg.learning.base import (
    ARM_ORDER,
    PolicyDecision,
    ProtectedGate,
    argmax_by_arm_order,
    ordered_eligible,
)

POLICY_VERSION = "contextual-epsilon-greedy-v1"


class ContextualEpsilonGreedyPolicy:
    """Protected contextual epsilon-greedy policy over feasible topology arms."""

    kind = "P4-ContextualEpsilonGreedy"

    def __init__(
        self,
        *,
        dim: int = 5,
        epsilon: float = 0.1,
        lam: float = 1.0,
        seed: int = 0,
        warmup_per_arm: int = 1,
        feature_schema_version: str = "ctx-v1",
    ) -> None:
        if dim < 1 or not 0.0 <= epsilon <= 1.0 or lam <= 0 or warmup_per_arm < 0:
            raise ValueError("invalid epsilon-greedy hyperparameters")
        self.dim = dim
        self.epsilon = float(epsilon)
        self.lam = float(lam)
        self.seed = int(seed)
        self.warmup_per_arm = int(warmup_per_arm)
        self.feature_schema_version = feature_schema_version
        self.rng = np.random.default_rng(self.seed)
        self.warmup_order: tuple[TopologyName, ...] = tuple(
            ARM_ORDER[i] for i in self.rng.permutation(len(ARM_ORDER))
        )
        self.A: dict[TopologyName, np.ndarray] = {a: self.lam * np.eye(self.dim) for a in ARM_ORDER}
        self.b: dict[TopologyName, np.ndarray] = {a: np.zeros(self.dim) for a in ARM_ORDER}
        self.selections: dict[TopologyName, int] = {a: 0 for a in ARM_ORDER}
        self.updates: dict[TopologyName, int] = {a: 0 for a in ARM_ORDER}
        self.gate = ProtectedGate()

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

    def select(
        self,
        context: Sequence[float],
        eligible: Sequence[TopologyName],
        feature_schema_version: str,
    ) -> PolicyDecision:
        x = self._vector(context, feature_schema_version)
        arms = ordered_eligible(eligible)
        means = {arm: float(self.theta(arm) @ x) for arm in ARM_ORDER}
        scores = dict(means)
        common = dict(
            policy_kind=self.kind,
            policy_version=POLICY_VERSION,
            eligible=arms,
            feature_schema_version=feature_schema_version,
            context=tuple(float(v) for v in x),
            scores=scores,
            means=means,
            exploration_probability=self.epsilon,
        )
        if not arms:
            return PolicyDecision(
                **common, topology=None, reason_codes=(ReasonCode.NO_ELIGIBLE_TOPOLOGY,)
            )

        under = [a for a in self.warmup_order if a in arms and self.selections[a] < self.warmup_per_arm]
        if under:
            chosen, warmup, explored = under[0], True, False
        else:
            warmup = False
            explored = bool(self.rng.random() < self.epsilon)
            if explored:
                chosen = arms[int(self.rng.integers(len(arms)))]
            else:
                chosen = argmax_by_arm_order({a: scores[a] for a in arms})
        self.selections[chosen] += 1
        return PolicyDecision(**common, topology=chosen, warmup=warmup, explored=explored)

    def observe(self, event: LearningEvent) -> None:
        """Update from an ADMITTED episode and its ACP-recomputed reward only."""
        reward = self.gate.admit(event)
        x = self._vector(event.context, event.feature_schema_version)
        self.A[event.topology] = self.A[event.topology] + np.outer(x, x)
        self.b[event.topology] = self.b[event.topology] + reward * x
        self.updates[event.topology] += 1
        self.gate.mark_applied(event)

    def snapshot(self) -> dict[str, Any]:
        """Return JSON-safe model and selector state for exact seeded replay."""
        return {
            "kind": self.kind,
            "policy_version": POLICY_VERSION,
            "hyperparameters": {
                "dim": self.dim,
                "epsilon": self.epsilon,
                "lam": self.lam,
                "seed": self.seed,
                "warmup_per_arm": self.warmup_per_arm,
                "feature_schema_version": self.feature_schema_version,
            },
            "A": {a.value: self.A[a].tolist() for a in ARM_ORDER},
            "b": {a.value: self.b[a].tolist() for a in ARM_ORDER},
            "selections": {a.value: self.selections[a] for a in ARM_ORDER},
            "updates": {a.value: self.updates[a] for a in ARM_ORDER},
            "rng_state": copy.deepcopy(self.rng.bit_generator.state),
            "applied_episodes": sorted(self.gate.applied_episodes),
        }

    @classmethod
    def from_snapshot(cls, state: dict[str, Any]) -> Self:
        policy = cls(**state["hyperparameters"])
        for arm in ARM_ORDER:
            policy.A[arm] = np.asarray(state["A"][arm.value], dtype=float)
            policy.b[arm] = np.asarray(state["b"][arm.value], dtype=float)
            policy.selections[arm] = int(state["selections"][arm.value])
            policy.updates[arm] = int(state["updates"][arm.value])
        policy.rng.bit_generator.state = copy.deepcopy(state["rng_state"])
        policy.gate = ProtectedGate(state["applied_episodes"])
        return policy

    def clone(self) -> Self:
        return type(self).from_snapshot(self.snapshot())


__all__ = ["ContextualEpsilonGreedyPolicy", "POLICY_VERSION"]
