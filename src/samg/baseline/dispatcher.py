"""Conventional centralized greedy dispatcher (the baseline's planner; D042).

A central warehouse controller (the fleet's WMS hub, a software agent) assigns every
task itself. It does not learn, does not select a topology and does not use CP-SAT.

Task order: among tasks whose prerequisites are planned, highest priority first, then
earliest ready time, then task ID. Robot choice: the eligible robot with the smallest

    score = queue_weight  * wait until the robot is free and the inputs have arrived
          + travel_weight * A* travel time from the robot's projected cell to the task
          + exec_weight   * estimated execution time

(the brief's ``travel + execution + queue - priority_bonus``; a per-task priority bonus
cannot change which robot is best, so priority orders tasks instead). Ties go to the
robot ID. Weights come from ``config/baseline.yaml`` and are declared once, not tuned
against SAMG. Communication with robots goes through the controller star, the same
hop delay/loss/retry rules as SAMG (``topology.HopTable`` over the hierarchical template).
"""

from __future__ import annotations

import heapq
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from samg.allocation.common import AllocationProblem, feasible_plan
from samg.domain import AllocationPlan, Assignment, SolverName
from samg.twin.agents import RobotSpec
from samg.twin.environment import RobotState, _legs
from samg.twin.path_planning import NoRoute, distance
from samg.twin.task_generator import WarehouseTask

BASELINE_VERSION = "baseline-v1"
CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "baseline.yaml"
MS = 1000.0


@dataclass(frozen=True)
class DispatchWeights:
    queue_weight: float = 1.0
    travel_weight: float = 1.0
    exec_weight: float = 1.0

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> DispatchWeights:
        if not path.exists():
            return cls()
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(**data.get("dispatcher", {}))


def _pack_station(env: Any) -> str:
    return next(s.station_id for s in env.layout.stations if s.kind == "pack")


def _target_cells(task: WarehouseTask, robot: RobotSpec, env: Any) -> tuple[Any, Any] | None:
    """(first target, final cell) of the task's physical legs; None for stationary work."""
    if not robot.mobile or task.kind == "PACK":
        return None
    legs = _legs(task, env.layout, env.inventory, _pack_station(env), env.timing)
    return legs[0][0], legs[-1][0]


def dispatch(problem: AllocationProblem, env: Any, wtasks: dict[str, WarehouseTask],
             states: dict[str, RobotState], weights: DispatchWeights | None = None) -> AllocationPlan:
    """Greedy centralized assignment of every not-yet-done task in ``problem``."""
    started = time.perf_counter()
    weights = weights or DispatchWeights()
    mission = problem.mission
    robots = {r.robot_id: r for r in env.robots}
    cell = {rid: st.cell for rid, st in states.items()}
    free_at = {a.agent_id: 0.0 for a in problem.scenario.agents}
    capacity = {a.agent_id: a.capacity for a in problem.scenario.agents}
    budget = {a.agent_id: a.resource_budget for a in problem.scenario.agents}
    assigned: dict[str, Assignment] = {}
    skipped: set[str] = set()

    pending = {t.task_id: set(t.dependencies) for t in mission.tasks}
    children: dict[str, list[str]] = {t.task_id: [] for t in mission.tasks}
    for pre, dep in mission.dependency_edges():
        children[pre].append(dep)

    def ready_key(task_id: str) -> tuple:
        deps = mission.task(task_id).dependencies
        ready = max((assigned[d].end for d in deps if d in assigned), default=0.0)
        return (-mission.task(task_id).priority_weight, ready, task_id)

    heap = [ready_key(t) for t, d in pending.items() if not d]
    heapq.heapify(heap)
    while heap:
        task_id = heapq.heappop(heap)[-1]
        task = mission.task(task_id)
        best: tuple | None = None
        if not any(d in skipped for d in task.dependencies):
            for rid in problem.eligible[task_id]:
                if capacity[rid] <= 0 or budget[rid] < task.resource_demand:
                    continue
                routes = [problem.hops.route(assigned[d].agent_id, rid) for d in task.dependencies]
                if any(r is None for r in routes):
                    continue
                inputs_at = max((assigned[d].end + r.delay for d, r in zip(task.dependencies, routes)), default=0.0)
                start = max(free_at[rid], inputs_at)
                travel_ms = 0.0
                cells = _target_cells(wtasks[task_id], robots[rid], env) if rid in robots else None
                if cells is not None:
                    try:
                        travel_ms = distance(env.layout, cell[rid], cells[0]) / robots[rid].speed * MS
                    except NoRoute:
                        continue
                exec_ms = problem.effective_duration(task_id, rid)
                score = (weights.queue_weight * start + weights.travel_weight * travel_ms
                         + weights.exec_weight * exec_ms)
                cand = (round(score, 6), rid, start, exec_ms, cells)
                if best is None or cand < best:
                    best = cand
        if best is None:
            skipped.add(task_id)  # conventional behaviour: the task stays unassigned/blocked
        else:
            _, rid, start, exec_ms, cells = best
            assigned[task_id] = Assignment(task_id=task_id, agent_id=rid, start=start, end=start + exec_ms)
            free_at[rid] = start + exec_ms
            capacity[rid] -= 1
            budget[rid] -= task.resource_demand
            if cells is not None:
                cell[rid] = cells[1]
        for child in children[task_id]:
            pending[child].discard(task_id)
            if not pending[child]:
                heapq.heappush(heap, ready_key(child))

    plan = feasible_plan(problem, list(assigned.values()), SolverName.GREEDY, status="BASELINE_DISPATCH",
                         runtime_ms=(time.perf_counter() - started) * 1000)
    return plan
