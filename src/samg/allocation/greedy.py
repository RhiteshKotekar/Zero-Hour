"""Deterministic greedy fallback allocator (D003).

Task order: among tasks whose prerequisites are decided, pick by
(mandatory first, dependency depth, fewest capable agents, task ID).
Candidate order: (incremental objective, most remaining capacity, agent ID).
It applies the same graph-derived handoff cost and delay as CP-SAT, never
violates a constraint, and reports infeasibility with reason codes.
"""

from __future__ import annotations

import heapq
import time

from samg.allocation.common import MINUTE_MS, AllocationProblem, feasible_plan, infeasible_plan
from samg.domain import AllocationFailure, AllocationPlan, Assignment, SolverName


def allocate_greedy(problem: AllocationProblem, *, fallback_used: bool = False) -> AllocationPlan:
    started = time.perf_counter()
    reasons, detail = problem.precheck()
    if reasons:
        return infeasible_plan(problem, SolverName.GREEDY, reasons, detail, status="PRECHECK",
                               fallback_used=fallback_used)

    mission = problem.mission
    weights = problem.config.weights
    depth = mission.depth()
    agents = {a.agent_id: a for a in problem.scenario.agents}
    remaining_capacity = {a: agents[a].capacity for a in agents}
    remaining_budget = {a: agents[a].resource_budget for a in agents}
    agent_free = {a: 0.0 for a in agents}
    agent_load = {a: 0.0 for a in agents}
    makespan = 0.0
    max_load = 0.0

    assigned: dict[str, Assignment] = {}
    skipped: set[str] = set()
    pending_deps = {t.task_id: set(t.dependencies) for t in mission.tasks}
    children: dict[str, list[str]] = {t.task_id: [] for t in mission.tasks}
    for prereq, dependent in mission.dependency_edges():
        children[prereq].append(dependent)

    def key(task_id: str) -> tuple:
        task = mission.task(task_id)
        return (not task.mandatory, depth[task_id], len(problem.eligible[task_id]), task_id)

    ready = [key(t) for t, deps in pending_deps.items() if not deps]
    heapq.heapify(ready)
    while ready:
        task_id = heapq.heappop(ready)[-1]
        task = mission.task(task_id)
        preds = task.dependencies
        blocked = any(p in skipped for p in preds)

        best: tuple | None = None
        saw_capable = saw_with_room = False
        if not blocked:
            for agent_id in problem.eligible[task_id]:
                saw_capable = True
                if remaining_capacity[agent_id] <= 0 or remaining_budget[agent_id] < task.resource_demand:
                    continue
                saw_with_room = True
                routes = [problem.hops.route(assigned[p].agent_id, agent_id) for p in preds]
                if any(r is None for r in routes):
                    continue
                ready_at = max([assigned[p].end + r.delay for p, r in zip(preds, routes)], default=0.0)
                start = max(agent_free[agent_id], ready_at)
                end = start + task.duration_ms
                new_load = agent_load[agent_id] + task.duration_ms
                cost = (weights["makespan"] * (max(makespan, end) - makespan) / MINUTE_MS
                        + weights["handoff_cost"] * sum(r.cost for r in routes)
                        + weights["resource_use"] * task.resource_demand
                        + weights["max_agent_load"] * (max(max_load, new_load) - max_load) / MINUTE_MS)
                candidate = (round(cost, 9), -remaining_capacity[agent_id], agent_id, start, end)
                if best is None or candidate < best:
                    best = candidate

        if best is None:
            if task.mandatory:
                if blocked or (saw_capable and not saw_with_room):
                    reason = AllocationFailure.CAPACITY_EXCEEDED
                elif not saw_capable:
                    reason = AllocationFailure.NO_CAPABLE_AGENT
                else:
                    reason = AllocationFailure.NO_PERMITTED_PATH
                return infeasible_plan(problem, SolverName.GREEDY, [reason],
                                       f"greedy could not place mandatory task {task_id}", status="INFEASIBLE",
                                       runtime_ms=(time.perf_counter() - started) * 1000,
                                       fallback_used=fallback_used)
            skipped.add(task_id)
        else:
            _, _, agent_id, start, end = best
            assigned[task_id] = Assignment(task_id=task_id, agent_id=agent_id, start=start, end=end)
            remaining_capacity[agent_id] -= 1
            remaining_budget[agent_id] -= task.resource_demand
            agent_free[agent_id] = end
            agent_load[agent_id] += task.duration_ms
            makespan = max(makespan, end)
            max_load = max(max_load, agent_load[agent_id])

        for child in children[task_id]:
            pending_deps[child].discard(task_id)
            if not pending_deps[child]:
                heapq.heappush(ready, key(child))

    return feasible_plan(problem, list(assigned.values()), SolverName.GREEDY, status="FEASIBLE",
                         runtime_ms=(time.perf_counter() - started) * 1000, fallback_used=fallback_used)
