"""Deterministic scenario generation and mission simulation (owner: Dev A).

Public interface (THREE_PERSON_PLAN §2): ``run`` (plan -> ``ExecutionTrace``),
``compute_metrics`` and ``compute_reward`` (brief §7.2), plus the scenario
builders in ``samg.simulation.scenarios``.
"""

from samg.simulation.engine import run
from samg.simulation.reward import compute_metrics, compute_reward

__all__ = ["compute_metrics", "compute_reward", "run"]
