"""Shared allocation problem, plan evaluation and plan assembly (owner: Dev A).

Both allocators report objective terms through ``evaluate`` so CP-SAT and the
greedy fallback are always compared on identical arithmetic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from samg.domain import (
    AllocationConfig,
    AllocationFailure,
    AllocationPlan,
    Assignment,
    CoordinationGraph,
    Handoff,
    ObjectiveTerms,
    Scenario,
    SolverName,
    TopologyCostConfig,
)
from samg.topology import HopTable, eligible_agents

MINUTE_MS = 60_000.0


@dataclass
class AllocationProblem:
    scenario: Scenario
    graph: CoordinationGraph
    costs: TopologyCostConfig
    config: AllocationConfig
    hops: HopTable = field(init=False)
    eligible: dict[str, list[str]] = field(init=False)

    def __post_init__(self) -> None:
        if self.graph.mission_id != self.scenario.mission.mission_id:
            raise ValueError("graph was built for a different mission")
        self.hops = HopTable(self.graph, self.costs)
        self.eligible = {t.task_id: eligible_agents(self.scenario, t) for t in self.scenario.mission.tasks}

    @property
    def mission(self):
        return self.scenario.mission

    def precheck(self) -> tuple[list[AllocationFailure], str]:
        """Failures detectable without search: a mandatory task nobody can perform."""
        missing = [t.task_id for t in self.mission.tasks if t.mandatory and not self.eligible[t.task_id]]
        if missing:
            return [AllocationFailure.NO_CAPABLE_AGENT], "no capable available agent for " + ", ".join(missing)
        return [], ""


def evaluate(problem: AllocationProblem, assignments: list[Assignment]) -> tuple[list[Handoff], ObjectiveTerms]:
    """Handoff explanations and objective terms for a complete schedule."""
    by_task = {a.task_id: a for a in assignments}
    handoffs: list[Handoff] = []
    for prereq, dependent in problem.mission.dependency_edges():
        if prereq not in by_task or dependent not in by_task:
            continue
        a, b = by_task[prereq].agent_id, by_task[dependent].agent_id
        route = problem.hops.route(a, b)
        if route is None:
            raise ValueError(f"assignment uses unpermitted handoff {a}->{b} for {prereq}->{dependent}")
        handoffs.append(Handoff(prerequisite_task=prereq, dependent_task=dependent, from_agent=a, to_agent=b,
                                hops=route.hops, path=route.path, cost=route.cost, delay=route.delay))

    load: dict[str, float] = {}
    for a in assignments:
        load[a.agent_id] = load.get(a.agent_id, 0.0) + problem.mission.task(a.task_id).duration_ms
    terms = {
        "makespan": max((a.end for a in assignments), default=0.0) / MINUTE_MS,
        "handoff_cost": sum(h.cost for h in handoffs),
        "resource_use": sum(problem.mission.task(a.task_id).resource_demand for a in assignments),
        "max_agent_load": max(load.values(), default=0.0) / MINUTE_MS,
        "unserved_priority": sum(t.priority_weight for t in problem.mission.tasks if t.task_id not in by_task),
    }
    weights = problem.config.weights
    total = sum(weights[k] * v for k, v in terms.items())
    return handoffs, ObjectiveTerms(**terms, weighted_total=total, weights=dict(weights))


def plan_id(mission_id: str, graph_version: str, solver: SolverName, assignments: list[Assignment]) -> str:
    """Deterministic plan ID (documented fixture-style ID): same inputs -> same ID."""
    payload = json.dumps([mission_id, graph_version, solver.value,
                          sorted((a.task_id, a.agent_id, a.start) for a in assignments)],
                         separators=(",", ":"))
    return "plan-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def feasible_plan(problem: AllocationProblem, assignments: list[Assignment], solver: SolverName, *,
                  status: str, runtime_ms: float, fallback_used: bool = False) -> AllocationPlan:
    assignments = sorted(assignments, key=lambda a: (a.start, a.task_id))
    handoffs, objective = evaluate(problem, assignments)
    assigned = {a.task_id for a in assignments}
    return AllocationPlan(
        plan_id=plan_id(problem.mission.mission_id, problem.graph.graph_version, solver, assignments),
        mission_id=problem.mission.mission_id,
        topology=problem.graph.topology,
        graph_version=problem.graph.graph_version,
        feasible=True,
        solver=solver,
        solver_status=status,
        fallback_used=fallback_used,
        runtime_ms=runtime_ms,
        assignments=tuple(assignments),
        unassigned_tasks=tuple(t.task_id for t in problem.mission.tasks if t.task_id not in assigned),
        handoffs=tuple(handoffs),
        objective=objective,
        config_version=problem.config.version,
    )


def infeasible_plan(problem: AllocationProblem, solver: SolverName, reasons: list[AllocationFailure], detail: str,
                    *, status: str = "", runtime_ms: float = 0.0, fallback_used: bool = False) -> AllocationPlan:
    return AllocationPlan(
        plan_id=plan_id(problem.mission.mission_id, problem.graph.graph_version, solver, []),
        mission_id=problem.mission.mission_id,
        topology=problem.graph.topology,
        graph_version=problem.graph.graph_version,
        feasible=False,
        solver=solver,
        solver_status=status,
        fallback_used=fallback_used,
        runtime_ms=runtime_ms,
        reason_codes=tuple(dict.fromkeys(reasons)),
        detail=detail,
        config_version=problem.config.version,
    )
