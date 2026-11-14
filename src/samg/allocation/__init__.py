"""Constrained allocation strategies and allocation plans (owner: Dev A).

Public interface: ``allocate(scenario, graph, costs=None, config=None) -> AllocationPlan``.
CP-SAT is used by default; the deterministic greedy allocator runs when CP-SAT
is disabled or returns no feasible incumbent without proving infeasibility
(``plan.fallback_used`` records it, D003).
"""

from __future__ import annotations

from samg.allocation.common import AllocationProblem, evaluate
from samg.allocation.cpsat import allocate_cpsat
from samg.allocation.greedy import allocate_greedy
from samg.domain import (
    AllocationConfig,
    AllocationPlan,
    CoordinationGraph,
    Scenario,
    TopologyCostConfig,
)


def allocate(
    scenario: Scenario,
    graph: CoordinationGraph,
    costs: TopologyCostConfig | None = None,
    config: AllocationConfig | None = None,
) -> AllocationPlan:
    problem = AllocationProblem(scenario, graph, costs or TopologyCostConfig(), config or AllocationConfig())
    if not problem.config.use_cpsat:
        return allocate_greedy(problem)
    plan, _status = allocate_cpsat(problem)
    if plan is not None:
        return plan
    return allocate_greedy(problem, fallback_used=True)


from samg.allocation.feasibility import feasible_topologies  # noqa: E402  (needs allocate defined)

__all__ = ["AllocationProblem", "allocate", "allocate_cpsat", "allocate_greedy", "evaluate", "feasible_topologies"]
