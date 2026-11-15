"""Live warehouse session: a server-side simulation clock driving SAMG wave by wave.

    order source --arrivals--> tasks --(no wave running)--> run_wave on a scratch world = PREVIEW
        clock passes the wave end --> same inputs on the real world = COMMITTED (learner updates)
        operator / demo-script injections at time t --> re-run the running wave's preview

Every decision (topology, allocation, execution, witness, ACP verdicts, reward, learning) is
made by ``samg.twin.adapter.run_wave`` -> ``samg.orchestration.run_single_mission``. This module
only keeps time, feeds inputs and records what happened. All randomness is seeded: the wave
seed is ``spec.seed + wave - 1`` exactly as in ``run_warehouse``.

Time-anchored injections (inside the running wave, at the current ``t``):

* ``robot_failure``: engine ``agent_down_at_ms`` - the task the robot executes at ``t`` fails
  then, its later tasks are blocked; the robot is excluded from later waves.
* ``malicious_report``: the robot's task executing at ``t`` (else its next) is abandoned (forced
  failure) and ``AttackConfig`` makes it sign false completion and reward claims, which the
  witness contradicts and the ACP disputes.
* ``delayed_task``: extra execution seconds on one task.

Environment injections (``comm_failure``, ``aisle_blockage``, ``inventory_unavailable``) change
the warehouse for waves planned *after* ``t``.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from samg.domain import PolicyMode, TaskState, TopologyName
from samg.evaluation.attacks import AttackConfig
from samg.learning import ARM_ORDER
from samg.learning.fixed import FixedTopologyPolicy
from samg.orchestration import World
from samg.twin.adapter import (
    MS,
    Wave,
    WarehouseEnv,
    WarehouseRun,
    WaveOverrides,
    _clone,
    build_state,
    compare_policies,
    initial_states,
    make_world,
    run_wave,
)
from samg.twin.congestion import AisleLocks
from samg.twin.environment import INF, RobotState, task_windows
from samg.twin.layout import load_config
from samg.twin.orders import Order
from samg.twin.scenarios import INJECTION_KINDS, Injection, RunSpec, preset
from samg.twin.sources import OrderSource, source_for
from samg.twin.task_generator import OrderHold, WarehouseTask, generate_tasks

log = logging.getLogger(__name__)

WAVE_INJECTIONS = ("robot_failure", "malicious_report", "delayed_task")
ENV_INJECTIONS = ("comm_failure", "aisle_blockage", "inventory_unavailable")
RUNS_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "runs"
_RUN_ID = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_EPS = 1e-9
OPERATOR_KIND = "P0-OPERATOR"     # policy_kind of a wave whose topology the operator forced (P0* = no learning)


def _topology(value: str | None) -> TopologyName | None:
    if value in (None, "", "auto"):
        return None
    try:
        return TopologyName(str(value).upper())
    except ValueError:
        raise ValueError(f"unknown topology {value}; expected one of {[t.value for t in TopologyName]} or auto") from None


@dataclass
class _Running:
    """Inputs of the running wave (fixed at planning) plus its live injections and preview."""

    number: int
    task_ids: list[str]
    done: frozenset[str]
    states: dict[str, RobotState]
    locks: AisleLocks                      # committed locks before this wave (copied for previews)
    t_offset: float
    excluded: frozenset[str]
    env: WarehouseEnv
    down: dict[str, float] = field(default_factory=dict)
    forced: set[str] = field(default_factory=set)
    delays: dict[str, float] = field(default_factory=dict)
    attack: AttackConfig | None = None
    preview: Wave | None = None
    forced_topology: TopologyName | None = None     # operator override fixed for this wave

    def overrides(self) -> WaveOverrides:
        return WaveOverrides(agent_down_at_ms=dict(self.down), forced=frozenset(self.forced),
                             delays_ms=dict(self.delays), attack=self.attack)


def _same_trace(a: list[tuple], b: list[tuple], tol_ms: float = 5.0) -> bool:
    """Equal transitions, allowing millisecond rounding from the physical-delay feedback loop."""
    return len(a) == len(b) and all(x[:4] == y[:4] and abs(x[4] - y[4]) <= tol_ms for x, y in zip(a, b, strict=True))


def _transitions(wave: Wave, before_ms: float | None = None) -> list[tuple]:
    if wave.record.trace is None:
        return []
    return [(tr.task_id, tr.agent_id, tr.from_state.value, tr.to_state.value, tr.sim_time)
            for tr in wave.record.trace.transitions if before_ms is None or tr.sim_time < before_ms]


class LiveSession:
    """One live warehouse session (thread-safe; the API's clock loop calls ``advance``)."""

    def __init__(self, scenario: str = "judge_demo", policy: str | None = None, seed: int | None = None,
                 experience: int | None = None, use_cpsat: bool = True, cfg: dict[str, Any] | None = None,
                 script: list[dict[str, Any]] | None = None, topology: str | None = None) -> None:
        self.params = dict(scenario=scenario, policy=policy, seed=seed, experience=experience, use_cpsat=use_cpsat,
                           cfg=cfg, script=script, topology=topology)
        # operator override: every wave planned while set uses this topology instead of the policy's choice
        self.forced_topology: TopologyName | None = _topology(topology)
        self.forced_since: float | None = 0.0 if self.forced_topology else None
        self.cfg = cfg = cfg or load_config()
        if scenario not in cfg["scenarios"]:
            raise ValueError(f"unknown scenario {scenario}")
        sc = cfg["scenarios"][scenario]
        overrides: dict[str, Any] = {"use_cpsat": use_cpsat, "injections": ()}   # live: injections are timed
        if policy is not None:
            overrides["policy"] = policy
        if seed is not None:
            overrides["seed"] = int(seed)
        if experience is not None:
            overrides["experience"] = int(experience)
        self.spec: RunSpec = preset(cfg, scenario, **overrides)
        self.lock = threading.RLock()
        self.session_id = f"{scenario}-s{self.spec.seed}-{time.strftime('%H%M%S')}"
        live = cfg.get("live", {})
        self.rate = float(live.get("rate", 1.0))
        self.t, self.playing, self.speed, self.revision = 0.0, False, 1.0, 0
        self.complete = False

        self.env_injections: list[Injection] = []
        self.env = WarehouseEnv(cfg, (), use_cpsat=use_cpsat)
        learnable = self.spec.policy in ("adaptive", "ucb1")
        exp = self.spec.experience if self.spec.experience is not None else cfg["learning"]["experience"]
        self.experience = int(exp) if learnable else 0
        self.world = make_world(self.env, self.spec.policy, experience=self.experience, cfg=cfg)
        self.policy_before = self.world.policy.snapshot()
        skus = [s.sku for s in self.env.inventory.all() if s.stock > 0]
        self.source: OrderSource = source_for(cfg, scenario, skus)

        self.orders: list[Order] = []
        self.arrival: dict[str, float] = {}
        self.unplanned: list[str] = []
        self.holds: list[OrderHold] = []
        self.hold_times: dict[str, float] = {}
        self.tasks: dict[str, WarehouseTask] = {}
        self.done: set[str] = set()
        self.initial = initial_states(self.env)
        self.states = dict(self.initial)
        self.locks = AisleLocks()
        self.excluded: frozenset[str] = frozenset()
        self.idle_down: dict[str, float] = {}
        self.waves: list[Wave] = []
        self.current: _Running | None = None
        self._last_plan_key: tuple | None = None

        steps = sc.get("script", []) if script is None else script
        self.script = sorted(({**s, "fired": False} for s in steps), key=lambda s: float(s["at"]))
        self.injections: list[dict[str, Any]] = []
        self.notices: deque[dict[str, str]] = deque(maxlen=200)
        self._state_cache: tuple[int, dict[str, Any]] | None = None

        with self.lock:
            self._process(-1.0)

    # --- clock ---------------------------------------------------------------------

    def clock(self) -> dict[str, Any]:
        return {"t": round(self.t, 3), "playing": self.playing, "speed": self.speed, "revision": self.revision}

    def advance(self, dt: float) -> bool:
        """Move the clock forward ``dt`` simulated seconds, handling every event on the way.

        Returns whether anything structural changed (``revision`` bumped)."""
        with self.lock:
            rev = self.revision
            target = self.t + max(dt, 0.0)
            while True:
                nxt = self._next_event()
                if nxt is None or nxt > target:
                    self.t = target
                    break
                prev, self.t = self.t, max(nxt, self.t)
                self._process(prev)
            self._check_complete()
            return self.revision != rev

    def advance_real(self, dt_real: float) -> bool:
        """Clock-loop entry: ``dt_real`` wall seconds at the current speed and rate (no-op when paused)."""
        if not self.playing or self.complete:
            return False
        return self.advance(min(dt_real, 0.25) * self.speed * self.rate)

    def _next_event(self) -> float | None:
        times = []
        nxt = self.source.next_arrival(self.t)
        if nxt is not None:
            times.append(nxt)
        pending = [float(s["at"]) for s in self.script if not s["fired"]]
        if pending:
            times.append(max(min(pending), self.t))
        if self.current is not None and self.current.preview is not None:
            times.append(max(self.current.preview.end_s, self.t))
        return min(times) if times else None

    def _process(self, prev: float) -> None:
        """Handle everything due at ``self.t``: arrivals, wave commit, scripted injections, planning."""
        for a in self.source.arrivals(prev, self.t):
            self.orders.append(a.order)
            self.arrival[a.order.order_id] = a.at_s
            self.unplanned.append(a.order.order_id)
            self._touch()
        if self.current is not None and self.current.preview is not None and self.current.preview.end_s <= self.t + _EPS:
            self._commit()
        for step in self.script:
            if not step["fired"] and float(step["at"]) <= self.t + _EPS:
                step["fired"] = True
                args = {k: v for k, v in step.items() if k not in ("at", "fired", "kind")}
                self.inject(step["kind"], source="script", **args)
        self._plan()

    def _check_complete(self) -> None:
        idle = self.current is None and not self.unplanned
        if idle and self.source.next_arrival(self.t) is None and all(s["fired"] for s in self.script) \
                and not self.complete:
            self.complete, self.playing = True, False
            self._notice("ok", f"Session complete at t={self.t:.0f}s: no running wave, no pending orders")
            self._touch()

    def control(self, action: str, value: float | None = None) -> dict[str, Any]:
        """``play | pause | step | speed`` (``reset`` is handled by the owner: a new session)."""
        with self.lock:
            if action == "play":
                self.playing = not self.complete
            elif action == "pause":
                self.playing = False
            elif action == "step":
                self.advance(float(value) if value else 5.0)
            elif action == "speed":
                if not value or value <= 0:
                    raise ValueError("speed needs a positive value")
                self.speed = float(value)
            else:
                raise ValueError(f"unknown action {action}")
            return self.clock()

    # --- waves -----------------------------------------------------------------------

    def _plan(self) -> None:
        """Start a wave when none is running and there are arrived, unverified tasks."""
        if self.current is not None:
            return
        if self.unplanned:
            new = set(self.unplanned)
            tasks, holds = generate_tasks(self.orders, self.env.inventory, self.env.layout, self.env.robots, self.cfg)
            for task in tasks:
                if task.order_id in new:
                    self.tasks[task.task_id] = task
            for h in holds:
                if h.order_id in new:
                    self.holds.append(h)
                    self.hold_times[h.order_id] = self.t
            self.unplanned = []
            self._touch()
        remaining = [tid for tid in self.tasks if tid not in self.done]
        key = (frozenset(remaining), tuple(i.describe() for i in self.env_injections), self.excluded)
        if not remaining or key == self._last_plan_key:
            return
        self._last_plan_key = key
        self.current = _Running(number=len(self.waves) + 1, task_ids=remaining, done=frozenset(self.done),
                                states=dict(self.states), locks=copy.deepcopy(self.locks), t_offset=self.t,
                                excluded=self.excluded, env=self.env, forced_topology=self.forced_topology)
        self._preview()

    def _wave_args(self, cur: _Running) -> dict[str, Any]:
        return dict(done=cur.done, number=cur.number, mission_id=f"WH{self.spec.seed:03d}-{cur.number}",
                    mission_index=self.experience + cur.number - 1, seed=self.spec.seed + cur.number - 1,
                    states=cur.states, t_offset=cur.t_offset, injections=(), excluded=cur.excluded,
                    overrides=cur.overrides())

    def _preview(self) -> None:
        """Run the current wave on a scratch world (policy clone, in-memory store): no learning persists."""
        cur = self.current
        assert cur is not None
        cur.preview = run_wave(cur.env, self._world_for(cur, scratch=True), self.tasks, cur.task_ids,
                               locks=copy.deepcopy(cur.locks), **self._wave_args(cur))
        if cur.forced_topology is not None and cur.preview.record.decision.topology is None:
            # the forced topology has no feasible plan for this wave: say so and let the policy decide
            self._notice("warn", f"Wave {cur.number}: {cur.forced_topology.value} is not feasible for this wave "
                                 "(no valid graph/plan); SAMG's own choice is used")
            cur.forced_topology = None
            cur.preview = run_wave(cur.env, self._world_for(cur, scratch=True), self.tasks, cur.task_ids,
                                   locks=copy.deepcopy(cur.locks), **self._wave_args(cur))
        cur.preview.status = "preview"
        self._touch()

    def _world_for(self, cur: _Running, *, scratch: bool) -> World:
        """The world a wave runs in. An operator-forced wave uses a fixed policy in its own audit store, so the
        protected learner is never updated from a decision it did not make."""
        if cur.forced_topology is not None:
            return World.create(FixedTopologyPolicy(cur.forced_topology, kind=OPERATOR_KIND), mode=PolicyMode.PROTECTED)
        if scratch:
            return World.create(_clone(self.world.policy), mode=PolicyMode.PROTECTED)
        return self.world

    def _commit(self) -> None:
        """Re-run the finished wave on the real world (same inputs); the learner updates only here."""
        cur = self.current
        assert cur is not None and cur.preview is not None
        locks = copy.deepcopy(cur.locks)
        wave = run_wave(cur.env, self._world_for(cur, scratch=False), self.tasks, cur.task_ids, locks=locks,
                        **self._wave_args(cur))
        if _transitions(wave) != _transitions(cur.preview) or \
                wave.record.decision.topology is not cur.preview.record.decision.topology:
            log.warning("wave %s commit differs from its preview", cur.number)
            self._notice("warn", f"Wave {cur.number}: committed trace differs from preview (logged)")
        self.waves.append(wave)
        self.locks = locks
        if wave.replay is not None:
            self.states = dict(wave.replay.states)
        for rid, t_down in self.idle_down.items():
            self.states[rid] = self._down_state(self.states[rid], t_down)
        self.done |= {t for t in cur.task_ids if wave.verified.get(t) == TaskState.VERIFIED_COMPLETE.value}
        self.excluded = self.excluded | wave.failing_robots
        self.current = None
        self._touch()

    @staticmethod
    def _down_state(st: RobotState, t: float) -> RobotState:
        return st if st.failed else replace(st, free_at=INF, failed=True, failed_at=t)

    # --- injections --------------------------------------------------------------------

    def set_topology(self, topology: str | None) -> dict[str, Any]:
        """Operator topology override (``None``/``"auto"`` hands the choice back to the policy).

        The running wave is re-planned with it when none of its tasks has started yet (the past is unchanged);
        otherwise it applies from the next wave. Returns ``{topology, applies_from_wave, effect}``."""
        with self.lock:
            topo = _topology(topology)
            self.forced_topology = topo
            self.forced_since = self.t if topo else None
            cur = self.current
            label = topo.value if topo else "SAMG's own choice"
            if cur is not None and cur.preview is not None and cur.forced_topology is not topo:
                started = cur.preview.record.trace is not None and any(
                    s <= self.t + _EPS for s, _e, _f, _r in self._windows(cur).values())
                if not started:
                    cur.forced_topology = topo
                    self._preview()
                    applied = cur.preview.record.decision.topology  # type: ignore[union-attr]
                    effect = f"wave {cur.number} re-planned with {applied.value if applied else 'no topology'}"
                    nxt = cur.number
                else:
                    effect = f"wave {cur.number} is already executing; {label} applies from wave {cur.number + 1}"
                    nxt = cur.number + 1
            else:
                nxt = (cur.number + 1) if cur is not None else len(self.waves) + 1
                effect = f"{label} applies from wave {nxt}"
            msg = f"Operator topology override: {topo.value}" if topo else "Topology override cleared"
            self._notice("warn" if topo else "ok", f"{msg} · {effect}")
            self._touch()
            return {"topology": topo.value if topo else None, "applies_from_wave": nxt, "effect": effect,
                    "at": round(self.t, 3)}

    def inject(self, kind: str, *, robot: str | None = None, aisle: str | None = None, sku: str | None = None,
               task: str | None = None, delay_s: float | None = None, source: str = "operator") -> dict[str, Any]:
        """Apply an injection at the current ``t``. Returns ``{accepted, at, effect, kind, target, wave}``."""
        with self.lock:
            if kind not in INJECTION_KINDS:
                raise ValueError(f"unknown injection {kind}")
            cur = self.current
            wave = cur.number if cur else None
            try:
                if kind in ENV_INJECTIONS:
                    target, effect = self._inject_env(Injection(kind=kind, aisle=aisle, sku=sku))
                    wave = None
                elif kind == "robot_failure" and cur is None:
                    target, effect = self._inject_idle_failure(robot)
                elif cur is None or cur.preview is None or cur.preview.record.plan is None:
                    raise _Reject("no wave is running")
                else:
                    before = cur.preview
                    target, effect = {"robot_failure": self._inject_failure, "malicious_report": self._inject_malicious,
                                      "delayed_task": self._inject_delay}[kind](cur, robot=robot, task=task,
                                                                                 delay_s=delay_s)
                    cut = (self.t - cur.t_offset) * MS
                    if cur.preview is not before and not _same_trace(_transitions(cur.preview, cut),
                                                                    _transitions(before, cut)):
                        log.warning("injection %s changed the trace before t=%.1f", kind, self.t)
                        self._notice("warn", f"{INJECTION_KINDS[kind]}: re-run changed events before t (logged)")
            except _Reject as r:
                res = {"accepted": False, "at": round(self.t, 3), "kind": kind, "target": robot or aisle or sku or task,
                       "effect": str(r), "wave": wave, "source": source}
                self._notice("warn", f"{INJECTION_KINDS[kind]} rejected: {r}")
                return res
            res = {"accepted": True, "at": round(self.t, 3), "kind": kind, "target": target, "effect": effect,
                   "wave": wave, "source": source}
            self.injections.append({"t": res["at"], **{k: v for k, v in res.items() if k not in ("at", "accepted")}})
            self._notice("warn", f"{INJECTION_KINDS[kind]}: {effect}")
            self._touch()
            if cur is None and kind in ENV_INJECTIONS + ("robot_failure",):
                self._plan()
            return res

    def _windows(self, cur: _Running) -> dict[str, tuple[float, float, bool, str]]:
        """Executed tasks of the preview: task -> (start_s, end_s absolute, failed, robot)."""
        rec = cur.preview.record  # type: ignore[union-attr]
        agent = {a.task_id: a.agent_id for a in rec.plan.assignments}  # type: ignore[union-attr]
        return {tid: (s + cur.t_offset, e + cur.t_offset, f, agent[tid])
                for tid, (s, e, f) in task_windows(rec.trace).items()}  # type: ignore[arg-type]

    def _task_for(self, cur: _Running, *, robot: str | None = None, kind: str | None = None,
                  avoid: set[str] | None = None) -> tuple[str, str] | None:
        """(task, robot) executing at ``t`` matching robot/kind, else the next one to start."""
        cands = [(s, tid, r) for tid, (s, e, f, r) in self._windows(cur).items()
                 if e > self.t + _EPS and not f and (robot is None or r == robot) and r not in (avoid or set())
                 and (kind is None or self.tasks[tid].kind == kind)]
        running = sorted(c for c in cands if c[0] <= self.t)
        upcoming = sorted(c for c in cands if c[0] > self.t)
        pick = (running or upcoming or [None])[0]
        return (pick[1], pick[2]) if pick else None

    def _cell_at(self, cur: _Running, rid: str, t: float) -> tuple[int, int] | None:
        """Where the running wave's preview puts ``rid`` at ``t`` (its physical replay)."""
        rep = cur.preview.replay if cur.preview else None
        if rep is None:
            return None
        for sg in rep.segments.get(rid, []):
            if sg.t0 <= t < sg.t1:
                if sg.kind == "move" and sg.path:
                    n = len(sg.path) - 1
                    i = min(n, int((t - sg.t0) / max(sg.t1 - sg.t0, 1e-9) * n + 0.5))
                    return sg.path[i]
                return sg.cell
        return None

    def _robot_in_aisle(self, cur: _Running) -> str:
        """auto:AISLE — a robot executing a task inside a narrow pick aisle right now."""
        aisle_of = self.env.layout.aisle_of
        avoid = set(self.excluded) | set(cur.down) | ({cur.attack.compromised_agent} if cur.attack else set())
        for tid, (s0, e0, failed, rid) in sorted(self._windows(cur).items(), key=lambda x: (x[1][0], x[0])):
            if rid in avoid or failed or not (s0 <= self.t < e0):
                continue
            cell = self._cell_at(cur, rid, self.t)
            if cell is not None and tuple(cell) in aisle_of:
                return rid
        raise _Reject("no robot is inside a pick aisle right now")

    def _robot(self, spec: str | None, kind: str | None = None) -> str:
        if not spec:
            raise _Reject("needs a robot (id or auto:KIND)")
        if spec == "auto:AISLE":
            if self.current is None or self.current.preview is None:
                raise _Reject("no wave is running")
            return self._robot_in_aisle(self.current)
        if spec.startswith("auto:"):
            cur = self.current
            hit = self._task_for(cur, kind=spec.split(":", 1)[1], avoid=set(self.excluded) | set(cur.down)
                                 | ({cur.attack.compromised_agent} if cur.attack else set())) if cur else None
            if hit is None:
                raise _Reject(f"no robot is executing or about to start a {spec[5:]} task")
            return hit[1]
        if spec not in self.env.robot or not self.env.robot[spec].physical:
            raise _Reject(f"unknown robot {spec}")
        return spec

    def _inject_failure(self, cur: _Running, *, robot: str | None, **_: Any) -> tuple[str, str]:
        rid = self._robot(robot)
        if rid in self.excluded or rid in cur.down or rid in self.idle_down:
            raise _Reject(f"{rid} is already down")
        running = self._task_for(cur, robot=rid)
        cur.down[rid] = (self.t - cur.t_offset) * MS
        self._preview()
        if running and self._windows(cur).get(running[0], (0, 0, False))[2]:
            return rid, f"{rid} down at t={self.t:.0f}s: {running[0]} fails, its later tasks are blocked; " \
                        "unverified tasks are replanned without it at the wave end"
        return rid, f"{rid} down at t={self.t:.0f}s while idle; excluded from later waves"

    def _inject_idle_failure(self, robot: str | None) -> tuple[str, str]:
        """``robot_failure`` with no running wave: down from ``t``, excluded from later waves."""
        rid = self._robot(robot)
        if rid in self.excluded or rid in self.idle_down:
            raise _Reject(f"{rid} is already down")
        self.idle_down[rid] = self.t
        self.states[rid] = self._down_state(self.states[rid], self.t)
        self.excluded = self.excluded | {rid}
        return rid, f"{rid} down at t={self.t:.0f}s while idle; excluded from later waves"

    def _inject_malicious(self, cur: _Running, *, robot: str | None, **_: Any) -> tuple[str, str]:
        if cur.attack is not None:
            raise _Reject(f"{cur.attack.compromised_agent} is already compromised in this wave")
        rid = self._robot(robot)
        hit = self._task_for(cur, robot=rid)
        if hit is None:
            raise _Reject(f"{rid} has no running or upcoming task in this wave")
        chosen = cur.preview.record.decision.topology  # type: ignore[union-attr]
        cur.forced.add(hit[0])
        cur.attack = AttackConfig(compromised_agent=rid, preferred_topology=next(a for a in ARM_ORDER if a is not chosen),
                                  schedule=frozenset({self.experience + cur.number - 1}))
        self._preview()
        return rid, f"{rid} compromised: abandons {hit[0]} and signs false completion + reward claims " \
                    f"(pushing {cur.attack.preferred_topology.value}); witness and ACP verify at the wave end"

    def _inject_delay(self, cur: _Running, *, task: str | None, delay_s: float | None, **_: Any) -> tuple[str, str]:
        delay = float(delay_s if delay_s is not None else 60.0)
        if task and task != "auto":
            w = self._windows(cur).get(task)
            if task not in cur.task_ids or (w and w[1] <= self.t + _EPS) or (w is None and task in cur.done):
                raise _Reject(f"{task} is not pending or running in this wave")
            target = task
        else:
            hit = self._task_for(cur, kind="PACK") or self._task_for(cur)
            if hit is None:
                raise _Reject("no running or upcoming task")
            target = hit[0]
        cur.delays[target] = cur.delays.get(target, 0.0) + delay * MS
        self._preview()
        return target, f"{target} +{delay:.0f}s execution time"

    def _inject_env(self, inj: Injection) -> tuple[str, str]:
        if inj.kind == "aisle_blockage" and inj.aisle not in {a.aisle_id for a in self.env.layout.aisles}:
            raise _Reject(f"unknown aisle {inj.aisle}")
        if inj.kind == "inventory_unavailable" and inj.sku not in self.env.inventory:
            raise _Reject(f"unknown SKU {inj.sku}")
        if any(i == inj for i in self.env_injections):
            raise _Reject("already active")
        self.env_injections.append(inj)
        self.env = WarehouseEnv(self.cfg, tuple(self.env_injections), use_cpsat=self.spec.use_cpsat)
        target = inj.aisle or inj.sku or "network"
        return target, f"{inj.describe().split(': ', 1)[1]} · applies to waves planned after t={self.t:.0f}s"

    # --- state ---------------------------------------------------------------------------

    def _touch(self) -> None:
        self.revision += 1

    def _notice(self, level: str, text: str) -> None:
        self.notices.append({"level": level, "text": text})

    def drain_notices(self) -> list[dict[str, str]]:
        with self.lock:
            out = list(self.notices)
            self.notices.clear()
            return out

    def state(self) -> dict[str, Any]:
        """The §4 state contract for everything planned so far (committed waves + running preview) + ``live``."""
        with self.lock:
            if self._state_cache and self._state_cache[0] == self.revision:
                st = self._state_cache[1]
            else:
                st = self._build()
                self._state_cache = (self.revision, st)
            st["live"].update(t=round(self.t, 3), playing=self.playing, speed=self.speed)
            return st

    def _build(self) -> dict[str, Any]:
        cur = self.current
        waves = self.waves + ([cur.preview] if cur and cur.preview else [])
        final = dict(cur.preview.replay.states) if cur and cur.preview and cur.preview.replay else dict(self.states)
        for rid, t_down in self.idle_down.items():
            final[rid] = self._down_state(final[rid], t_down)
        run = WarehouseRun(spec=self.spec, env=self.env, orders=list(self.orders), holds=list(self.holds),
                           tasks=self.tasks, waves=waves, initial_states=self.initial, final_states=final,
                           policy_kind=self.world.policy.kind, experience=self.experience,
                           policy_state_before=self.policy_before, policy_state_after=self.world.policy.snapshot(),
                           extra={"arrivals": self.arrival, "hold_times": self.hold_times})
        st = build_state(run)
        for r in st["robots"]:
            if r["id"] in self.idle_down and not any(s["kind"] == "failed" for s in r["segments"]):
                t0 = self.idle_down[r["id"]]
                last = r["segments"][-1] if r["segments"] else None
                sx = self.states[r["id"]]
                r["segments"].append({"t0": round(t0, 3), "t1": None, "kind": "failed", "status": "FAILED",
                                      "cell": list(sx.cell), "b0": round(sx.battery, 2), "b1": round(sx.battery, 2),
                                      "o0": round(sx.odometer, 2), "o1": round(sx.odometer, 2),
                                      "note": "robot failure while idle", **({"wave": last["wave"]} if last else {})})
        st["spec"]["order_source"] = self.source.kind
        st["live"] = {
            "session_id": self.session_id, "mode": "live", "revision": self.revision, "t": round(self.t, 3),
            "playing": self.playing, "speed": self.speed, "rate": self.rate, "complete": self.complete,
            "script": [dict(s) for s in self.script], "injections": list(self.injections),
            "pending_orders": [o for o in self.unplanned],
            "planning": "running" if cur else "idle",
            "forced_topology": self.forced_topology.value if self.forced_topology else None,
            "forced_since": None if self.forced_since is None else round(self.forced_since, 3),
        }
        return st


class _Reject(Exception):
    """An injection that cannot apply now (returned as ``accepted: false``, never raised to the API)."""


# --- replay store and comparison ---------------------------------------------------------


def save_run(session: LiveSession, name: str | None = None, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    """Store the session's current state (+ spec and script) as ``<runs_dir>/<id>.json``."""
    state = session.state()
    run_id = re.sub(r"[^A-Za-z0-9_.-]", "-", name or f"{session.session_id}-t{int(session.t)}")[:80]
    meta = {"id": run_id, "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "scenario": session.spec.scenario,
            "policy": session.spec.policy, "seed": session.spec.seed, "t": round(session.t, 3),
            "end_s": state["end_s"], "waves": len(state["waves"]), "complete": session.complete}
    doc = {"meta": meta, "spec": state["spec"], "script": state["live"]["script"], "state": state}
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{run_id}.json").write_text(json.dumps(doc))
    return meta


def list_runs(runs_dir: Path = RUNS_DIR) -> list[dict[str, Any]]:
    """Metadata of every stored run, newest first."""
    if not runs_dir.exists():
        return []
    metas = []
    for p in runs_dir.glob("*.json"):
        try:
            metas.append(json.loads(p.read_text())["meta"])
        except (ValueError, KeyError):
            log.warning("skipping unreadable run file %s", p)
    return sorted(metas, key=lambda m: m["saved_at"], reverse=True)


def load_run(run_id: str, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    """A stored run; its state is marked ``live.mode = "replay"`` and every wave ``committed``."""
    if not _RUN_ID.match(run_id):
        raise KeyError(run_id)
    path = runs_dir / f"{run_id}.json"
    if not path.exists():
        raise KeyError(run_id)
    doc = json.loads(path.read_text())
    doc["state"]["live"]["mode"] = "replay"
    for w in doc["state"]["waves"]:
        w["status"] = "committed"
    return doc


_COMPARE: dict[tuple, dict[str, Any]] = {}
_COMPARE_LOCK = threading.Lock()


def compare(seeds: tuple[int, ...] | None = None, use_cpsat: bool = True) -> dict[str, Any]:
    """``compare_policies`` cached per (seeds, use_cpsat) for the process."""
    key = (tuple(seeds) if seeds else None, use_cpsat)
    with _COMPARE_LOCK:
        if key not in _COMPARE:
            _COMPARE[key] = compare_policies(seeds=key[0], use_cpsat=use_cpsat)
        return _COMPARE[key]
