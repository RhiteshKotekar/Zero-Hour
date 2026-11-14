"""Context features ``ctx-v1`` (brief §6.1): ``x = [1, d, h, r, a]``.

- d, dependency density: dependency edges / (n * (n - 1) / 2), n = task count.
- h, capability heterogeneity: mean pairwise Jaccard distance between the
  capability sets of available agents.
- r, resource scarcity: total task resource demand / total resource budget of
  available agents, clipped to [0, 1].
- a, agent availability: available agents / registered agents.

Missing-value rules (documented, never silent): fewer than 2 tasks -> d = 0;
fewer than 2 available agents -> h = 0; zero available budget -> r = 1 if any
demand exists else 0; no registered agents -> a = 0.

The mission family label is never used.
"""

from __future__ import annotations

from itertools import combinations

from pydantic import Field, model_validator

from samg.domain import SamgModel, Scenario

FEATURE_SCHEMA_VERSION = "ctx-v1"
FEATURE_NAMES: tuple[str, ...] = ("intercept", "dependency_density", "capability_heterogeneity",
                                  "resource_scarcity", "agent_availability")


class MissionContext(SamgModel):
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    mission_id: str
    feature_names: tuple[str, ...] = FEATURE_NAMES
    features: tuple[float, ...] = Field(description="Ordered as feature_names; intercept first.")

    @model_validator(mode="after")
    def _shape(self) -> MissionContext:
        if len(self.features) != len(self.feature_names):
            raise ValueError("feature vector length must match feature_names")
        if self.features[0] != 1.0:
            raise ValueError("first feature is the intercept and must be 1.0")
        if any(not 0.0 <= f <= 1.0 for f in self.features):
            raise ValueError("features must be normalised to [0, 1]")
        return self

    def as_dict(self) -> dict[str, float]:
        return dict(zip(self.feature_names, self.features, strict=True))


def _clip(x: float) -> float:
    return min(1.0, max(0.0, x))


def _jaccard_distance(a: set[str], b: set[str]) -> float:
    union = a | b
    return 0.0 if not union else 1.0 - len(a & b) / len(union)


def extract_features(scenario: Scenario) -> MissionContext:
    mission = scenario.mission
    n = len(mission.tasks)
    d = len(mission.dependency_edges()) / (n * (n - 1) / 2) if n >= 2 else 0.0

    available = scenario.available_agents()
    pairs = list(combinations([set(a.capabilities) for a in available], 2))
    h = sum(_jaccard_distance(x, y) for x, y in pairs) / len(pairs) if pairs else 0.0

    demand = sum(t.resource_demand for t in mission.tasks)
    budget = sum(a.resource_budget for a in available)
    r = (demand / budget if budget > 0 else (1.0 if demand > 0 else 0.0))

    a = len(available) / len(scenario.agents) if scenario.agents else 0.0
    return MissionContext(mission_id=mission.mission_id,
                          features=(1.0, _clip(d), _clip(h), _clip(r), _clip(a)))
