"""Conventional baseline execution over the warehouse twin (D042).

Same environment, orders, tasks, robots, seeds, physics, simulator and fault injections
as SAMG (``samg.twin``); only the coordination architecture differs:

* planning: ``baseline.dispatcher.dispatch`` over a fixed controller star (the fleet's WMS
  hub, built with the hierarchical template), no topology selection, no LinUCB, no CP-SAT;
* trust: robots' signed claims are authenticated (signature check, as any conventional
  system would) and then believed. There is no witness corroboration and no evidence gate.
  The next wave plans from what was *claimed* complete, so a false completion is never
  redone and its downstream work is planned as if it had happened;
* recovery: robots that broke down are excluded and their unfinished tasks are re-dispatched
  greedily in the next wave (conventional centralized recovery, no topology change).

Evaluation uses ground truth the controller never sees: the record carries the evaluator's
ground-truth observations (``WitnessService`` over the simulator trace) so the twin's KPI code
scores both modes with one definition, and ``run_metrics`` adds believed-versus-true counts.
Nothing in ``samg.twin``, ``samg.api`` or ``web/`` is modified.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import timedelta
from typing import Any

from samg.allocation import allocate
from samg.allocation.common import AllocationProblem
from samg.baseline.dispatcher import BASELINE_VERSION, DispatchWeights, dispatch
from samg.context import extract_features
from samg.domain import EventType, PolicyMode, ReasonCode, TaskState, TopologyName
from samg.domain.config import V2_HOP_FAILURE_PROBABILITY, SimulationModelConfig
from samg.evaluation.attacks import apply_attack
from samg.learning.base import PolicyDecision
from samg.orchestration import SIM_BASE_TIME, MissionRunRecord, mission_keys
from samg.simulation import compute_reward
from samg.simulation import run as simulate
from samg.assurance.signatures import verify_event
from samg.topology import build_graph
from samg.twin.adapter import (
    MAX_PHYSICAL_PASSES,
    OVERRUN_TOLERANCE_MS,
    Wave,
    WarehouseEnv,
    WarehouseRun,
    _merge,
    _resolve_injections,
    build_state,
    execute,
    initial_states,
    make_world,
)
from samg.twin.congestion import AisleLocks
from samg.twin.environment import replay_wave
from samg.twin.layout import load_config
from samg.twin.orders import orders_from_config
from samg.twin.scenarios import RunSpec
from samg.twin.task_generator import generate_tasks
from samg.witness.reports import draft_reports, sign_reports
from samg.witness.service import WitnessService

BASELINE_KIND = "BASELINE-CENTRAL-GREEDY"
STAR = TopologyName.HIERARCHICAL  # controller -> robot star: the hierarchical template over the WMS hub
MODES = ("samg", "baseline")


def run_wave_baseline(env: WarehouseEnv, wtasks: dict[str, Any], task_ids: list[str], *, done: frozenset[str],
                      number: int, mission_id: str, mission_index: int, seed: int, states: dict[str, Any],
                      locks: AisleLocks, t_offset: float, injections: tuple, excluded: frozenset[str],
                      weights: DispatchWeights, planner: str = "greedy") -> tuple[Wave, dict[str, Any]]:
    tasks = [wtasks[t] for t in task_ids]
    scenario = env.scenario(mission_id, tasks, done=done, seed=seed, unavailable=excluded, wave=number)
    verdict, graph = build_graph(scenario, STAR, env.settings.costs)
    ctx = extract_features(scenario)
    decision = PolicyDecision(
        policy_kind=BASELINE_KIND, policy_version=BASELINE_VERSION, topology=STAR if graph else None,
        eligible=(STAR,) if graph else (), feature_schema_version=ctx.feature_schema_version,
        context=ctx.features, reason_codes=() if graph else (ReasonCode.NO_ELIGIBLE_TOPOLOGY,))
    base = dict(mission_index=mission_index, seed=seed, scenario_id=scenario.scenario_id, mission_id=mission_id,
                epoch=scenario.mission.epoch, policy_instance=BASELINE_KIND, policy_kind=BASELINE_KIND,
                mode=PolicyMode.VULNERABLE,  # trusts authenticated claims; no evidence gate
                context=ctx, eligibility={STAR: verdict}, decision=decision,
                topology_decision_id=f"baseline:{mission_id}")
    info: dict[str, Any] = {"wave": number, "believed_complete": [], "true_complete": [], "claims": 0,
                            "claims_accepted": 0, "false_claims": 0, "false_claims_accepted": 0,
                            "handoff_hops": 0, "retransmissions": 0}
    if graph is None:
        rec = MissionRunRecord(**base)
        return (Wave(number=number, mission_id=mission_id, mission_index=mission_index, t_offset=t_offset,
                     task_ids=list(task_ids), record=rec, replay=None, injections_applied=[], physical_passes=0,
                     delays_ms={}, verified={}, failing_robots=frozenset(), excluded_robots=excluded), info)

    if planner == "cpsat":  # ladder rung B1: SAMG's optimiser over the same star, still trusting claims
        plan = allocate(scenario, graph, env.settings.costs, env.settings.allocation)
    else:
        plan = dispatch(AllocationProblem(scenario, graph, env.settings.costs, env.settings.allocation),
                        env, wtasks, states, weights)
    if not plan.feasible:  # CP-SAT (rung B1) found no plan: like SAMG's twin path, the wave does not execute
        rec = MissionRunRecord(**base, graph=graph, plan=plan)
        return (Wave(number=number, mission_id=mission_id, mission_index=mission_index, t_offset=t_offset,
                     task_ids=list(task_ids), record=rec, replay=None, injections_applied=[], physical_passes=0,
                     delays_ms={}, verified={}, failing_robots=frozenset(), excluded_robots=excluded), info)
    forced, failing, breakdowns, delays, attack, applied = _resolve_injections(injections, plan, wtasks,
                                                                               mission_index, STAR)
    forced = set(forced)
    if attack is not None:
        sabotaged = attack.sabotaged_task(mission_index, plan)
        if sabotaged:
            forced.add(sabotaged)
    robots = {r.robot_id: r for r in env.robots}
    phys: dict[str, float] = {}
    passes = 0
    for passes in range(1, MAX_PHYSICAL_PASSES + 1):
        trace = simulate(scenario, graph, plan, seed, env.settings.costs, forced_failures=forced,
                         task_delays_ms=_merge(delays, phys), agent_breakdowns=breakdowns)
        rep = replay_wave(layout=env.layout, inventory=env.inventory, robots=robots, states=states, tasks=wtasks,
                          plan=plan, trace=trace, timing=env.timing, locks=copy.deepcopy(locks), t_offset=t_offset,
                          failing_robots=frozenset(failing))
        if not rep.overruns_ms or max(rep.overruns_ms.values()) <= OVERRUN_TOLERANCE_MS:
            break
        phys = _merge(phys, rep.overruns_ms)
    executed_failures = {(tr.agent_id, tr.task_id) for tr in trace.transitions
                         if tr.from_state is TaskState.EXECUTING and tr.to_state is TaskState.FAILED}
    failing = {r for r in failing if (r, breakdowns.get(r)) in executed_failures}
    replay = replay_wave(layout=env.layout, inventory=env.inventory, robots=robots, states=states, tasks=wtasks,
                         plan=plan, trace=trace, timing=env.timing, locks=locks, t_offset=t_offset,
                         failing_robots=frozenset(failing))

    # Robots report (honestly, or falsely if compromised); the controller authenticates and believes.
    registry, ring = mission_keys(scenario, env.settings.security)
    base_time = SIM_BASE_TIME + timedelta(days=mission_index)
    gt_reward = compute_reward(trace.metrics, env.settings.reward)
    drafts = draft_reports(trace, plan, gt_reward)
    attacked = bool(attack is not None and attack.active(mission_index))
    if attacked:
        drafts = apply_attack(drafts, trace, plan, gt_reward, attack, agents=[a.agent_id for a in scenario.agents])
    agent_events, oracle = sign_reports(drafts, mission_id=mission_id, epoch=scenario.mission.epoch,
                                        base_time=base_time, registry=registry, ring=ring)
    accepted = [e for e in agent_events if verify_event(e, registry) is None]
    believed = sorted({e.task_id for e in accepted if e.event_type is EventType.TASK_COMPLETE_CLAIM and e.task_id})
    true_done = sorted(o.task_id for o in trace.outcomes if o.completed)
    false_ids = {eid for eid, is_false in oracle.items() if is_false}

    # Evaluator-only ground truth (never seen by the controller): scores both modes with one KPI definition.
    gt_obs = WitnessService(env.settings.security.witness.identity_id, registry, ring).observe(trace, base_time)
    verified = {w.task_id: w.to_state.value for w in gt_obs}
    info.update(believed_complete=believed, true_complete=true_done, claims=len(agent_events),
                claims_accepted=len(accepted), false_claims=len(false_ids),
                false_claims_accepted=sum(1 for e in accepted if e.event_id in false_ids),
                handoff_hops=sum(h.hops for h in plan.handoffs),
                retransmissions=trace.metrics.communication_failures)
    rec = MissionRunRecord(**base, graph=graph, plan=plan, trace=trace, ground_truth_reward=gt_reward,
                           identities=tuple(registry.identities()), witness_events=tuple(gt_obs),
                           agent_events=tuple(agent_events), false_claim_event_ids=tuple(sorted(false_ids)),
                           attacked=attacked)
    wave = Wave(number=number, mission_id=mission_id, mission_index=mission_index, t_offset=t_offset,
                task_ids=list(task_ids), record=rec, replay=replay, injections_applied=applied,
                physical_passes=passes, delays_ms=_merge(delays, phys), verified=verified,
                failing_robots=frozenset(failing), excluded_robots=excluded)
    return wave, info


def make_env(spec: RunSpec, cfg: dict[str, Any], sim: SimulationModelConfig | None = None) -> WarehouseEnv:
    """The twin's environment for ``spec``; with ``sim`` the same simulator model is applied to it.

    ``sim`` with ``handoff_max_attempts < 3`` is model v2: hop loss is at least the predeclared v2
    value (a ``comm_failure`` injection keeps its higher twin value). ``None`` = the twin unchanged.
    """
    env = WarehouseEnv(cfg, spec.injections, use_cpsat=spec.use_cpsat)
    if sim is not None:
        costs = env.settings.costs
        hop_p = max(costs.hop_failure_probability, V2_HOP_FAILURE_PROBABILITY)             if sim.handoff_max_attempts < 3 else costs.hop_failure_probability
        env.settings = replace(env.settings, costs=costs.model_copy(
            update={"simulation_model": sim, "hop_failure_probability": hop_p}))
    return env


def run_warehouse_samg(spec: RunSpec, cfg: dict[str, Any] | None = None,
                       sim: SimulationModelConfig | None = None) -> WarehouseRun:
    """``twin.adapter.run_warehouse`` composed from the twin's own functions, with an optional model."""
    cfg = cfg or load_config()
    env = make_env(spec, cfg, sim)
    orders = list(spec.orders) if spec.orders is not None else orders_from_config(cfg)
    learnable = spec.policy in ("adaptive", "ucb1")
    experience = int(cfg["learning"]["experience"] if spec.experience is None else spec.experience) if learnable else 0
    world = make_world(env, spec.policy, experience=experience, cfg=cfg)
    before = world.policy.snapshot()
    start = initial_states(env)
    waves, holds, wtasks, final = execute(env, world, orders, seed=spec.seed, mission_prefix=f"WH{spec.seed:03d}",
                                          index_base=experience, injections=spec.injections, replan=spec.replan,
                                          max_waves=spec.max_waves, states=start)
    return WarehouseRun(spec=spec, env=env, orders=orders, holds=holds, tasks=wtasks, waves=waves,
                        initial_states=start, final_states=final, policy_kind=world.policy.kind,
                        experience=experience, policy_state_before=before, policy_state_after=world.policy.snapshot(),
                        extra={"mode": "samg"})


def run_warehouse_baseline(spec: RunSpec, cfg: dict[str, Any] | None = None,
                           weights: DispatchWeights | None = None,
                           sim: SimulationModelConfig | None = None, planner: str = "greedy") -> WarehouseRun:
    """The baseline counterpart of ``twin.adapter.run_warehouse`` for the identical ``RunSpec``."""
    cfg = cfg or load_config()
    weights = weights or DispatchWeights.load()
    env = make_env(spec, cfg, sim)
    orders = list(spec.orders) if spec.orders is not None else orders_from_config(cfg)
    task_list, holds = generate_tasks(orders, env.inventory, env.layout, env.robots, env.cfg)
    wtasks = {t.task_id: t for t in task_list}
    start = initial_states(env)
    states = dict(start)
    locks = AisleLocks()
    waves: list[Wave] = []
    infos: list[dict[str, Any]] = []
    remaining = [t.task_id for t in task_list]
    done: set[str] = set()
    excluded: frozenset[str] = frozenset()
    t_offset = 0.0
    prefix = f"BL{spec.seed:03d}"
    for number in range(1, spec.max_waves + 1):
        if not remaining:
            break
        wave, info = run_wave_baseline(env, wtasks, remaining, done=frozenset(done), number=number,
                                       mission_id=f"{prefix}-{number}", mission_index=number - 1,
                                       seed=spec.seed + number - 1, states=states, locks=locks, t_offset=t_offset,
                                       injections=spec.injections if number == 1 else (), excluded=excluded,
                                       weights=weights, planner=planner)
        waves.append(wave)
        infos.append(info)
        if wave.replay is None:
            break
        states = dict(wave.replay.states)
        done |= set(info["believed_complete"])  # the controller's belief, not ground truth
        remaining = [t for t in remaining if t not in done]
        excluded = excluded | wave.failing_robots
        t_offset = wave.end_s
        if not spec.replan:
            break
    empty = {"kind": BASELINE_KIND, "version": BASELINE_VERSION}
    return WarehouseRun(spec=spec, env=env, orders=orders, holds=holds, tasks=wtasks, waves=waves,
                        initial_states=start, final_states=states, policy_kind=BASELINE_KIND, experience=0,
                        policy_state_before=empty, policy_state_after=empty,
                        extra={"mode": "baseline", "planner": planner, "baseline_waves": infos,
                               "dispatch_weights": weights.__dict__})


def run_mode(spec: RunSpec, mode: str, cfg: dict[str, Any] | None = None,
             sim: SimulationModelConfig | None = None) -> WarehouseRun:
    """Run the identical ``RunSpec`` under SAMG (the twin's pipeline) or the conventional baseline.

    ``sim`` (e.g. ``SimulationModelConfig()`` = model v2 with common random numbers) is applied to
    both modes identically; ``None`` keeps the twin's default model.
    """
    if mode == "samg":
        return run_warehouse_samg(spec, cfg, sim)
    if mode == "baseline":
        return run_warehouse_baseline(spec, cfg, sim=sim)
    raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")


def run_metrics(run: WarehouseRun) -> dict[str, Any]:
    """Twin KPIs (one definition for both modes) plus believed-versus-true task/order counts."""
    state = build_state(run)
    kpis = dict(state["kpis"])
    true_done: set[str] = set()
    believed: set[str] = set()
    hops = retrans = claims = claims_ok = false_c = false_ok = 0
    infos = run.extra.get("baseline_waves")
    for i, w in enumerate(run.waves):
        if w.record.trace is not None:
            true_done |= {o.task_id for o in w.record.trace.outcomes if o.completed}
            retrans += w.record.trace.metrics.communication_failures
        if w.record.plan is not None:
            hops += sum(h.hops for h in w.record.plan.handoffs)
        if infos:
            info = infos[i]
            believed |= set(info["believed_complete"])
            claims += info["claims"]
            claims_ok += info["claims_accepted"]
            false_c += info["false_claims"]
            false_ok += info["false_claims_accepted"]
        else:  # SAMG: the next wave plans from witness-verified completions only
            believed |= {t for t, s in w.verified.items() if s == TaskState.VERIFIED_COMPLETE.value}
            claims += len(w.record.agent_events)
            false_ids = set(w.record.false_claim_event_ids)
            false_c += len(false_ids)
            accepted = {d.event_id for d in w.record.final_decisions
                        if d.status.value in ("CORROBORATED", "AUTHENTICATED")}
            claims_ok += len(accepted)
            false_ok += len(false_ids & accepted)
    corrupted = sorted(believed - true_done)
    by_order: dict[str, list[str]] = {}
    for t in run.tasks.values():
        by_order.setdefault(t.order_id, []).append(t.task_id)
    truly_fulfilled = [o for o, ts in by_order.items() if all(t in true_done for t in ts)]
    dispatched = {o["id"] for o in state.get("orders", []) if o.get("dispatched_at") is not None} \
        if state.get("orders") and "id" in state["orders"][0] else set()
    kpis.update(
        mode=run.extra.get("mode", "samg"),
        tasks_total=len(run.tasks), tasks_truly_completed=len(true_done & set(run.tasks)),
        tasks_believed_completed=len(believed & set(run.tasks)), corrupted_tasks=len(corrupted),
        orders_truly_fulfilled=len(truly_fulfilled),
        orders_shipped_incomplete=len({o for o in dispatched if o not in set(truly_fulfilled)}),
        handoff_hops=hops, retransmissions=retrans, claims=claims, claims_accepted=claims_ok,
        false_claims=false_c, false_claims_accepted=false_ok, false_claims_rejected=false_c - false_ok,
        coordination=("CENTRALIZED GREEDY" if run.extra.get("mode") == "baseline"
                      else "SECURE ADAPTIVE MISSION GRAPH"),
    )
    return kpis
