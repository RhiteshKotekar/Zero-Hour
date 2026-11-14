"""Unit tests for ctx-v1 context features (Dev A)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from samg.context import FEATURE_NAMES, MissionContext, extract_features
from samg.simulation.scenarios import judge_scenario


def test_feature_order_is_versioned() -> None:
    assert FEATURE_NAMES == ("intercept", "dependency_density", "capability_heterogeneity",
                             "resource_scarcity", "agent_availability")


def test_judge_features_match_hand_computation() -> None:
    f = extract_features(judge_scenario()).as_dict()
    assert f["intercept"] == 1.0
    assert f["dependency_density"] == pytest.approx(7 / 28)
    assert f["agent_availability"] == 1.0
    demand = 2 + 3 + 2 + 1 + 5 + 6 + 2 + 4
    budget = 0 + 6 + 12 + 10 + 12 + 8
    assert f["resource_scarcity"] == pytest.approx(demand / budget)
    assert 0 < f["capability_heterogeneity"] <= 1


def test_unavailable_agent_lowers_availability() -> None:
    scenario = judge_scenario()
    agents = tuple(a.model_copy(update={"available": a.agent_id != "A3"}) for a in scenario.agents)
    f = extract_features(scenario.model_copy(update={"agents": agents})).as_dict()
    assert f["agent_availability"] == pytest.approx(5 / 6)


def test_features_are_deterministic() -> None:
    assert extract_features(judge_scenario()) == extract_features(judge_scenario())


def test_context_rejects_unnormalised_values() -> None:
    with pytest.raises(ValidationError):
        MissionContext(mission_id="m", features=(1.0, 1.5, 0, 0, 0))
    with pytest.raises(ValidationError):
        MissionContext(mission_id="m", features=(0.0, 0, 0, 0, 0))
