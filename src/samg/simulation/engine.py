"""Seeded execution simulator: ``AllocationPlan`` -> ``ExecutionTrace`` (owner: Dev A).

Minimal integration version, written by the integrator for the Phase 2
vertical slice. Dev A owns this module and may replace the execution model;
the public entry point ``run(scenario, graph, plan, seed, ...)`` and the
``ExecutionTrace`` it returns are what Dev B's witness and report generators use.

Execution model (all randomness from ``np.random.default_rng(seed)``):

* Every assigned task goes ``OPEN -> ASSIGNED`` at t = 0. Tasks run in plan
  start order; an agent runs one task at a time.
* A task starts when its agent is free and every prerequisite's output has
  arrived: prerequisite end + per-hop handoff delay along the plan's
  coordination path (``handoff_delay_ms_per_hop``).
* Each hop of a cross-agent handoff fails with ``hop_failure_probability``;
  a failed hop is retransmitted (one extra hop delay) up to
  ``MAX_HOP_ATTEMPTS`` attempts. If every attempt fails, the message is lost
  and the dependent task is ``BLOCKED`` (then ``FAILED`` at mission end).
* Actual duration = nominal x U(1 - jitter, 1 + jitter), where nominal is the plan's
  ``assignment.end - assignment.start`` (the allocator's effective duration for that
  agent, so planning-time overheads such as span of control reach ground truth);
  ``task.duration_ms`` is used only if the plan carries a zero-length interval.
* Optional task failure: ``task_failure_probability`` per task, or a forced
  failure for task IDs in ``forced_failures`` (fault injection for tests and
  attack scenarios). A failed task ends ``EXECUTING -> FAILED``; its
  dependents become ``BLOCKED``.
* A completed task ends ``EXECUTING -> REPORTED_COMPLETE``: the simulator only
  knows the work finished. ``VERIFIED_COMPLETE`` is set by the independent
  witness (``samg.witness``), never by the simulator or an agent.
* Unassigned tasks go ``OPEN -> BLOCKED -> FAILED``.

Times are integer simulated milliseconds so witness events (``sim_time_ms``)
reproduce the ground-truth metrics exactly.
"""

from __future__ import annotations

from collections.abc import Collection

import numpy as np

from samg.domain import (
    AllocationPlan,
    CoordinationGraph,
    ExecutionTrace,
    Scenario,
    TaskOutcome,
    TaskState,
    TaskTransition,
    TopologyCostConfig,
)
from samg.simulation.reward import compute_metrics

ENGINE_VERSION = "sim-v0-integration"
MAX_HOP_ATTEMPTS = 3
DEFAULT_DURATION_JITTER = 0.10

S = TaskState


def run(
    scenario: Scenario,
    graph: CoordinationGraph,
    plan: AllocationPlan,
    seed: int,
    costs: TopologyCostConfig | None = None,
    *,
    duration_jitter: float = DEFAULT_DURATION_JITTER,
    task_failure_probability: float = 0.0,
    forced_failures: Collection[str] = (),
) -> ExecutionTrace:
    """Execute ``plan`` once under ``seed`` and return the ground-truth trace.

    Raises ``ValueError`` for an infeasible plan: the caller must apply the
    reward failure outcome (``compute_reward(None, cfg)``) instead of simulating.
    """
    if not plan.feasible:
        raise ValueError(f"cannot execute infeasible plan {plan.plan_id}: {plan.reason_codes}")
    if plan.graph_version != graph.graph_version or plan.mission_id != scenario.mission.mission_id:
        raise ValueError("plan was not produced for this mission/graph")
    costs = costs or TopologyCostConfig()
    mission = scenario.mission
    rng = np.random.default_rng(seed)

    order = sorted(plan.assignments, key=lambda a: (a.start, a.task_id))
    handoff = {(h.prerequisite_task, h.dependent_task): h for h in plan.handoffs}

    # Pre-draw a fixed block of randomness per task (in plan order) and per handoff
    # hop so that one branch's outcome never shifts another task's draws.
    draws: dict[str, tuple[float, float]] = {a.task_id: (float(rng.random()), float(rng.random())) for a in order}
    hop_draws: dict[tuple[str, str], np.ndarray] = {
        key: rng.random((max(h.hops, 0), MAX_HOP_ATTEMPTS)) for key, h in sorted(handoff.items())
    }

    transitions: list[tuple[int, int, TaskTransition]] = []  # (time, step, transition)
    step = 0

    def emit(task_id: str, agent_id: str | None, frm: TaskState, to: TaskState, t: int) -> None:
        nonlocal step
        transitions.append((t, step, TaskTransition(task_id=task_id, agent_id=agent_id, from_state=frm,
                                                    to_state=to, sim_time=float(t))))
        step += 1

    for a in order:
        emit(a.task_id, a.agent_id, S.OPEN, S.ASSIGNED, 0)

    agent_free: dict[str, int] = {}
    end_time: dict[str, int] = {}
    completed: set[str] = set()
    failed_at: dict[str, int] = {}  # blocked or failed, with the time it became known
    outcomes: dict[str, TaskOutcome] = {}
    comm_failures = 0
    forced = set(forced_failures)

    for a in order:
        task = mission.task(a.task_id)
        ready = 0
        blocked_at: int | None = None
        reason = ""
        for dep in task.dependencies:
            if dep not in completed:
                blocked_at = max(blocked_at or 0, failed_at.get(dep, 0))
                reason = f"UPSTREAM_FAILED:{dep}"
                continue
            h = handoff.get((dep, a.task_id))
            hops = h.hops if h else 0
            delay = 0
            lost = False
            for hop in range(hops):
                attempts = 0
                while attempts < MAX_HOP_ATTEMPTS:
                    ok = hop_draws[(dep, a.task_id)][hop, attempts] >= costs.hop_failure_probability
                    attempts += 1
                    delay += int(round(costs.handoff_delay_ms_per_hop))
                    if ok:
                        break
                    comm_failures += 1
                else:
                    lost = True
                    break
            arrival = end_time[dep] + delay
            if lost:
                blocked_at = max(blocked_at or 0, arrival)
                reason = f"MESSAGE_LOST:{dep}"
            ready = max(ready, arrival)

        if blocked_at is not None:
            emit(a.task_id, a.agent_id, S.ASSIGNED, S.BLOCKED, blocked_at)
            failed_at[a.task_id] = blocked_at
            outcomes[a.task_id] = TaskOutcome(task_id=a.task_id, agent_id=a.agent_id, completed=False,
                                              failure_reason=reason)
            continue

        jitter_u, fail_u = draws[a.task_id]
        start = max(agent_free.get(a.agent_id, 0), ready)
        nominal = a.end - a.start if a.end > a.start else task.duration_ms
        duration = int(round(nominal * (1.0 - duration_jitter + 2.0 * duration_jitter * jitter_u)))
        end = start + max(duration, 1)
        agent_free[a.agent_id] = end
        emit(a.task_id, a.agent_id, S.ASSIGNED, S.EXECUTING, start)
        if a.task_id in forced or fail_u < task_failure_probability:
            emit(a.task_id, a.agent_id, S.EXECUTING, S.FAILED, end)
            failed_at[a.task_id] = end
            outcomes[a.task_id] = TaskOutcome(task_id=a.task_id, agent_id=a.agent_id, completed=False,
                                              start=float(start), end=float(end), failure_reason="TASK_FAILED")
        else:
            emit(a.task_id, a.agent_id, S.EXECUTING, S.REPORTED_COMPLETE, end)
            end_time[a.task_id] = end
            completed.add(a.task_id)
            outcomes[a.task_id] = TaskOutcome(task_id=a.task_id, agent_id=a.agent_id, completed=True,
                                              start=float(start), end=float(end))

    mission_end = max((t for t, _, _ in transitions), default=0)
    for task_id in sorted(failed_at):
        if outcomes[task_id].start is None:  # blocked, never executed
            emit(task_id, plan.assignee(task_id), S.BLOCKED, S.FAILED, mission_end)
    for task in mission.tasks:
        if plan.assignee(task.task_id) is None:
            emit(task.task_id, None, S.OPEN, S.BLOCKED, 0)
            emit(task.task_id, None, S.BLOCKED, S.FAILED, mission_end)
            outcomes[task.task_id] = TaskOutcome(task_id=task.task_id, agent_id=None, completed=False,
                                                 failure_reason="UNASSIGNED")

    ordered = tuple(tr for _, _, tr in sorted(transitions, key=lambda x: (x[0], x[1])))
    outcome_list = tuple(outcomes[t.task_id] for t in mission.tasks)
    metrics = compute_metrics(scenario, graph, plan, outcome_list, costs, communication_failures=comm_failures)
    return ExecutionTrace(
        mission_id=mission.mission_id, epoch=mission.epoch, plan_id=plan.plan_id, topology=plan.topology,
        graph_version=graph.graph_version, seed=seed, transitions=ordered, outcomes=outcome_list, metrics=metrics,
    )


__all__ = ["ENGINE_VERSION", "MAX_HOP_ATTEMPTS", "run"]
