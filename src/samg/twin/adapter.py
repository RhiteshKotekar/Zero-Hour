"""Warehouse -> SAMG -> warehouse: the digital-twin run loop (owner: Dev B).

    orders + inventory --task_generator--> SAMG MissionSpec (one "wave")
      -> extract_features -> feasible_topologies -> policy.select     (SAMG, unchanged)
      -> physical dry run: simulate + replay, feed overruns back as task delays
      -> run_single_mission(..., task_delays_ms, feasible)             (SAMG: allocate, simulate,
                                                                         witness, ACP, guarded update)
      -> replay_wave (robot routes, aisle locks, battery)              (warehouse physics)
      -> tasks the witness did not verify -> next wave (replanning with failed robots excluded)

Nothing here chooses a topology, allocates, validates, computes a reward or learns:
those are SAMG's public functions. This module only translates and records.
"""

from __future__ import annotations

import copy
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import timedelta
from functools import lru_cache
from statistics import fmean, pstdev
from typing import Any

from samg.allocation import feasible_topologies
from samg.context import extract_features
from samg.domain import AgentEvent, EventType, MissionSpec, PolicyMode, Scenario, TaskState, TopologyName
from samg.evaluation.attacks import AttackConfig
from samg.learning import ARM_ORDER, make_policy
from samg.learning.base import TopologyPolicy
from samg.orchestration import SIM_BASE_TIME, MissionRunRecord, RunSettings, World, run_single_mission
from samg.simulation.engine import run as simulate
from samg.twin.agents import RobotSpec, robots_from_config, to_agent_profile
from samg.twin.congestion import AisleLocks
from samg.twin.environment import INF, RobotState, Segment, WaveReplay, _clip, clip_overlaps, replay_wave
from samg.twin.inventory import Inventory
from samg.twin.layout import Layout, load_config
from samg.twin.orders import Order, generate_orders, orders_from_config, s_to_clock
from samg.twin.scenarios import INJECTION_KINDS, POLICY_KINDS, Injection, RunSpec
from samg.twin.task_generator import OrderHold, WarehouseTask, generate_tasks, to_task_specs

MS = 1000.0
STATE_VERSION = "wh-state-v1"
MAX_PHYSICAL_PASSES = 4
OVERRUN_TOLERANCE_MS = 250.0


# --- environment ---------------------------------------------------------------


class WarehouseEnv:
    """Static world for one run: layout (with blockages), inventory, fleet, SAMG settings."""

    def __init__(self, cfg: dict[str, Any], injections: tuple[Injection, ...] = (), *, use_cpsat: bool = True) -> None:
        self.cfg = cfg
        layout = Layout.from_config(cfg)
        blocked = {i.aisle for i in injections if i.kind == "aisle_blockage"}
        self.layout = layout.with_blocked_aisles(blocked) if blocked else layout
        stock = {i.sku: 0 for i in injections if i.kind == "inventory_unavailable"}
        self.inventory = Inventory.from_config(cfg, self.layout, stock)  # type: ignore[arg-type]
        self.robots: list[RobotSpec] = robots_from_config(cfg, self.layout)
        self.robot = {r.robot_id: r for r in self.robots}
        base = RunSettings.load(use_cpsat=use_cpsat)
        samg = cfg["samg"]
        hop_p = samg["comm_failure_probability"] if any(i.kind == "comm_failure" for i in injections) \
            else samg["hop_failure_probability"]
        update: dict[str, Any] = {"handoff_delay_ms_per_hop": samg["handoff_delay_s_per_hop"] * MS,
                                  "hop_failure_probability": hop_p}
        if "distributed_max_degree" in samg:   # twin-fleet override (D043); the core config keeps its value
            update["distributed_max_degree"] = int(samg["distributed_max_degree"])
        costs = base.costs.model_copy(update=update)
        self.settings = replace(base, costs=costs)
        self.timing = cfg["timing"]

    def scenario(self, mission_id: str, tasks: list[WarehouseTask], *, done: frozenset[str], seed: int,
                 unavailable: frozenset[str], wave: int) -> Scenario:
        specs = to_task_specs(tasks, self.cfg, done=done)
        sid = f"warehouse-{mission_id}"
        mission = MissionSpec(
            mission_id=mission_id, scenario_id=sid, tasks=specs, deadline_ms=self.cfg["samg"]["deadline_s"] * MS,
            generator_version="warehouse-v1", family="warehouse",
            generator_params={"orders": sorted({t.order_id for t in tasks if t.task_id not in done}), "wave": wave},
        )
        agents = tuple(to_agent_profile(r, resource_budget=self.cfg["samg"]["resource_budget"],
                                        available=r.robot_id not in unavailable) for r in self.robots)
        return Scenario(scenario_id=sid, seed=seed, mission=mission, agents=agents)


def _clone(policy: TopologyPolicy) -> TopologyPolicy:
    return type(policy).from_snapshot(policy.snapshot())  # type: ignore[attr-defined]


def _merge(*maps: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for m in maps:
        for k, v in m.items():
            out[k] += v
    return dict(out)


# --- one wave -------------------------------------------------------------------


@dataclass
class Wave:
    number: int
    mission_id: str
    mission_index: int
    t_offset: float
    task_ids: list[str]
    record: MissionRunRecord
    replay: WaveReplay | None
    injections_applied: list[dict[str, Any]]
    physical_passes: int
    delays_ms: dict[str, float]
    verified: dict[str, str]                 # task -> last witness-observed state
    failing_robots: frozenset[str]
    excluded_robots: frozenset[str]
    status: str = "committed"               # live sessions: "preview" until the clock passes end_s

    @property
    def end_s(self) -> float:
        ends = [self.t_offset]
        if self.record.trace:
            ends.append(self.t_offset + max(t.sim_time for t in self.record.trace.transitions) / MS)
        if self.replay:
            ends.append(self.replay.end_s)
        return max(ends)


def _resolve_injections(spec_inj: tuple[Injection, ...], plan: Any, wtasks: dict[str, WarehouseTask],
                        mission_index: int, chosen: TopologyName) -> tuple[set[str], set[str], dict[str, float],
                                                                             dict[str, str], AttackConfig | None,
                                                                             list[dict[str, Any]]]:
    forced: set[str] = set()
    failing: set[str] = set()
    breakdowns: dict[str, str] = {}
    delays: dict[str, float] = {}
    attack = None
    applied: list[dict[str, Any]] = []
    by_agent: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for a in plan.assignments:
        by_agent[a.agent_id].append((a.start, a.task_id))

    avoid_orders: set[str] = set()

    def resolve(robot: str | None, exclude: set[str]) -> str | None:
        """``auto:KIND`` = the robot SAMG assigned the earliest task of that kind (else the name as given),
        skipping robots already targeted and orders already hit by another injection."""
        if robot and robot.startswith("auto:"):
            kind = robot.split(":", 1)[1]
            for a in sorted(plan.assignments, key=lambda a: (a.start, a.task_id)):
                t = wtasks[a.task_id]
                if t.kind == kind and a.agent_id not in exclude and t.order_id not in avoid_orders:
                    return a.agent_id
            return None
        return robot

    used: set[str] = set()
    # malicious reports first, so an automatic robot failure can avoid the sabotaged order
    for inj in sorted(spec_inj, key=lambda i: i.kind != "malicious_report"):
        if inj.kind == "robot_failure":
            robot = resolve(inj.robot, used)
            inj = replace(inj, robot=robot or inj.robot)
            used.add(inj.robot or "")
            own = sorted(x for x in by_agent.get(inj.robot or "", []) if wtasks[x[1]].order_id not in avoid_orders)
            preferred = [t for _, t in own if wtasks[t].kind == "TRANSPORT"]
            target = (preferred or [t for _, t in own] or [None])[0]
            if target:
                breakdowns[inj.robot] = target  # type: ignore[index]
                failing.add(inj.robot)  # type: ignore[arg-type]
                applied.append({"kind": inj.kind, "robot": inj.robot, "task": target, "effective": True})
            else:
                applied.append({"kind": inj.kind, "robot": inj.robot, "effective": False,
                                "note": f"{inj.robot} has no task in this wave; failure not triggered"})
        elif inj.kind == "delayed_task":
            target = inj.task if inj.task in {a.task_id for a in plan.assignments} else next(
                (a.task_id for a in sorted(plan.assignments, key=lambda a: (a.start, a.task_id))
                 if wtasks[a.task_id].kind == "PACK"), None)
            if target:
                delays[target] = delays.get(target, 0.0) + inj.delay_s * MS
                applied.append({"kind": inj.kind, "task": target, "delay_s": inj.delay_s, "effective": True})
        elif inj.kind == "malicious_report":
            inj = replace(inj, robot=resolve(inj.robot, used) or inj.robot)
            used.add(inj.robot or "")
            preferred_topo = next(t for t in ARM_ORDER if t is not chosen)
            attack = AttackConfig(compromised_agent=inj.robot, preferred_topology=preferred_topo,
                                  schedule=frozenset({mission_index}), sabotage_schedule=frozenset({mission_index}))
            sab = attack.sabotaged_task(mission_index, plan)
            if sab:
                avoid_orders.add(wtasks[sab].order_id)
            applied.append({"kind": inj.kind, "robot": inj.robot, "effective": True,
                            "preferred_topology": preferred_topo.value,
                            "sabotaged_task": attack.sabotaged_task(mission_index, plan)})
        else:  # comm_failure / aisle_blockage / inventory_unavailable act through the environment
            applied.append({"kind": inj.kind, "effective": True, "detail": inj.describe()})
    return forced, failing, breakdowns, delays, attack, applied


@dataclass(frozen=True)
class WaveOverrides:
    """Time-anchored live injections inside one wave (times in ms relative to the wave start).

    * ``agent_down_at_ms``: engine ``agent_down_at_ms`` (robot failure at a given time);
    * ``forced``: forced task failures (the abandoned task of a malicious report);
    * ``delays_ms``: extra execution time per task (delayed task);
    * ``attack``: ``AttackConfig`` whose signed false claims accompany the abandon.
    """

    agent_down_at_ms: dict[str, float] = field(default_factory=dict)
    forced: frozenset[str] = frozenset()
    delays_ms: dict[str, float] = field(default_factory=dict)
    attack: AttackConfig | None = None


def run_wave(env: WarehouseEnv, world: World, wtasks: dict[str, WarehouseTask], task_ids: list[str], *,
             done: frozenset[str], number: int, mission_id: str, mission_index: int, seed: int,
             states: dict[str, RobotState], locks: AisleLocks, t_offset: float,
             injections: tuple[Injection, ...], excluded: frozenset[str],
             overrides: WaveOverrides | None = None) -> Wave:
    """Plan and execute one SAMG wave, then replay it physically. ``locks`` is mutated.

    ``overrides`` (live sessions) adds time-anchored injections on top of the spec-level ones.
    """
    down = dict(overrides.agent_down_at_ms) if overrides else {}
    tasks = [wtasks[t] for t in task_ids]
    scenario = env.scenario(mission_id, tasks, done=done, seed=seed, unavailable=excluded, wave=number)
    feasible = feasible_topologies(scenario, env.settings.costs, env.settings.allocation)
    ctx = extract_features(scenario)
    probe = _clone(world.policy).select(ctx.features, feasible[0], ctx.feature_schema_version)

    forced: set[str] = set()
    failing: set[str] = set()
    breakdowns: dict[str, str] = {}
    delays: dict[str, float] = {}
    attack = None
    applied: list[dict[str, Any]] = []
    phys: dict[str, float] = {}
    passes = 0
    if probe.topology is not None:
        graph, plan = feasible[2][probe.topology]
        forced, failing, breakdowns, delays, attack, applied = _resolve_injections(injections, plan, wtasks, mission_index,
                                                                       probe.topology)
        if overrides is not None:
            forced |= set(overrides.forced)
            delays = _merge(delays, overrides.delays_ms)
            attack = overrides.attack or attack
            failing |= set(down)
        dry_forced = set(forced)
        if attack is not None:
            sab = attack.sabotaged_task(mission_index, plan)
            if sab:
                dry_forced.add(sab)
        robots = {r.robot_id: r for r in env.robots}
        for passes in range(1, MAX_PHYSICAL_PASSES + 1):
            trace = simulate(scenario, graph, plan, seed, env.settings.costs, forced_failures=dry_forced,
                             task_delays_ms=_merge(delays, phys), agent_breakdowns=breakdowns,
                             agent_down_at_ms=down)
            rep = replay_wave(layout=env.layout, inventory=env.inventory, robots=robots, states=states,
                              tasks=wtasks, plan=plan, trace=trace, timing=env.timing, locks=copy.deepcopy(locks),
                              t_offset=t_offset, failing_robots=frozenset(failing))
            if not rep.overruns_ms or max(rep.overruns_ms.values()) <= OVERRUN_TOLERANCE_MS:
                break
            phys = _merge(phys, rep.overruns_ms)

    record = run_single_mission(scenario, world, env.settings, seed=seed, mission_index=mission_index, attack=attack,
                                forced_failures=forced, task_delays_ms=_merge(delays, phys),
                                agent_breakdowns=breakdowns, agent_down_at_ms=down, feasible=feasible)
    replay = None
    verified: dict[str, str] = {}
    if record.trace is not None:
        executed_failures = {(tr.agent_id, tr.task_id) for tr in record.trace.transitions
                             if tr.from_state is TaskState.EXECUTING and tr.to_state is TaskState.FAILED}
        failing = {r for r in failing if (r, breakdowns.get(r)) in executed_failures or r in down}
        for inj in applied:
            if inj["kind"] == "robot_failure" and inj.get("effective") and inj["robot"] not in failing:
                inj["effective"] = False
                inj["note"] = f"{inj['robot']}'s task {inj['task']} never started (upstream not complete); no robot failure"
    if record.plan is not None and record.trace is not None:
        if record.decision.topology is not probe.topology:
            raise RuntimeError("policy decision differs from its dry-run probe")
        replay = replay_wave(layout=env.layout, inventory=env.inventory, robots={r.robot_id: r for r in env.robots},
                             states=states, tasks=wtasks, plan=record.plan, trace=record.trace, timing=env.timing,
                             locks=locks, t_offset=t_offset, failing_robots=frozenset(failing))
        for rid, ms in down.items():
            _mark_down(replay, rid, t_offset + ms / MS, locks)
        for w in record.witness_events:
            verified[w.task_id] = w.to_state.value
    return Wave(number=number, mission_id=mission_id, mission_index=mission_index, t_offset=t_offset,
                task_ids=list(task_ids), record=record, replay=replay, injections_applied=applied,
                physical_passes=passes, delays_ms=_merge(delays, phys), verified=verified,
                failing_robots=frozenset(failing), excluded_robots=excluded)


def _mark_down(replay: WaveReplay, rid: str, t_down: float, locks: AisleLocks | None = None) -> None:
    """A robot that went down while idle (no task executing) is FAILED from ``t_down`` on, where it stands
    (possibly on its way back to the park), and becomes an obstacle for the traffic planner."""
    st = replay.states[rid]
    if st.failed:
        return
    t0 = max(t_down, st.free_at)
    cell = st.cell
    loc = locks.traffic.locate(rid, t0) if locks is not None else None
    if loc is not None:
        t0 = max(t0, loc[1].arrive) if loc[1].arrive > t0 and loc[1].arrive - t0 < 2.0 else t0
        cell = loc[1].cell
    track = replay.segments.setdefault(rid, [])
    _clip(track, t0)
    replay.segments[rid].append(
        Segment(rid, t0, INF, "failed", "FAILED", cell, battery0=st.battery, battery1=st.battery,
                odo0=st.odometer, odo1=st.odometer, note="robot failure while idle"))
    if locks is not None:
        locks.traffic.mark_failed(rid, t0, cell)
    replay.states[rid] = replace(st, cell=cell, free_at=INF, failed=True, failed_at=t0)


# --- full run ---------------------------------------------------------------------


@dataclass
class WarehouseRun:
    spec: RunSpec
    env: WarehouseEnv
    orders: list[Order]
    holds: list[OrderHold]
    tasks: dict[str, WarehouseTask]
    waves: list[Wave]
    initial_states: dict[str, RobotState]
    final_states: dict[str, RobotState]
    policy_kind: str
    experience: int
    policy_state_before: dict[str, Any]
    policy_state_after: dict[str, Any]
    extra: dict[str, Any] = field(default_factory=dict)


def initial_states(env: WarehouseEnv) -> dict[str, RobotState]:
    return {r.robot_id: RobotState(cell=r.home, battery=r.battery) for r in env.robots}


def make_world(env: WarehouseEnv, policy: str, *, experience: int, cfg: dict[str, Any]) -> World:
    alpha = float(cfg["learning"]["alpha"])
    if policy in ("adaptive", "ucb1"):
        kind = "P3" if policy == "adaptive" else "P2"
        if experience > 0:
            snap = json.loads(trained_snapshot(kind, experience, env.settings.allocation.use_cpsat, alpha))
            from samg.learning import LinUCBPolicy, UCB1Policy
            pol: TopologyPolicy = (LinUCBPolicy if kind == "P3" else UCB1Policy).from_snapshot(snap)
        else:
            pol = make_policy(kind, {"alpha": alpha} if kind == "P3" else {}, seed=0)
    else:
        pol = make_policy(policy)
    return World.create(pol, mode=PolicyMode.PROTECTED)


def execute(env: WarehouseEnv, world: World, orders: list[Order], *, seed: int, mission_prefix: str,
            index_base: int, injections: tuple[Injection, ...] = (), replan: bool = True, max_waves: int = 3,
            states: dict[str, RobotState] | None = None) -> tuple[list[Wave], list[OrderHold], dict[str, WarehouseTask],
                                                                  dict[str, RobotState]]:
    """Run an order book through SAMG wave by wave. Returns waves, holds, tasks, final robot states."""
    task_list, holds = generate_tasks(orders, env.inventory, env.layout, env.robots, env.cfg)
    wtasks = {t.task_id: t for t in task_list}
    states = dict(states or initial_states(env))
    locks = AisleLocks()
    waves: list[Wave] = []
    remaining = [t.task_id for t in task_list]
    done: set[str] = set()
    excluded: frozenset[str] = frozenset()
    t_offset = 0.0
    for number in range(1, max_waves + 1):
        if not remaining:
            break
        wave = run_wave(env, world, wtasks, remaining, done=frozenset(done), number=number,
                        mission_id=f"{mission_prefix}-{number}", mission_index=index_base + number - 1, seed=seed + number - 1,
                        states=states, locks=locks, t_offset=t_offset,
                        injections=injections if number == 1 else (), excluded=excluded)
        waves.append(wave)
        if wave.replay is None:
            break
        states = dict(wave.replay.states)
        done |= {t for t in remaining if wave.verified.get(t) == TaskState.VERIFIED_COMPLETE.value}
        remaining = [t for t in remaining if t not in done]
        excluded = excluded | wave.failing_robots
        t_offset = wave.end_s
        if not replan:
            break
    return waves, holds, wtasks, states


def run_warehouse(spec: RunSpec, cfg: dict[str, Any] | None = None) -> WarehouseRun:
    cfg = cfg or load_config()
    env = WarehouseEnv(cfg, spec.injections, use_cpsat=spec.use_cpsat)
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
                        experience=experience, policy_state_before=before, policy_state_after=world.policy.snapshot())


@lru_cache(maxsize=8)
def trained_snapshot(kind: str, experience: int, use_cpsat: bool, alpha: float) -> str:
    """Adaptive policy state after ``experience`` generated warehouse missions (clean, single wave).

    Training order books come from ``generate_orders`` with seeds disjoint from the demo and the
    comparison seeds. Every training mission runs the same pipeline (physical dry run, SAMG,
    witness, ACP, guarded update). Cached per process.
    """
    cfg = load_config()
    env = WarehouseEnv(cfg, (), use_cpsat=use_cpsat)
    pol = make_policy(kind, {"alpha": alpha} if kind == "P3" else {}, seed=0)
    world = World.create(pol, mode=PolicyMode.PROTECTED)
    skus = [s.sku for s in env.inventory.all() if s.stock > 0]
    base = int(cfg["learning"]["training_seed_base"])
    for i in range(experience):
        orders = generate_orders(base + i, skus)
        execute(env, world, orders, seed=base + i, mission_prefix=f"TRAIN{i:02d}", index_base=i, replan=False,
                max_waves=1)
    return json.dumps(pol.snapshot())


# --- state for the frontend ---------------------------------------------------------


def _claim_time(e: AgentEvent, mission_index: int, t_offset: float) -> float:
    base = SIM_BASE_TIME + timedelta(days=mission_index)
    return t_offset + (e.issued_at - base).total_seconds()


def _r(x: float | None, nd: int = 3) -> float | None:
    if x is None or (isinstance(x, float) and math.isinf(x)):
        return None
    return round(float(x), nd)


def build_state(run: WarehouseRun) -> dict[str, Any]:
    """The normalised ``WarehouseState`` timeline consumed by the dashboard (JSON-safe).

    Static parts (layout, stations, inventory) are sent once; dynamic parts are time-stamped
    so the browser interpolates between simulation ticks without recomputing anything.
    """
    cfg, env = run.env.cfg, run.env
    clock = cfg["start_clock"]
    events: list[dict[str, Any]] = []
    arrivals: dict[str, float] = run.extra.get("arrivals", {})
    hop_s = env.settings.costs.handoff_delay_ms_per_hop / MS

    def ev(t: float, level: str, title: str, detail: str = "", **ref: Any) -> None:
        events.append({"t": _r(t), "seq": len(events), "level": level, "title": title, "detail": detail,
                       **{k: v for k, v in ref.items() if v is not None}})

    for o in run.orders:
        ev(arrivals.get(o.order_id, 0.0), "info", f"Order {o.order_id} received",
           f"{o.priority} · due {s_to_clock(clock, o.deadline_s)} · {', '.join(o.items)}", order=o.order_id)
    for h in run.holds:
        ev(run.extra.get("hold_times", {}).get(h.order_id, arrivals.get(h.order_id, 0.0)), "warn",
           f"Order {h.order_id} on hold", f"{h.sku}: {h.reason.replace('_', ' ').lower()} "
           "(inventory check before mission generation)", order=h.order_id)

    task_states: dict[str, list[dict[str, Any]]] = defaultdict(list)
    task_assign: dict[str, list[dict[str, Any]]] = defaultdict(list)
    claims: list[dict[str, Any]] = []
    waves_json: list[dict[str, Any]] = []
    robot_segments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    signalled: set[tuple[str, tuple[int, int]]] = set()     # failure signals already announced
    congestion: list[dict[str, Any]] = []
    windows_abs: dict[str, tuple[float, float]] = {}
    witness_json: list[dict[str, Any]] = []
    seen_tasks: set[str] = set()

    for w in run.waves:
        rec, off = w.record, w.t_offset
        d = rec.decision
        n_orders = len({run.tasks[t].order_id for t in w.task_ids})
        replanned = [t for t in w.task_ids if t in seen_tasks]
        seen_tasks.update(w.task_ids)
        if not replanned:
            ev(off, "samg", f"Mission {w.mission_id} generated",
               f"{len(w.task_ids)} SAMG tasks from {n_orders} orders (PICK → TRANSPORT → PACK → DISPATCH)",
               wave=w.number)
        else:
            new = len(w.task_ids) - len(replanned)
            ev(off, "bad", "Replanning", f"{len(replanned)} tasks not witness-verified are re-planned as mission "
               f"{w.mission_id}" + (f" with {new} new tasks" if new else "")
               + (f"; excluded: {', '.join(sorted(w.excluded_robots))} (failed)" if w.excluded_robots else ""),
               wave=w.number)
            for tid in replanned:
                task_states[tid].append({"t": _r(off), "state": "REPLANNED", "wave": w.number})
        ctx = rec.context.as_dict()
        ev(off, "samg", "Context features extracted",
           " · ".join(f"{k}={v:.2f}" for k, v in ctx.items() if k != "intercept"), wave=w.number)
        offered = [t.value for t in d.eligible]
        inelig = [f"{t.value}: {', '.join(r.value for r in v.reasons)}" for t, v in rec.eligibility.items() if not v.eligible]
        if d.topology is None:
            ev(off, "bad", "No eligible topology", "; ".join(inelig) or ",".join(r.value for r in d.reason_codes),
               wave=w.number)
        else:
            how = ("seeded warm-up" if d.warmup else "argmax score") if d.bonuses else "fixed baseline"
            score = d.scores.get(d.topology)
            ev(off, "samg", f"{d.policy_kind} selected {d.topology.value}",
               f"{how}" + (f" · score {score:.3f} = mean {d.means[d.topology]:.3f} + bonus {d.bonuses[d.topology]:.3f}"
                           if d.bonuses and score is not None else "") + f" · offered {', '.join(offered)}"
               + (f" · not eligible: {'; '.join(inelig)}" if inelig else ""), wave=w.number)
        plan = rec.plan
        if plan is not None:
            ob = plan.objective
            ev(off, "samg", f"{plan.solver.value} allocation {plan.solver_status or ''}".strip(),
               f"{len(plan.assignments)} tasks assigned" + (" (greedy fallback)" if plan.fallback_used else "")
               + (f" · planned makespan {ob.makespan * 60:.0f}s · handoff cost {ob.handoff_cost:.1f}" if ob else ""),
               wave=w.number)
            for a in plan.assignments:
                prev = task_assign[a.task_id][-1]["agent"] if task_assign[a.task_id] else None
                task_assign[a.task_id].append({"wave": w.number, "agent": a.agent_id,
                                               "plan_start": _r(off + a.start / MS), "plan_end": _r(off + a.end / MS),
                                               "reassigned_from": prev if prev and prev != a.agent_id else None})
                if prev and prev != a.agent_id:
                    ev(off, "samg", f"{a.task_id} reassigned {prev} → {a.agent_id}", "CP-SAT re-allocation after replanning",
                       task=a.task_id, robot=a.agent_id, wave=w.number)
        for inj in w.injections_applied:
            if not inj.get("effective"):
                ev(off, "warn", f"Injection not triggered: {INJECTION_KINDS[inj['kind']]}", inj.get("note", ""), wave=w.number)
            elif inj["kind"] == "delayed_task":
                ev(off, "warn", f"Delay injected on {inj['task']}", f"+{inj['delay_s']:.0f}s added to SAMG execution",
                   task=inj["task"], wave=w.number)
            elif inj["kind"] in ("comm_failure", "aisle_blockage", "inventory_unavailable"):
                ev(off, "warn", f"Condition active: {INJECTION_KINDS[inj['kind']]}", inj.get("detail", ""), wave=w.number)

        trace = rec.trace
        done_end: dict[str, float] = {}
        if trace is not None:
            outcomes = {o.task_id: o for o in trace.outcomes}
            done_end = {o.task_id: off + o.end / MS for o in trace.outcomes if o.completed and o.end is not None}
            for tr in trace.transitions:
                t = off + tr.sim_time / MS
                task_states[tr.task_id].append({"t": _r(t), "state": tr.to_state.value, "from": tr.from_state.value,
                                                "wave": w.number, "agent": tr.agent_id})
                if tr.to_state is TaskState.EXECUTING:
                    ev(t, "info", f"{tr.agent_id} started {tr.task_id}", run.tasks[tr.task_id].label,
                       robot=tr.agent_id, task=tr.task_id, wave=w.number)
                elif tr.to_state is TaskState.FAILED and tr.from_state is TaskState.EXECUTING:
                    robot_failed = tr.agent_id in w.failing_robots
                    robot_failed = robot_failed and outcomes[tr.task_id].failure_reason == "AGENT_BREAKDOWN"
                    ev(t, "bad", f"{tr.agent_id} FAILED" if robot_failed else f"{tr.task_id} failed",
                       (f"robot breakdown during {tr.task_id} (fault injection); its later tasks are blocked"
                        if robot_failed
                        else f"{tr.agent_id} did not complete the task"), robot=tr.agent_id, task=tr.task_id,
                       wave=w.number)
                elif tr.to_state is TaskState.BLOCKED:
                    reason = outcomes[tr.task_id].failure_reason or ""
                    ev(t, "warn", f"{tr.task_id} blocked", reason.replace("_", " ").replace(":", ": ").lower(),
                       task=tr.task_id, wave=w.number)
            for o in trace.outcomes:
                if o.start is not None and o.end is not None:
                    windows_abs[o.task_id] = (off + o.start / MS, off + o.end / MS)
        for we in rec.witness_events:
            t = off + we.sim_time_ms / MS
            witness_json.append({"t": _r(t), "task": we.task_id, "from": we.from_state.value, "to": we.to_state.value,
                                 "witness": we.witness_id, "wave": w.number})
            if we.to_state is TaskState.VERIFIED_COMPLETE:
                task_states[we.task_id].append({"t": _r(t), "state": "VERIFIED_COMPLETE", "wave": w.number})
                ev(t, "ok", f"Witness verified {we.task_id}", "independent sensor evidence, signed by WITNESS-0",
                   task=we.task_id, wave=w.number)
            elif we.to_state is TaskState.FAILED and we.from_state is TaskState.BLOCKED:
                ev(t, "warn", f"Witness: {we.task_id} not performed", "blocked by an upstream failure; stays open "
                   "for replanning", task=we.task_id, wave=w.number)
            elif we.to_state is TaskState.FAILED:
                ev(t, "bad", f"Witness observed {we.task_id} FAILED", "signed by WITNESS-0", task=we.task_id,
                   wave=w.number)

        auth = {x.event_id: x for x in rec.auth_decisions}
        final = {x.event_id: x for x in rec.final_decisions}
        false_ids = set(rec.false_claim_event_ids)
        for e in rec.agent_events:
            a, f = auth.get(e.event_id), final.get(e.event_id)
            t = _claim_time(e, w.mission_index, off)
            evidence = f.status.value if f else None
            witnessed = w.verified.get(e.task_id) if e.task_id else None
            c = {"t": _r(t), "wave": w.number, "id": e.event_id, "agent": e.agent_id, "type": e.event_type.value,
                 "task": e.task_id, "auth": a.status.value if a else None,
                 "auth_reasons": [r.value for r in (a.reason_codes if a else ())],
                 "evidence": evidence, "reasons": [r.value for r in (f.reason_codes if f else ())],
                 "claimed_reward": _r(e.payload.get("claimed_reward")) if e.event_type is EventType.REWARD_CLAIM else None,
                 "witness_state": witnessed, "false_claim": e.event_id in false_ids}
            claims.append(c)
            if evidence == "DISPUTED":
                what = (f"reward {c['claimed_reward']}" if e.event_type is EventType.REWARD_CLAIM
                        else f"{e.task_id} complete")
                ev(t, "sec", f"SECURITY: {e.agent_id} claim rejected",
                   f"claims {what} · signature VALID · witness evidence contradicts → DISPUTED, quarantined",
                   robot=e.agent_id, task=e.task_id, wave=w.number, claim=e.event_id)
        ep = rec.episode
        t_end = w.end_s
        if ep is not None:
            ev(t_end, "ok" if ep.status.value == "ADMITTED" else "warn", f"ACP episode {ep.status.value}",
               ", ".join(r.value for r in ep.reason_codes), wave=w.number)
        if rec.acp_reward is not None:
            ev(t_end, "samg", f"Secure reward {rec.acp_reward.reward:.4f}",
               "recomputed by the ACP from witness-verified outcomes"
               + (f" · agent-claimed {rec.claimed_reward:.4f} not used" if rec.claimed_reward is not None
                  and abs(rec.claimed_reward - rec.acp_reward.reward) > 1e-4 else ""), wave=w.number)
        le = rec.learning_event
        if rec.policy_kind.startswith("P0"):
            ev(t_end, "info", "Fixed baseline: no learning", "the topology was set by the operator", wave=w.number)
        elif rec.learning_applied and le is not None:
            ev(t_end, "samg", f"Guarded update applied: {le.topology.value} ← {le.reward:.4f}",
               f"source {le.reward_source.value}", wave=w.number)
        elif le is not None or rec.learning_rejection is not None:
            ev(t_end, "warn", "Learning update blocked",
               (rec.learning_rejection.value if rec.learning_rejection else "-") + " · policy state unchanged",
               wave=w.number)

        if w.replay is not None:
            for rid, segs in w.replay.segments.items():
                robot_segments[rid].extend(s.to_json() | {"wave": w.number} for s in segs)
            for wt in w.replay.waits:
                congestion.append({"robot": wt.robot, "task": wt.task, "aisle": wt.aisle, "cell": list(wt.cell),
                                   "t0": _r(wt.t0), "t1": _r(wt.t1), "blockers": list(wt.blockers),
                                   "wave": w.number})
                ev(wt.t0, "warn", f"Congestion at {wt.aisle}",
                   f"{wt.robot} waits {wt.seconds:.1f}s" + (f" ({', '.join(wt.blockers)} in the way)" if wt.blockers
                                                             else ""),
                   robot=wt.robot, aisle=wt.aisle, wave=w.number)
            by_failure: dict[tuple, list] = defaultdict(list)
            for rr in w.replay.reroutes:
                by_failure[(rr.failed, rr.cell)].append(rr)
            for (failed_r, cell), rrs in sorted(by_failure.items(), key=lambda x: min(r.t_fail for r in x[1])):
                where = rrs[0].aisle or env.layout.zone_at(cell)
                if (failed_r, cell) not in signalled:
                    signalled.add((failed_r, cell))
                    ev(min(r.t_fail for r in rrs), "bad", f"Failure signal: {failed_r} blocks {where} {list(cell)}",
                       f"broadcast to the fleet; {', '.join(sorted({r.robot for r in rrs}))} take an alternative path",
                       robot=failed_r, aisle=rrs[0].aisle, wave=w.number)
                for rr in rrs:
                    if rr.replanned:
                        ev(rr.t, "warn", f"{rr.robot} rerouted around {failed_r}",
                           (f"{rr.task}: re-planned mid-route, " if rr.task else "returning to park: re-planned, ")
                           + f"{rr.delay_s:+.1f}s vs its original route", robot=rr.robot, task=rr.task, wave=w.number)
                    else:
                        ev(rr.t, "info", f"{rr.robot} routes around failed {failed_r}",
                           f"{rr.task or 'park'}: alternative path past {where} {list(cell)} "
                           f"({rr.delay_s:+.1f}s vs the blocked shortest route)", robot=rr.robot, task=rr.task,
                           wave=w.number)
            for ar in w.replay.arrivals:
                ev(ar.t, "move", f"{ar.robot} reached {ar.place}", ar.task, robot=ar.robot, task=ar.task, wave=w.number)

        g = rec.graph
        waves_json.append({
            "number": w.number, "mission_id": w.mission_id, "status": w.status, "t0": _r(off), "t1": _r(w.end_s),
            "tasks": w.task_ids, "excluded": sorted(w.excluded_robots), "failing": sorted(w.failing_robots),
            "physical_passes": w.physical_passes,
            "delays_s": {k: _r(v / MS) for k, v in sorted(w.delays_ms.items())},
            "injections": w.injections_applied,
            "policy": rec.policy_kind, "topology": d.topology.value if d.topology else None, "warmup": d.warmup,
            "context": [{"name": k, "value": _r(v)} for k, v in ctx.items()],
            "arms": [{"topology": arm.value, "offered": arm in d.eligible, "selected": arm is d.topology,
                      "mean": _r(d.means.get(arm)), "bonus": _r(d.bonuses.get(arm)), "score": _r(d.scores.get(arm)),
                      "reasons": [r.value for r in rec.eligibility[arm].reasons] if arm in rec.eligibility else []}
                     for arm in ARM_ORDER],
            "graph": None if g is None else {
                "topology": g.topology.value, "coordinators": list(g.coordinators),
                "cells": {k: list(v) for k, v in g.cells.items()}, "cell_coordinators": dict(g.cell_coordinators),
                "links": [list(x) for x in g.coordination_links()]},
            "allocation": None if plan is None else {
                "solver": plan.solver.value, "status": plan.solver_status, "fallback": plan.fallback_used,
                "objective": None if plan.objective is None else {
                    "makespan_s": _r(plan.objective.makespan * 60), "handoff_cost": _r(plan.objective.handoff_cost),
                    "weighted_total": _r(plan.objective.weighted_total)},
                "handoffs": [{"from_task": h.prerequisite_task, "to_task": h.dependent_task, "path": list(h.path),
                              "hops": h.hops, "cost": _r(h.cost),
                              "depart_s": _r(done_end.get(h.prerequisite_task)),
                              "arrive_s": _r(done_end[h.prerequisite_task] + h.hops * hop_s)
                              if h.prerequisite_task in done_end else None}
                             for h in plan.handoffs if h.hops > 0]},
            "episode": None if ep is None else {"status": ep.status.value, "reasons": [r.value for r in ep.reason_codes]},
            "reward": None if rec.acp_reward is None else {
                "value": _r(rec.acp_reward.reward, 4),
                "terms": {k: {"component": _r(rec.acp_reward.components[k], 4), "weight": rec.acp_reward.weights[k],
                              "contribution": _r(v, 4)} for k, v in rec.acp_reward.contributions.items()}},
            "ground_truth_reward": _r(rec.ground_truth_reward.reward, 4) if rec.ground_truth_reward else None,
            "claimed_reward": _r(rec.claimed_reward, 4),
            "metrics": None if rec.trace is None else {
                "makespan_s": _r(rec.trace.metrics.makespan / MS), "coordination_cost": _r(rec.trace.metrics.coordination_cost),
                "communication_failures": rec.trace.metrics.communication_failures,
                "completion": _r(rec.trace.metrics.weighted_completion, 4)},
            "learning": {"applied": rec.learning_applied,
                         "topology": le.topology.value if le else None, "reward": _r(le.reward, 4) if le and le.reward is not None else None,
                         "source": le.reward_source.value if le else None,
                         "rejection": rec.learning_rejection.value if rec.learning_rejection else None},
        })

    # orders: status derived only from task states (witness-verified dispatch = fulfilled)
    verified_at = {tid: next((s["t"] for s in sts if s["state"] == "VERIFIED_COMPLETE"), None)
                   for tid, sts in task_states.items()}
    orders_json = []
    hold_ids = {h.order_id for h in run.holds}
    for o in run.orders:
        tids = [t.task_id for t in run.tasks.values() if t.order_id == o.order_id]
        disp = verified_at.get(f"{o.order_id}-DISPATCH")
        oj = o.to_json(clock) | {"arrival_s": _r(arrivals.get(o.order_id, 0.0)), "tasks": tids, "hold": o.order_id in hold_ids,
                                 "hold_reason": next((f"{h.sku} {h.reason}" for h in run.holds if h.order_id == o.order_id), None),
                                 "dispatched_at": disp, "on_time": None if disp is None else disp <= o.deadline_s,
                                 "consolidation": next((t.consolidation for t in run.tasks.values() if t.order_id == o.order_id), None),
                                 "dock": next((t.dock for t in run.tasks.values() if t.order_id == o.order_id), None)}
        orders_json.append(oj)
        if disp is not None:
            ev(disp, "ok", f"Order {o.order_id} dispatched",
               f"witness-verified at {s_to_clock(clock, disp)} · {'on time' if disp <= o.deadline_s else 'LATE'}",
               order=o.order_id)

    tasks_json = []
    for tid, t in run.tasks.items():
        sts = sorted(task_states.get(tid, []), key=lambda s: s["t"])
        deps_end = [windows_abs[dp][1] for dp in t.dependencies if dp in windows_abs]
        latency = None
        if tid in windows_abs:
            wave0 = next((wv.t_offset for wv in run.waves if tid in wv.task_ids and wv.record.trace and
                          any(x.task_id == tid and x.to_state is TaskState.EXECUTING for x in wv.record.trace.transitions)), 0.0)
            release = max(deps_end + [wave0])
            latency = windows_abs[tid][0] - release
        tasks_json.append({
            "id": tid, "order": t.order_id, "kind": t.kind, "label": t.label, "sku": t.sku, "priority": t.priority,
            "capability": t.capability, "deps": list(t.dependencies), "estimate_s": _r(t.estimate_s),
            "states": sts, "assignments": task_assign.get(tid, []),
            "window": [_r(x) for x in windows_abs[tid]] if tid in windows_abs else None,
            "latency_s": _r(latency), "verified_at": verified_at.get(tid),
            "zone": (env.layout.zone_at(env.inventory[t.sku].pick_face) if t.sku else
                     {"TRANSPORT": "Consolidation → Packing", "PACK": "Packing", "DISPATCH": "Dispatch"}[t.kind]),
        })

    robots_json = []
    for r in env.robots:
        st0, st1 = run.initial_states[r.robot_id], run.final_states[r.robot_id]
        robots_json.append({
            "id": r.robot_id, "role": r.role, "label": r.label, "capabilities": list(r.capabilities),
            "coordinator": r.coordinator, "lead": r.lead, "physical": r.physical, "mobile": r.mobile,
            "home": list(r.home), "station": r.station, "speed": r.speed, "battery0": st0.battery,
            "segments": clip_overlaps(robot_segments.get(r.robot_id, [])),
            "failed_at": _r(st1.failed_at),
        })

    events.sort(key=lambda e: (e["t"], e["seq"]))   # same time: the order SAMG produced them
    end_s = max([w.end_s for w in run.waves] + [0.0])
    state = {
        "version": STATE_VERSION, "config_version": cfg["version"], "start_clock": clock,
        "spec": {"scenario": run.spec.scenario, "label": run.spec.label, "seed": run.spec.seed,
                 "policy": run.spec.policy, "policy_label": POLICY_KINDS[run.spec.policy],
                 "policy_kind": run.policy_kind, "experience": run.experience,
                 "injections": [i.describe() for i in run.spec.injections], "use_cpsat": run.spec.use_cpsat},
        "end_s": _r(end_s),
        "layout": env.layout.to_json(), "inventory": env.inventory.to_json(),
        "robots": robots_json, "orders": orders_json, "tasks": tasks_json, "waves": waves_json,
        "claims": sorted(claims, key=lambda c: c["t"]), "congestion": congestion, "events": events,
        "witness_events": sorted(witness_json, key=lambda x: x["t"]),
        "kpis": compute_kpis(run, orders_json, tasks_json, robots_json, congestion, claims, end_s),
    }
    return state


def compute_kpis(run: WarehouseRun, orders: list[dict[str, Any]], tasks: list[dict[str, Any]],
                 robots: list[dict[str, Any]], congestion: list[dict[str, Any]], claims: list[dict[str, Any]],
                 end_s: float) -> dict[str, Any]:
    """Final KPIs, every one derived from SAMG records or the physical replay."""
    done = [o for o in orders if o["dispatched_at"] is not None]
    mobile = [r for r in robots if r["mobile"]]
    busy = sum(min(s["t1"] if s["t1"] is not None else end_s, end_s) - s["t0"]
               for r in mobile for s in r["segments"]
               if s["kind"] in ("move", "work", "wait") and s.get("task"))   # returning to the park is not work
    travel = sum(s["o1"] - s["o0"] for r in robots for s in r["segments"])
    lat = [t["latency_s"] for t in tasks if t["latency_s"] is not None and t["verified_at"] is not None]
    rewards = [w.record.acp_reward.reward for w in run.waves if w.record.acp_reward is not None]
    failures = sum(1 for t in tasks for s in t["states"] if s["state"] == "FAILED" and s.get("from") == "EXECUTING")
    unverified = sum(1 for t in tasks if t["verified_at"] is None)
    return {
        "orders_total": len(orders), "orders_dispatched": len(done),
        "order_completion_rate": _r(len(done) / len(orders), 4) if orders else None,
        "on_time": sum(1 for o in done if o["on_time"]),
        "avg_fulfilment_s": _r(fmean(o["dispatched_at"] for o in done)) if done else None,
        "avg_task_latency_s": _r(fmean(lat)) if lat else None,
        "robot_utilization": _r(busy / (len(mobile) * end_s), 4) if mobile and end_s > 0 else None,
        "travel_m": _r(travel, 1),
        "congestion_s": _r(sum(c["t1"] - c["t0"] for c in congestion), 1), "congestion_events": len(congestion),
        "task_failures": failures, "unverified_tasks": unverified,
        "security_violations": sum(1 for c in claims if c["evidence"] == "DISPUTED"),
        "reward_last": _r(rewards[-1], 4) if rewards else None, "rewards": [_r(r, 4) for r in rewards],
        "makespan_s": _r(end_s),
        "topologies": [w.record.decision.topology.value if w.record.decision.topology else None for w in run.waves],
        "replans": max(len(run.waves) - 1, 0),
    }


# --- fixed-topology comparison ---------------------------------------------------------


COMPARE_POLICIES = ("P0-H", "P0-F", "P0-D", "adaptive")
COMPARE_METRICS = ("order_completion_rate", "avg_fulfilment_s", "robot_utilization", "congestion_s",
                   "coordination_cost", "reward_first_wave", "security_violations", "travel_m")


def compare_policies(cfg: dict[str, Any] | None = None, *, seeds: tuple[int, ...] | None = None,
                     use_cpsat: bool = True, injections: tuple[Injection, ...] = ()) -> dict[str, Any]:
    """Run the identical order book, layout and initial fleet under each policy for each seed.

    Adaptive starts every seed from the same trained snapshot (no learning carries across
    evaluation seeds). Reports per-policy mean and population std with n; no significance claim.
    """
    cfg = cfg or load_config()
    seeds = tuple(seeds or cfg["learning"]["comparison_seeds"])
    rows = []
    for pol in COMPARE_POLICIES:
        runs = []
        for seed in seeds:
            run = run_warehouse(RunSpec(seed=seed, policy=pol, injections=injections, use_cpsat=use_cpsat,
                                        scenario="comparison"), cfg)
            st = build_state(run)
            k = st["kpis"]
            first = run.waves[0].record if run.waves else None
            runs.append({
                "seed": seed, "topology": k["topologies"][0] if k["topologies"] else None,
                "feasible": bool(first and first.decision.topology is not None),
                "order_completion_rate": k["order_completion_rate"], "avg_fulfilment_s": k["avg_fulfilment_s"],
                "robot_utilization": k["robot_utilization"], "congestion_s": k["congestion_s"],
                "coordination_cost": sum(w.record.trace.metrics.coordination_cost for w in run.waves if w.record.trace),
                "reward_first_wave": first.acp_reward.reward if first and first.acp_reward else None,
                "security_violations": k["security_violations"], "travel_m": k["travel_m"],
            })
            if not runs[-1]["feasible"]:
                # no plan was executed: only "orders fulfilled" (0) is meaningful, the rest is not measured
                runs[-1].update({m: None for m in COMPARE_METRICS if m != "order_completion_rate"})
        summary = {}
        for m in COMPARE_METRICS:
            vals = [r[m] for r in runs if r[m] is not None]
            summary[m] = {"mean": _r(fmean(vals), 4) if vals else None,
                          "std": _r(pstdev(vals), 4) if len(vals) > 1 else (0.0 if vals else None), "n": len(vals)}
        rows.append({"policy": pol, "label": POLICY_KINDS[pol], "runs": runs, "summary": summary,
                     "topologies": dict(Counter(r["topology"] or "not eligible" for r in runs)),
                     "infeasible": sum(1 for r in runs if not r["feasible"])})
    return {"seeds": list(seeds), "policies": rows, "metrics": list(COMPARE_METRICS),
            "note": f"Same layout, order book, initial fleet and seeds {list(seeds)} for every policy; "
                    "means ± population std over seeds. Differences within the spread are not claimed."}
