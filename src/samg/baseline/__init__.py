"""Conventional centralized baseline for SAMG comparisons (D042).

Public API: ``run_mode(spec, mode)`` with mode ``"samg"`` or ``"baseline"``, ``run_warehouse_baseline``,
``run_metrics`` and ``dispatch``. Nothing in ``samg.twin``, ``samg.api`` or ``web/`` is modified.
"""

from samg.baseline.dispatcher import BASELINE_VERSION, DispatchWeights, dispatch
from samg.baseline.execution import BASELINE_KIND, MODES, run_metrics, run_mode, run_warehouse_baseline

__all__ = ["BASELINE_KIND", "BASELINE_VERSION", "MODES", "DispatchWeights", "dispatch", "run_metrics",
           "run_mode", "run_warehouse_baseline"]
