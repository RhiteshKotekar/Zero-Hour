"""Ground-truth metrics and the brief §7.2 reward (owner: Dev A).

Minimal integration version, written by the integrator for the Phase 2
vertical slice. Dev A may extend it (e.g. critical-task weights, alternative
weight sets), but the metric and reward rules below are what the ACP uses to
*recompute* the protected reward from witness-verified outcomes, so the same
functions must serve both the simulator and the ACP.

Normalisation and clipping (``config/reward.yaml``):

* ``C`` weighted completion = completed priority weight / total priority weight.
* ``T`` = makespan / deadline, clipped to [0, 1]. Makespan = latest end of a
  completed task; with nothing completed, ``T = 1``.
* ``R`` = resource demand of every task that started executing / total budget of
  the agents the plan assigned, clipped to [0, 1].
* ``H`` = (graph-derived handoff cost of every planned handoff whose prerequisite
  completed + ``link_cost`` x coordination links, D012/D021) /
  ``max_coordination_cost``, clipped to [0, 1].

    r = wC*C + wT*(1-T) + wR*(1-R) + wH*(1-H), clipped to [0, 1]

An invalid (infeasible) plan gets the predefined failure outcome, never a
normal reward.
"""

from __future__ import annotations

from collections.abc import Sequence

from samg.domain import (
    AllocationPlan,
    CoordinationGraph,
    GroundTruthMetrics,
    RewardBreakdown,
    RewardConfig,
    Scenario,
    TaskOutcome,
    TopologyCostConfig,
)
from samg.topology import max_coordination_cost

TERM_ORDER: tuple[str, ...] = ("completion", "duration", "resources", "coordination")


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def compute_metrics(
    scenario: Scenario,
    graph: CoordinationGraph,
    plan: AllocationPlan,
    outcomes: Sequence[TaskOutcome],
    costs: TopologyCostConfig,
    *,
    communication_failures: int = 0,
) -> GroundTruthMetrics:
    """Raw and normalised C, T, R, H for one executed plan.

    ``outcomes`` may come from the simulator (ground truth) or from the ACP's
    witness ledger; the arithmetic is identical either way.
    """
    mission = scenario.mission
    by_task = {o.task_id: o for o in outcomes}
    total_priority = sum(t.priority_weight for t in mission.tasks)
    done = {t.task_id for t in mission.tasks if by_task.get(t.task_id) and by_task[t.task_id].completed}
    if costs.simulation_model is not None and costs.simulation_model.enforce_deadline:
        # model v2 (D041): work finished after the deadline does not count as completed
        done = {t for t in done if by_task[t].end is None or by_task[t].end <= mission.deadline_ms}
    completion = sum(mission.task(t).priority_weight for t in done) / total_priority

    ends = [by_task[t].end for t in done if by_task[t].end is not None]
    makespan = max(ends) if ends else mission.deadline_ms
    duration_norm = _clip01(makespan / mission.deadline_ms)

    started = [o.task_id for o in outcomes if o.start is not None]
    resource_used = sum(mission.task(t).resource_demand for t in started)
    assigned_agents = {a.agent_id for a in plan.assignments}
    budget = sum(scenario.agent(a).resource_budget for a in assigned_agents)
    resource_norm = _clip01(resource_used / budget) if budget > 0 else (1.0 if resource_used > 0 else 0.0)

    handoff = sum(h.cost for h in plan.handoffs if h.prerequisite_task in done)
    coordination = handoff + costs.link_cost * len(graph.coordination_links())
    bound = max_coordination_cost(len(mission.dependency_edges()), len(scenario.available_agents()), costs)
    coordination_norm = _clip01(coordination / bound)

    mandatory_done = all(t.task_id in done for t in mission.tasks if t.mandatory)
    return GroundTruthMetrics(
        weighted_completion=_clip01(completion),
        makespan=makespan,
        duration_norm=duration_norm,
        resource_used=resource_used,
        resource_norm=resource_norm,
        coordination_cost=coordination,
        coordination_norm=coordination_norm,
        mandatory_completed=mandatory_done,
        communication_failures=communication_failures,
    )


def compute_reward(
    metrics: GroundTruthMetrics | None, config: RewardConfig, *, weights: str = "base"
) -> RewardBreakdown:
    """Brief §7.2 reward with every term and contribution.

    ``metrics=None`` means the plan was invalid/infeasible: the predefined
    failure outcome is returned instead of a normal reward. ``weights`` names
    ``"base"`` or one of ``config.alternatives`` (sensitivity checks).
    """
    w = dict(config.weights if weights == "base" else config.alternatives[weights])
    if metrics is None:
        zeros = {k: 0.0 for k in TERM_ORDER}
        return RewardBreakdown(weights=w, components=zeros, contributions=dict(zeros),
                               reward=config.failure_reward, failure_outcome=True,
                               failure_label=config.failure_label)
    components = {
        "completion": metrics.weighted_completion,
        "duration": 1.0 - metrics.duration_norm,
        "resources": 1.0 - metrics.resource_norm,
        "coordination": 1.0 - metrics.coordination_norm,
    }
    contributions = {k: w[k] * components[k] for k in TERM_ORDER}
    return RewardBreakdown(weights=w, components=components, contributions=contributions,
                           reward=_clip01(sum(contributions.values())))


__all__ = ["TERM_ORDER", "compute_metrics", "compute_reward"]
