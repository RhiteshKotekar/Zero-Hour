"""Unit tests for the seeded scenario generator (Dev A)."""

from __future__ import annotations

import pytest

from samg.context import extract_features
from samg.simulation.scenarios import (
    GENERATOR_VERSION,
    ScenarioFactors,
    factor_grid,
    generate_scenario,
    seed_splits,
    split_factor_combos,
)
from samg.topology import eligible_agents

GRID = factor_grid()


def test_grid_covers_every_combination_once() -> None:
    assert len(GRID) == 4 * 3 * 3 * 3 * 2
    assert len({f.key() for f in GRID}) == len(GRID)


def test_generator_is_deterministic() -> None:
    factors = ScenarioFactors(dependency="parallel", capability="clustered")
    assert generate_scenario(42, factors) == generate_scenario(42, factors)
    assert generate_scenario(42, factors) != generate_scenario(43, factors)


@pytest.mark.parametrize("factors", GRID[::7], ids=lambda f: f.key())
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_generated_scenarios_respect_guarantees(seed: int, factors: ScenarioFactors) -> None:
    scenario = generate_scenario(seed, factors)
    mission = scenario.mission
    assert mission.generator_version == GENERATOR_VERSION
    assert mission.generator_params["seed"] == seed
    for task in mission.tasks:
        assert eligible_agents(scenario, task), f"{task.task_id} has no capable agent"
    live = scenario.available_agents()
    assert sum(a.capacity for a in live) >= len(mission.tasks)
    if factors.availability == "one_unavailable":
        assert len(live) == len(scenario.agents) - 1
    if factors.dependency == "deep_chain":
        assert len(mission.dependency_edges()) == len(mission.tasks) - 1


def test_factors_change_features() -> None:
    dense = extract_features(generate_scenario(5, ScenarioFactors(dependency="branching"))).as_dict()
    sparse = extract_features(generate_scenario(5, ScenarioFactors(dependency="sparse"))).as_dict()
    assert dense["dependency_density"] > sparse["dependency_density"]
    tight = extract_features(generate_scenario(5, ScenarioFactors(resources="constrained"))).as_dict()
    loose = extract_features(generate_scenario(5, ScenarioFactors(resources="abundant"))).as_dict()
    assert tight["resource_scarcity"] > loose["resource_scarcity"]


def test_family_label_is_reporting_only() -> None:
    scenario = generate_scenario(3, ScenarioFactors(dependency="deep_chain", capability="specialist"))
    assert scenario.mission.family == "dependency_heavy"
    assert "family" not in extract_features(scenario).feature_names


def test_seed_splits_are_disjoint_and_deterministic() -> None:
    splits = seed_splits(7, 10, 50, 20)
    assert [len(splits[k]) for k in ("dev", "train", "test")] == [10, 50, 20]
    sets = [set(splits[k]) for k in ("dev", "train", "test")]
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
    assert seed_splits(7, 10, 50, 20) == splits


def test_factor_holdout_is_disjoint() -> None:
    split = split_factor_combos(7, 0.2)
    seen = {f.key() for f in split["seen"]}
    held = {f.key() for f in split["held_out"]}
    assert not seen & held
    assert len(seen) + len(held) == len(GRID)
    assert len(held) == round(len(GRID) * 0.2)
