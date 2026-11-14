"""Evaluation statistics (owner: Dev A).

All resampling takes an explicit seed. Counts are always reported alongside
rates so denominators are visible (brief §12.8).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    n: int
    mean: float | None
    median: float | None
    std: float | None
    ci95_low: float | None
    ci95_high: float | None


class PairedComparison(BaseModel):
    """``a - b`` over matched missions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    a: str
    b: str
    n_pairs: int
    mean_diff: float | None
    ci95_low: float | None
    ci95_high: float | None
    wins: int
    losses: int
    ties: int


def bootstrap_ci(values: Sequence[float], *, seed: int, n_resamples: int = 2000,
                 statistic=np.mean) -> tuple[float | None, float | None]:
    """Percentile bootstrap 95% CI. ``(None, None)`` for fewer than 2 values."""
    data = np.asarray(values, dtype=float)
    if data.size < 2:
        return None, None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, data.size, size=(n_resamples, data.size))
    stats = statistic(data[idx], axis=1)
    low, high = np.percentile(stats, [2.5, 97.5])
    return float(low), float(high)


def summarize(values: Sequence[float], *, seed: int) -> Summary:
    data = np.asarray(values, dtype=float)
    if data.size == 0:
        return Summary(n=0, mean=None, median=None, std=None, ci95_low=None, ci95_high=None)
    low, high = bootstrap_ci(data, seed=seed)
    return Summary(n=int(data.size), mean=float(data.mean()), median=float(np.median(data)),
                   std=float(data.std(ddof=1)) if data.size > 1 else 0.0, ci95_low=low, ci95_high=high)


def paired_comparison(a_name: str, a: Mapping[str, float], b_name: str, b: Mapping[str, float], *,
                      seed: int, tie_tol: float = 1e-9) -> PairedComparison:
    """Compare two policies on the missions both completed (keys = mission IDs)."""
    keys = sorted(set(a) & set(b))
    diffs = np.asarray([a[k] - b[k] for k in keys], dtype=float)
    low, high = bootstrap_ci(diffs, seed=seed)
    return PairedComparison(
        a=a_name, b=b_name, n_pairs=len(keys),
        mean_diff=float(diffs.mean()) if keys else None, ci95_low=low, ci95_high=high,
        wins=int((diffs > tie_tol).sum()), losses=int((diffs < -tie_tol).sum()),
        ties=int((np.abs(diffs) <= tie_tol).sum()),
    )


def oracle_regret(selected: Mapping[str, float], counterfactual: Mapping[str, Mapping[str, float]]) -> dict[str, float]:
    """Simulator-oracle regret per mission: best observed counterfactual reward minus the selected reward.

    ``counterfactual[mission][topology] = reward``; evaluation-only, never fed to a learner (brief §12.3).
    """
    regret: dict[str, float] = {}
    for mission, reward in selected.items():
        options = counterfactual.get(mission, {})
        if options:
            regret[mission] = max(max(options.values()) - reward, 0.0)
    return regret


def cumulative(values: Sequence[float]) -> list[float]:
    return [float(x) for x in np.cumsum(np.asarray(values, dtype=float))]
