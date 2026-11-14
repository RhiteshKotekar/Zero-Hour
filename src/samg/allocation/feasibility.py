"""Topology eligibility including allocation feasibility (D030; owner: Dev A).

``eligible_topologies`` only checks that a topology can be built and that every
dependency has *some* reachable agent pair. That is necessary but not sufficient:
capacity, budget and the joint path constraints can still make every plan
infeasible (seen for DISTRIBUTED when its degree cap removes a needed path).
``feasible_topologies`` additionally runs the allocator, so a policy is only ever
offered an arm that has a feasible plan. Feasibility is known before execution,
so this leaks no outcome information to the policy. The plans are returned so
callers do not solve twice.
"""

from __future__ import annotations

from samg.allocation import allocate
from samg.domain import (
    AllocationConfig,
    AllocationPlan,
    CoordinationGraph,
    IneligibilityReason,
    Scenario,
    TopologyCostConfig,
    TopologyEligibility,
    TopologyName,
)
from samg.topology import build_graph


def feasible_topologies(
    scenario: Scenario,
    costs: TopologyCostConfig | None = None,
    config: AllocationConfig | None = None,
) -> tuple[
    list[TopologyName],
    dict[TopologyName, TopologyEligibility],
    dict[TopologyName, tuple[CoordinationGraph, AllocationPlan]],
]:
    """``(eligible arms, verdict per arm, (graph, plan) per eligible arm)``."""
    costs = costs or TopologyCostConfig()
    verdicts: dict[TopologyName, TopologyEligibility] = {}
    plans: dict[TopologyName, tuple[CoordinationGraph, AllocationPlan]] = {}
    for topology in TopologyName:
        verdict, graph = build_graph(scenario, topology, costs)
        if graph is not None:
            plan = allocate(scenario, graph, costs, config)
            if plan.feasible:
                plans[topology] = (graph, plan)
            else:
                verdict = TopologyEligibility(
                    topology=topology, eligible=False, reasons=[IneligibilityReason.ALLOCATION_INFEASIBLE],
                    detail=", ".join(r.value for r in plan.reason_codes) + (f": {plan.detail}" if plan.detail else ""),
                )
        verdicts[topology] = verdict
    return [t for t in TopologyName if verdicts[t].eligible], verdicts, plans
