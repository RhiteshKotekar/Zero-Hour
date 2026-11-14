"""Unit tests for the topology landscape analysis (Dev A)."""

from __future__ import annotations

from samg.evaluation.landscape import (
    DESIGN_SEED_OFFSET,
    default_settings,
    grid_scenarios,
    landscape,
    summarize_landscape,
)
from samg.evaluation.runner import ExperimentConfig, build_splits
from samg.simulation.scenarios import judge_scenario


def test_judge_landscape_is_ranked_and_bounded() -> None:
    rows = landscape([judge_scenario()], {"base": default_settings()["base"]})
    (row,) = rows
    assert set(row.planned_reward) == set(row.eligible)
    assert all(0.0 <= v <= 1.0 for v in row.planned_reward.values())
    assert row.planned_reward[row.best] == max(row.planned_reward.values())
    assert row.factors == "manual"


def test_summary_shares_sum_to_one() -> None:
    rows = landscape(grid_scenarios(stride=54), default_settings())
    summary = summarize_landscape(rows)
    assert set(summary) == {"low", "base", "high", "no_link_cost", "no_handoff_cost"}
    for item in summary.values():
        assert abs(sum(item["best_share"].values()) - 1.0) < 1e-9


def test_design_seeds_never_overlap_experiment_seeds() -> None:
    cfg = ExperimentConfig()
    used = {s.seed for split in build_splits(cfg).values() for s, _ in split}
    design = {s.seed for s in grid_scenarios()}
    assert min(design) >= DESIGN_SEED_OFFSET
    assert not used & design
