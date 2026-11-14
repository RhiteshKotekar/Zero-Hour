"""CP-SAT allocator (brief §5.4, §7.1; D003).

Variables:
- ``x[t, a]``: task ``t`` assigned to eligible agent ``a``.
- ``y[i, j, a, b]``: for dependency ``i -> j``, ``i`` on ``a`` and ``j`` on ``b``;
  only created when ``a == b`` or a permitted coordination route exists, so a
  disconnected pair is infeasible rather than free.
- start/end per task, optional intervals per (task, agent) with no-overlap per agent.

Constraints: one assignee per mandatory task (at most one for optional tasks; a
task can only run if its prerequisites run), agent capacity and resource budget,
precedence including graph-derived handoff delay, reachable handoff paths.

Objective (integer-scaled): makespan, handoff cost, resource use, busiest-agent
load and unserved optional priority, with weights from ``config/allocation.yaml``.

Times are solved in units of ``time_unit_ms`` with durations and delays rounded
UP, so the reported millisecond schedule (start + true duration) never violates
precedence or overlap. A single worker plus a fixed seed keeps runs deterministic.
"""

from __future__ import annotations

import math
import time

from ortools.sat.python import cp_model

from samg.allocation.common import MINUTE_MS, AllocationProblem, feasible_plan, infeasible_plan
from samg.domain import AllocationFailure, AllocationPlan, Assignment, SolverName

OBJECTIVE_SCALE = 60_000  # makes the makespan-per-minute coefficient exact for 1 s time units


def _units(ms: float, unit_ms: int) -> int:
    return int(math.ceil(ms / unit_ms - 1e-9))


def allocate_cpsat(problem: AllocationProblem) -> tuple[AllocationPlan | None, str]:
    """Solve with CP-SAT.

    Returns ``(plan, status)``. ``plan`` is ``None`` when CP-SAT found no feasible
    solution without proving infeasibility (time limit / unknown); the caller
    then falls back to greedy.
    """
    started = time.perf_counter()
    reasons, detail = problem.precheck()
    if reasons:
        return infeasible_plan(problem, SolverName.CP_SAT, reasons, detail, status="PRECHECK"), "PRECHECK"

    mission = problem.mission
    settings = problem.config.cpsat
    unit = settings.time_unit_ms
    weights = problem.config.weights
    agents = {a.agent_id: a for a in problem.scenario.agents}
    tasks = list(mission.tasks)
    dur = {t.task_id: _units(t.duration_ms, unit) for t in tasks}

    max_delay = _units(problem.costs.max_path_hops * problem.costs.handoff_delay_ms_per_hop, unit)
    horizon = sum(dur.values()) + max_delay * max(1, len(mission.dependency_edges()))

    model = cp_model.CpModel()
    x: dict[tuple[str, str], cp_model.IntVar] = {}
    for t in tasks:
        for a in problem.eligible[t.task_id]:
            x[t.task_id, a] = model.new_bool_var(f"x[{t.task_id},{a}]")

    run: dict[str, cp_model.IntVar] = {}
    for t in tasks:
        run[t.task_id] = model.new_bool_var(f"run[{t.task_id}]")
        model.add(sum(x[t.task_id, a] for a in problem.eligible[t.task_id]) == run[t.task_id])
        if t.mandatory:
            model.add(run[t.task_id] == 1)

    for a, agent in agents.items():
        mine = [(t, x[t.task_id, a]) for t in tasks if (t.task_id, a) in x]
        if not mine:
            continue
        model.add(sum(v for _, v in mine) <= agent.capacity)
        model.add(sum(int(round(t.resource_demand * 1000)) * v for t, v in mine)
                  <= int(math.floor(agent.resource_budget * 1000 + 1e-6)))

    start = {t.task_id: model.new_int_var(0, horizon, f"s[{t.task_id}]") for t in tasks}
    end = {t.task_id: model.new_int_var(0, horizon, f"e[{t.task_id}]") for t in tasks}
    for t in tasks:
        model.add(end[t.task_id] == start[t.task_id] + dur[t.task_id])

    per_agent_intervals: dict[str, list] = {a: [] for a in agents}
    for (task_id, a), var in x.items():
        per_agent_intervals[a].append(model.new_optional_interval_var(
            start[task_id], dur[task_id], end[task_id], var, f"iv[{task_id},{a}]"))
    for intervals in per_agent_intervals.values():
        if len(intervals) > 1:
            model.add_no_overlap(intervals)

    handoff_terms = []
    for prereq, dependent in mission.dependency_edges():
        model.add(run[dependent] <= run[prereq])
        ys = []
        delay_terms = []
        for a in problem.eligible[prereq]:
            for b in problem.eligible[dependent]:
                route = problem.hops.route(a, b)
                if route is None:
                    continue
                y = model.new_bool_var(f"y[{prereq},{dependent},{a},{b}]")
                ys.append((a, b, y))
                if route.hops:
                    delay_terms.append(_units(route.delay, unit) * y)
                    handoff_terms.append(int(round(weights["handoff_cost"] * route.cost * OBJECTIVE_SCALE)) * y)
        for a in problem.eligible[prereq]:
            model.add(sum(y for aa, _, y in ys if aa == a) <= x[prereq, a])
        for b in problem.eligible[dependent]:
            model.add(sum(y for _, bb, y in ys if bb == b) == x[dependent, b])
        model.add(start[dependent] >= end[prereq] + sum(delay_terms)).only_enforce_if(run[dependent])

    makespan = model.new_int_var(0, horizon, "makespan")
    for t in tasks:
        model.add(makespan >= end[t.task_id]).only_enforce_if(run[t.task_id])
    max_load = model.new_int_var(0, sum(dur.values()), "max_load")
    for a in agents:
        mine = [dur[task_id] * v for (task_id, aa), v in x.items() if aa == a]
        if mine:
            model.add(max_load >= sum(mine))

    per_unit_minutes = unit / MINUTE_MS
    objective = [
        int(round(weights["makespan"] * per_unit_minutes * OBJECTIVE_SCALE)) * makespan,
        int(round(weights["max_agent_load"] * per_unit_minutes * OBJECTIVE_SCALE)) * max_load,
        *handoff_terms,
    ]
    if weights["resource_use"]:
        objective += [int(round(weights["resource_use"] * t.resource_demand * OBJECTIVE_SCALE)) * x[t.task_id, a]
                      for t in tasks for a in problem.eligible[t.task_id]]
    objective += [int(round(weights["unserved_priority"] * t.priority_weight * OBJECTIVE_SCALE)) * (1 - run[t.task_id])
                  for t in tasks if not t.mandatory]
    model.minimize(sum(objective))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = settings.time_limit_s
    solver.parameters.num_workers = settings.num_workers
    solver.parameters.random_seed = settings.random_seed
    code = solver.solve(model)
    status = solver.status_name(code)
    runtime_ms = (time.perf_counter() - started) * 1000

    if code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        assignments = [
            Assignment(task_id=task_id, agent_id=a, start=solver.value(start[task_id]) * unit,
                       end=solver.value(start[task_id]) * unit + mission.task(task_id).duration_ms)
            for (task_id, a), var in x.items() if solver.value(var)
        ]
        return feasible_plan(problem, assignments, SolverName.CP_SAT, status=status, runtime_ms=runtime_ms), status
    if code == cp_model.INFEASIBLE:
        return infeasible_plan(problem, SolverName.CP_SAT, [AllocationFailure.SOLVER_INFEASIBLE],
                               "CP-SAT proved no assignment satisfies capability, capacity, budget and path "
                               "constraints", status=status, runtime_ms=runtime_ms), status
    return None, status
