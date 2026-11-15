"""Topology-selection policies and evidence-gated learning.

Public API (THREE_PERSON_PLAN §2): ``make_policy`` and the policy classes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from samg.domain.enums import TopologyName
from samg.learning.base import ARM_ORDER, PolicyDecision, TopologyPolicy
from samg.learning.epsilon_greedy import ContextualEpsilonGreedyPolicy
from samg.learning.fixed import FixedTopologyPolicy, best_fixed_from_training
from samg.learning.linucb import LinUCBPolicy
from samg.learning.ucb1 import UCB1Policy
from samg.learning.vulnerable import VulnerableLinUCB

_FIXED = {
    "P0-H": TopologyName.HIERARCHICAL,
    "P0-F": TopologyName.FUNCTIONAL_CELL,
    "P0-D": TopologyName.DISTRIBUTED,
}

POLICY_KINDS = ("P0-H", "P0-F", "P0-D", "P1", "P2", "P3", "P4", "S1")


def make_policy(kind: str, cfg: Mapping[str, Any] | None = None, seed: int = 0) -> TopologyPolicy:
    """Build a policy by plan kind.

    * ``P0-H`` / ``P0-F`` / ``P0-D``: fixed topology.
    * ``P1``: best fixed on training; ``cfg["topology"]`` must name it.
    * ``P2``: UCB1 (``cfg["c"]``).
    * ``P3``: protected LinUCB (``cfg["alpha"]``, ``cfg["lam"]``, ``cfg["dim"]``, ``cfg["warmup_per_arm"]``).
    * ``P4``: protected contextual epsilon-greedy (``cfg["epsilon"]``, ``cfg["lam"]``,
      ``cfg["dim"]``, ``cfg["warmup_per_arm"]``).
    * ``S1``: ``VulnerableLinUCB`` — Experiment C only, never a default.
    """
    cfg = dict(cfg or {})
    if kind in _FIXED:
        return FixedTopologyPolicy(_FIXED[kind])
    if kind == "P1":
        return FixedTopologyPolicy(TopologyName(cfg["topology"]), kind="P1-BestFixed")
    if kind == "P2":
        return UCB1Policy(**{k: cfg[k] for k in ("c", "feature_schema_version") if k in cfg})
    if kind == "P4":
        keys = ("dim", "epsilon", "lam", "warmup_per_arm", "feature_schema_version")
        return ContextualEpsilonGreedyPolicy(seed=seed, **{k: cfg[k] for k in keys if k in cfg})
    if kind in ("P3", "S1"):
        keys = ("dim", "alpha", "lam", "warmup_per_arm", "feature_schema_version")
        cls = LinUCBPolicy if kind == "P3" else VulnerableLinUCB
        return cls(seed=seed, **{k: cfg[k] for k in keys if k in cfg})
    raise ValueError(f"unknown policy kind {kind!r}; expected one of {POLICY_KINDS}")


__all__ = [
    "ARM_ORDER",
    "ContextualEpsilonGreedyPolicy",
    "POLICY_KINDS",
    "FixedTopologyPolicy",
    "LinUCBPolicy",
    "PolicyDecision",
    "TopologyPolicy",
    "UCB1Policy",
    "VulnerableLinUCB",
    "best_fixed_from_training",
    "make_policy",
]
