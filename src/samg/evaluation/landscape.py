"""Topology landscape: which topology is best where, before any learning (owner: Dev A).

For each generated scenario and each feasible topology, compute the allocator's
plan and a *noise-free planned reward* with the brief §7.2 formula
(C = 1 for a complete plan, T = makespan / deadline, R = resource used /
assigned agents' budget, H = (handoff + link cost) / max coordination cost).
This is a proxy: the simulator's ground-truth reward replaces it in Experiments
A-C. It answers two pre-registration questions cheaply:

1. Does the best topology vary across missions? If one arm wins almost
   everywhere, contextual selection cannot beat the best fixed topology.
2. Does the ranking change under the predeclared cost settings (brief §5.4,
   §12.9)? If it flips, results are parameter-sensitive and must say so.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from samg.allocation import feasible_topologies
from samg.domain import AllocationConfig, AllocationPlan, RewardConfig, Scenario, TopologyCostConfig, TopologyName
from samg.simulation.scenarios import ScenarioFactors, factor_grid, generate_scenario
from samg.topology import HopTable, max_coordination_cost


class LandscapeRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    setting: str
    scenario_id: str
    family: str | None
    factors: str
    eligible: tuple[TopologyName, ...]
    planned_reward: dict[TopologyName, float]
    best: TopologyName | None
    margin: float | None  # best minus runner-up planned reward


def _factor_key(scenario: Scenario) -> str:
    params = scenario.mission.generator_params
    keys = ("dependency", "capability", "resources", "availability", "task_profile")
    return "/".join(str(params[k]) for k in keys) if all(k in params for k in keys) else "manual"


def planned_reward(scenario: Scenario, plan: AllocationPlan, link_cost_total: float,
                   costs: TopologyCostConfig, reward: RewardConfig) -> float:
    mission = scenario.mission
    assigned = {a.agent_id for a in plan.assignments}
    budget = sum(scenario.agent(a).resource_budget for a in assigned) or 1.0
    done = {a.task_id for a in plan.assignments}
    total_w = sum(t.priority_weight for t in mission.tasks)
    c = sum(t.priority_weight for t in mission.tasks if t.task_id in done) / total_w
    t_norm = min(1.0, max(a.end for a in plan.assignments) / mission.deadline_ms)
    r_norm = min(1.0, plan.objective.resource_use / budget)
    h_max = max_coordination_cost(len(mission.dependency_edges()), len(scenario.agents), costs)
    h_norm = min(1.0, (plan.objective.handoff_cost + link_cost_total) / h_max)
    w = reward.weights
    value = (w["completion"] * c + w["duration"] * (1 - t_norm) + w["resources"] * (1 - r_norm)
             + w["coordination"] * (1 - h_norm))
    return min(1.0, max(0.0, value))


def landscape(
    scenarios: Iterable[Scenario],
    settings: dict[str, TopologyCostConfig],
    *,
    allocation: AllocationConfig | None = None,
    reward: RewardConfig | None = None,
) -> list[LandscapeRow]:
    allocation = allocation or AllocationConfig()
    reward = reward or RewardConfig()
    rows: list[LandscapeRow] = []
    for scenario in scenarios:
        for name, costs in settings.items():
            eligible, _, plans = feasible_topologies(scenario, costs, allocation)
            values = {}
            for topology, (graph, plan) in plans.items():
                links = HopTable(graph, costs).link_maintenance_cost()
                values[topology] = planned_reward(scenario, plan, links, costs, reward)
            ranked = sorted(values.items(), key=lambda kv: (-kv[1], kv[0].value))
            best = ranked[0][0] if ranked else None
            margin = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else None
            rows.append(LandscapeRow(setting=name, scenario_id=scenario.scenario_id,
                                     family=scenario.mission.family,
                                     factors=_factor_key(scenario),
                                     eligible=tuple(eligible), planned_reward=values, best=best, margin=margin))
    return rows


def default_settings(base: TopologyCostConfig | None = None) -> dict[str, TopologyCostConfig]:
    """Predeclared settings: h0/h1 low/base/high plus the D021 link-cost ablation."""
    base = base or TopologyCostConfig()
    out = {name: base.with_setting(name) for name in ("low", "base", "high")}
    out["no_link_cost"] = base.model_copy(update={"link_cost": 0.0})
    out["no_handoff_cost"] = base.model_copy(update={"h0": 0.0, "h1": 0.0, "handoff_delay_ms_per_hop": 0.0})
    return out


def summarize_landscape(rows: list[LandscapeRow]) -> dict[str, dict]:
    """Per setting: best-topology shares overall and by family, plus mean margin."""
    out: dict[str, dict] = {}
    by_setting: dict[str, list[LandscapeRow]] = defaultdict(list)
    for r in rows:
        by_setting[r.setting].append(r)
    for setting, items in by_setting.items():
        best = Counter(r.best.value for r in items if r.best)
        fam: dict[str, Counter] = defaultdict(Counter)
        for r in items:
            if r.best:
                fam[r.family or "unknown"][r.best.value] += 1
        margins = [r.margin for r in items if r.margin is not None]
        out[setting] = {
            "n": len(items),
            "best_share": {k: v / len(items) for k, v in sorted(best.items())},
            "best_by_family": {f: dict(c) for f, c in sorted(fam.items())},
            "mean_margin": sum(margins) / len(margins) if margins else None,
        }
    return out


DESIGN_SEED_OFFSET = 50_000
"""Design-analysis seeds start here, above every ``seed_splits`` pool (< 10 000 + n), so landscape
studies used to shape the model never touch the experiment's dev/train/test missions."""


def grid_scenarios(stride: int = 1, seed_offset: int = DESIGN_SEED_OFFSET) -> list[Scenario]:
    grid: list[ScenarioFactors] = factor_grid()[::stride]
    return [generate_scenario(seed_offset + i, f) for i, f in enumerate(grid)]
