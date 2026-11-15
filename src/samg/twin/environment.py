"""Physical replay: SAMG's allocation + execution trace -> robot motion on the warehouse floor.

SAMG decides *who* does each task and *when* it starts and ends (``AllocationPlan`` and
``ExecutionTrace``). This module turns each executed task into physical activity for its
robot: a collision-free route from the robot's actual position (``samg.twin.traffic``: space-time
reservations, so no two robots ever share a cell and a narrow aisle holds one moving robot at a time),
service at the pick face / station, waits where another robot is in the way, and a return to the
robot's park cell when idle. A robot that fails blocks its cell; robots whose route crosses it are
re-planned on an alternative path from that moment (``WaveReplay.reroutes``).

Timing contract (per executed task, times in simulated seconds):

* the robot starts at SAMG's start time from wherever it actually is;
* if the physical activity finishes before SAMG's end time, the robot keeps servicing
  until the end (SAMG's duration includes jitter);
* if it finishes later, the excess is an *overrun* (longer real travel than the estimate,
  or aisle-congestion waits). ``samg.twin.adapter`` feeds overruns back into SAMG
  execution as per-task delays and re-runs, so in the final run travel, congestion and
  SAMG timing agree;
* a task that SAMG reports ``FAILED`` stops at SAMG's failure time. A robot under a
  robot-failure injection is ``FAILED`` from then on; otherwise it abandoned the task.

Robot movement is therefore never invented: every position comes from a planned route
traversed at the robot's configured speed within SAMG's execution window.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any

from samg.domain import AllocationPlan, ExecutionTrace, TaskState
from samg.twin.agents import RobotSpec
from samg.twin.congestion import AisleLocks
from samg.twin.inventory import Inventory
from samg.twin.layout import Cell, Layout
from samg.twin.path_planning import route
from samg.twin.task_generator import WarehouseTask
from samg.twin.traffic import Leg, Reroute, Step, Traffic

MS = 1000.0
INF = float("inf")
_EPS = 1e-6
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RobotState:
    cell: Cell
    battery: float
    odometer: float = 0.0
    free_at: float = 0.0
    failed: bool = False
    failed_at: float | None = None


@dataclass
class Segment:
    robot: str
    t0: float
    t1: float
    kind: str                     # move | wait | work | idle | failed
    status: str                   # robot status shown in the UI
    cell: Cell                    # position at t0 (end position for work/wait/idle)
    task: str | None = None
    path: list[Cell] | None = None
    battery0: float = 100.0
    battery1: float = 100.0
    odo0: float = 0.0
    odo1: float = 0.0
    aisle: str | None = None
    blockers: tuple[str, ...] = ()
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"t0": round(self.t0, 3), "t1": None if self.t1 == INF else round(self.t1, 3),
                             "kind": self.kind, "status": self.status, "cell": list(self.cell),
                             "b0": round(self.battery0, 2), "b1": round(self.battery1, 2),
                             "o0": round(self.odo0, 2), "o1": round(self.odo1, 2)}
        if self.task:
            d["task"] = self.task
        if self.path:
            d["path"] = [list(c) for c in self.path]
        if self.aisle:
            d["aisle"] = self.aisle
        if self.blockers:
            d["blockers"] = list(self.blockers)
        if self.note:
            d["note"] = self.note
        return d


@dataclass(frozen=True)
class Wait:
    robot: str
    task: str
    aisle: str
    cell: Cell
    t0: float
    t1: float
    blockers: tuple[str, ...]

    @property
    def seconds(self) -> float:
        return self.t1 - self.t0


@dataclass(frozen=True)
class Arrival:
    t: float
    robot: str
    task: str
    place: str


@dataclass
class WaveReplay:
    segments: dict[str, list[Segment]] = field(default_factory=dict)
    waits: list[Wait] = field(default_factory=list)
    arrivals: list[Arrival] = field(default_factory=list)
    overruns_ms: dict[str, float] = field(default_factory=dict)
    physical: dict[str, tuple[float, float]] = field(default_factory=dict)   # task -> (start, finish) s
    states: dict[str, RobotState] = field(default_factory=dict)
    end_s: float = 0.0
    reroutes: list[Reroute] = field(default_factory=list)


def task_windows(trace: ExecutionTrace) -> dict[str, tuple[float, float, bool]]:
    """Executed tasks -> (start_s, end_s, failed) from SAMG transitions."""
    start: dict[str, float] = {}
    out: dict[str, tuple[float, float, bool]] = {}
    for tr in trace.transitions:
        if tr.to_state is TaskState.EXECUTING:
            start[tr.task_id] = tr.sim_time / MS
        elif tr.from_state is TaskState.EXECUTING and tr.to_state in (TaskState.REPORTED_COMPLETE, TaskState.FAILED):
            out[tr.task_id] = (start[tr.task_id], tr.sim_time / MS, tr.to_state is TaskState.FAILED)
    return out


def _legs(task: WarehouseTask, layout: Layout, inventory: Inventory, pack_station: str,
          timing: dict[str, Any]) -> list[tuple[Cell, str, float, str, str]]:
    """(target cell, move status, service s, service status, place label) per leg."""
    drop = layout.consolidation_point(task.consolidation)
    station = layout.station(pack_station)
    dock = layout.station(task.dock)
    if task.kind == "PICK":
        sku = inventory[task.sku]  # type: ignore[index]
        return [(sku.pick_face, "MOVING", timing["pick_s"], "PICKING", f"{sku.aisle} · Rack {sku.rack} ({task.sku})"),
                (drop, "TRANSPORTING", timing["drop_s"], "TRANSPORTING", f"consolidation {task.consolidation}")]
    if task.kind == "TRANSPORT":
        return [(drop, "MOVING", timing["transport_load_s"], "TRANSPORTING", f"consolidation {task.consolidation}"),
                (station.access, "TRANSPORTING", timing["transport_unload_s"], "TRANSPORTING", station.label)]
    if task.kind == "DISPATCH":
        return [(station.outbound or station.access, "MOVING", timing["dispatch_handover_s"], "TRANSPORTING",
                 f"{station.label} outbound"),
                (dock.access, "TRANSPORTING", timing["dispatch_load_s"], "TRANSPORTING", dock.label)]
    raise ValueError(f"no legs for {task.kind}")


def _clip(track: list[Segment], cut: float) -> None:
    """Drop the part of a robot's segment list at or after ``cut`` (a re-plan starts there)."""
    while track and track[-1].t0 >= cut - _EPS:
        track.pop()
    if track and track[-1].t1 > cut:
        sg = track[-1]
        if sg.kind == "move" and sg.path and sg.t1 != INF:
            per = (sg.t1 - sg.t0) / max(len(sg.path) - 1, 1)
            n = max(1, min(len(sg.path) - 1, round((cut - sg.t0) / per)))
            frac = n / max(len(sg.path) - 1, 1)
            sg.battery1 = sg.battery0 + (sg.battery1 - sg.battery0) * frac
            sg.odo1 = sg.odo0 + (sg.odo1 - sg.odo0) * frac
            sg.path = sg.path[: n + 1]
        sg.t1 = cut


def clip_overlaps(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """JSON segments of one robot across waves: a later plan replaces whatever an earlier one had booked."""
    out: list[dict[str, Any]] = []
    for sg in sorted(segments, key=lambda x: x["t0"]):
        while out and out[-1]["t0"] >= sg["t0"] - _EPS and out[-1]["kind"] in ("idle", "move", "wait") \
                and not out[-1].get("task"):
            out.pop()
        if out and (out[-1]["t1"] is None or out[-1]["t1"] > sg["t0"] + _EPS):
            prev = dict(out[-1])
            if prev["kind"] == "move" and prev.get("path") and prev["t1"] is not None:
                per = (prev["t1"] - prev["t0"]) / max(len(prev["path"]) - 1, 1)
                n = max(1, min(len(prev["path"]) - 1, round((sg["t0"] - prev["t0"]) / per)))
                prev["path"] = prev["path"][: n + 1]
            prev["t1"] = round(sg["t0"], 3)
            out[-1] = prev
        out.append(sg)
    return out


def replay_wave(
    *,
    layout: Layout,
    inventory: Inventory,
    robots: dict[str, RobotSpec],
    states: dict[str, RobotState],
    tasks: dict[str, WarehouseTask],
    plan: AllocationPlan,
    trace: ExecutionTrace,
    timing: dict[str, Any],
    locks: AisleLocks,
    t_offset: float = 0.0,
    failing_robots: frozenset[str] = frozenset(),
) -> WaveReplay:
    """Replay one SAMG wave physically. ``locks`` (aisle holds + traffic reservations) is shared across waves
    and mutated."""
    windows = task_windows(trace)
    assignee = {a.task_id: a.agent_id for a in plan.assignments}
    pack_of_order = {}
    for t in tasks.values():
        if t.kind == "PACK":
            r = assignee.get(t.task_id)
            st = robots[r].station if r else None
            pack_of_order[t.order_id] = st or next(s.station_id for s in layout.stations if s.kind == "pack")

    out = WaveReplay(states=dict(states))
    segs: dict[str, list[Segment]] = {r: [] for r in robots}
    order = sorted(windows, key=lambda tid: (windows[tid][0], tid))
    per_m, per_s = timing["battery_per_m"], timing["battery_per_work_s"]
    traffic: Traffic = locks.traffic
    aisle_of = layout.aisle_of
    nb = layout.neighbours
    task_window: dict[str, tuple[float, float]] = {}

    for rid, robot in sorted(robots.items()):
        if not robot.mobile:
            continue
        st = out.states[rid]
        traffic.place(rid, st.cell, 0.0, aisle_of, st.battery, st.odometer)
        if st.failed and st.cell not in traffic.blocked:
            traffic.mark_failed(rid, st.failed_at if st.failed_at is not None else t_offset, st.cell)

    def label(cell: Cell | None) -> str:
        return layout.zone_at(cell) if cell is not None else "floor"

    def emit(rid: str, steps: list[Step], batt: float, odo: float, park: Cell) -> tuple[float, float]:
        track = segs[rid]
        for sp in steps:
            if sp.kind == "move":
                last = track[-1] if track else None
                if last and last.kind == "move" and last.status == sp.status and last.task == sp.task \
                        and abs(last.t1 - sp.t0) < _EPS:
                    last.path.append(sp.to)  # type: ignore[union-attr,arg-type]
                    last.t1 = sp.t1
                    last.battery1 -= per_m
                    last.odo1 += 1
                else:
                    track.append(Segment(rid, sp.t0, sp.t1, "move", sp.status, sp.cell, task=sp.task,
                                         path=[sp.cell, sp.to],  # type: ignore[list-item]
                                         battery0=batt, battery1=batt - per_m, odo0=odo, odo1=odo + 1,
                                         note="" if sp.task else "returning to the robot park"))
                batt -= per_m
                odo += 1
            elif sp.kind == "wait":
                where = label(sp.waiting_for)
                track.append(Segment(rid, sp.t0, sp.t1, "wait", "WAITING", sp.cell, task=sp.task, battery0=batt,
                                     battery1=batt, odo0=odo, odo1=odo, aisle=where, blockers=sp.blockers,
                                     note=f"waiting for {where}" + (f" ({', '.join(sp.blockers)} in the way)"
                                                                     if sp.blockers else "")))
                if sp.task:
                    out.waits.append(Wait(rid, sp.task, where, sp.cell, sp.t0, sp.t1, sp.blockers))
            elif sp.task is not None and sp.t1 > sp.t0 + _EPS:
                out.arrivals.append(Arrival(sp.t0, rid, sp.task, sp.place))
                track.append(Segment(rid, sp.t0, sp.t1, "work", sp.status, sp.cell, task=sp.task, battery0=batt,
                                     battery1=batt - per_s * (sp.t1 - sp.t0), odo0=odo, odo1=odo, note=sp.place))
                batt -= per_s * (sp.t1 - sp.t0)
            elif sp.task is not None:
                out.arrivals.append(Arrival(sp.t0, rid, sp.task, sp.place))
        if steps and steps[-1].task is None and steps[-1].cell == park:
            track.append(Segment(rid, steps[-1].t1, INF, "idle", "IDLE", park, battery0=batt, battery1=batt,
                                 odo0=odo, odo1=odo, note="parked"))
        return batt, odo

    def around_failures(rid: str, t0: float, legs: list[Leg]) -> list[Leg]:
        """A target cell occupied by a failed robot is serviced from the nearest free cell (same aisle first)."""
        out_legs = []
        for lg in legs:
            b = traffic.blocked.get(lg.target)
            if b is None or b[1] == rid or lg.park:
                out_legs.append(lg)
                continue
            aisle = aisle_of.get(lg.target)
            cands = sorted((c for c in layout.walkable if c not in traffic.blocked
                            and (aisle is None or aisle_of.get(c) == aisle)),
                           key=lambda c: (abs(c[0] - lg.target[0]) + abs(c[1] - lg.target[1]), c))
            if not cands:
                out_legs.append(lg)
                continue
            out_legs.append(replace(lg, target=cands[0], place=f"{lg.place} (reaching past failed {b[1]})"))
        return out_legs

    def detour(rid: str, start_cell: Cell, t0: float, legs: list[Leg], steps: list[Step]) -> None:
        """A robot planned after a failure: if its plain route crossed a failed robot, report the detour."""
        if not traffic.blocked:
            return
        cell, plain = start_cell, []
        for lg in legs:
            try:
                plain += route(layout, cell, lg.target)[1:]
            except Exception:   # noqa: BLE001 - unreachable target: nothing to compare
                return
            cell = lg.target
        hit = next(((c, traffic.blocked[c]) for c in plain if c in traffic.blocked and traffic.blocked[c][0] <= t0
                    and traffic.blocked[c][1] != rid), None)
        if hit is None:
            return
        moves = sum(1 for sp in steps if sp.kind == "move")
        task = next((lg.task for lg in legs if lg.task), None)
        out.reroutes.append(Reroute(t0, rid, hit[1][1], hit[0], aisle_of.get(hit[0]),
                                    round((moves - len(plain)) / robots[rid].speed, 3), task, replanned=False,
                                    t_fail=hit[1][0]))

    def go(rid: str, start_cell: Cell, j: int, t0: float, legs: list[Leg]) -> tuple[list[Step], list[Leg]]:
        robot = robots[rid]
        dt = 1.0 / robot.speed
        legs = around_failures(rid, t0, legs)
        steps = traffic.plan(rid, start_cell, t0, legs, dt, neighbours=nb, aisle_of=aisle_of)
        if steps is not None:
            detour(rid, start_cell, t0, legs, steps)
        if steps is None:      # no conflict-free plan: follow plain routes (logged, counted)
            traffic.fallbacks += 1
            log.warning("traffic: no conflict-free plan for %s at t=%.1f; following plain routes", rid, t0)
            steps, t, cell = [], t0, start_cell
            for k, leg in enumerate(legs):
                for a, b in zip(route(layout, cell, leg.target), route(layout, cell, leg.target)[1:], strict=False):
                    steps.append(Step("move", t, t + dt, a, to=b, status=leg.move_status, task=leg.task, leg=k))
                    t += dt
                end = max(t + leg.service, leg.min_end)
                steps.append(Step("work", t, end, leg.target, status=leg.service_status, task=leg.task,
                                  place=leg.place, leg=k))
                t, cell = end, leg.target
        occ = traffic.timeline[rid][j]
        traffic.commit(rid, j, t0, steps, legs, dt, aisle_of, per_m=per_m, per_s=per_s)
        _clip(segs[rid], t0)
        emit(rid, steps, occ.battery, occ.odometer, robot.home)
        return steps, legs

    def park_leg(rid: str) -> Leg:
        return Leg(robots[rid].home, 0.0, "MOVING", "IDLE", "robot park", None, park=True)

    def realize(rid: str, tid: str, steps: list[Step], legs: list[Leg]) -> None:
        """Book-keeping of a (re-)planned, non-failed task: physical window, overrun, robot state."""
        s, e = task_window[tid]
        last = max(k for k, lg in enumerate(legs) if lg.task == tid)
        work = [sp for sp in steps if sp.kind == "work" and sp.leg == last]
        finish = (work[0].t0 + legs[last].service) if work else e
        if finish > e + 1e-6:
            out.overruns_ms[tid] = (finish - e) * MS
        else:
            out.overruns_ms.pop(tid, None)
        out.physical[tid] = (s, max(finish, e))
        tl = traffic.timeline[rid]
        st = out.states[rid]
        out.states[rid] = replace(st, cell=tl[-1].cell, battery=tl[-1].battery, odometer=tl[-1].odometer,
                                  free_at=max(finish, e))

    def reroute_around(failed: str, cell: Cell, t: float) -> None:
        """The failure signal: every robot whose booked motion crosses ``cell`` re-plans from ``t``."""
        for rid in traffic.affected_by(cell, t, failed):
            ap = traffic.plans.get(rid)
            loc = traffic.locate(rid, t)
            if ap is None or loc is None:
                continue
            j, occ = loc
            start = max(t, occ.arrive)
            rem: list[Leg] = []
            for k, lg in enumerate(ap.legs):
                if ap.leg_end[k] <= start + _EPS and not lg.park:
                    continue
                if not rem and occ.cell == lg.target and occ.arrive <= start + _EPS:
                    rem.append(replace(lg, service=max(0.0, min(lg.service, ap.leg_end[k] - start))))
                else:
                    rem.append(lg)
            if not rem:
                continue
            rem = around_failures(rid, start, rem)
            task = next((lg.task for lg in rem if lg.task), None)
            old_end = max((ap.leg_end[k] for k, lg in enumerate(ap.legs) if lg.task), default=start)
            dt = 1.0 / robots[rid].speed
            steps = traffic.plan(rid, occ.cell, start, rem, dt, neighbours=nb, aisle_of=aisle_of)
            if steps is None:
                log.warning("traffic: %s has no alternative path around %s at %s", rid, failed, cell)
                continue
            traffic.commit(rid, j, start, steps, rem, dt, aisle_of, per_m=per_m, per_s=per_s)
            _clip(segs[rid], start)
            emit(rid, steps, occ.battery, occ.odometer, robots[rid].home)
            new_end = max((sp.t1 for sp in steps if sp.task), default=start)
            if task and task in task_window:
                realize(rid, task, steps, rem)
            out.reroutes.append(Reroute(t, rid, failed, cell, aisle_of.get(cell),
                                        round(new_end - old_end, 3) if task else 0.0, task, t_fail=t))

    for tid in order:
        s_rel, e_rel, failed = windows[tid]
        s, e = s_rel + t_offset, e_rel + t_offset
        task_window[tid] = (s, e)
        rid = assignee[tid]
        robot, st, task = robots[rid], out.states[rid], tasks[tid]

        if not robot.mobile:   # stationary pack arm: works in place for the SAMG window
            if st.free_at < s:
                segs[rid].append(Segment(rid, st.free_at, s, "idle", "IDLE", st.cell, battery0=st.battery,
                                         battery1=st.battery, odo0=st.odometer, odo1=st.odometer))
            segs[rid].append(Segment(rid, s, e, "work", "PACKING", st.cell, task=tid, battery0=st.battery,
                                     battery1=st.battery, odo0=st.odometer, odo1=st.odometer,
                                     note=f"{task.order_id} at {robot.station}"))
            out.physical[tid] = (s, e)
            out.states[rid] = replace(st, free_at=e)
            continue

        j, occ = traffic.locate(rid, s)  # type: ignore[misc]
        start = max(s, occ.arrive)
        if not segs[rid] and st.free_at < start:
            segs[rid].append(Segment(rid, max(st.free_at, t_offset), start, "idle", "IDLE", occ.cell,
                                     battery0=occ.battery, battery1=occ.battery, odo0=occ.odometer,
                                     odo1=occ.odometer))
        legs = [Leg(target, float(service), mstatus, sstatus, place, tid)
                for target, mstatus, service, sstatus, place in _legs(task, layout, inventory,
                                                                      pack_of_order[task.order_id], timing)]
        legs[-1] = replace(legs[-1], min_end=e)       # keeps servicing until SAMG's end (duration jitter)
        legs.append(park_leg(rid))
        steps, legs = go(rid, occ.cell, j, start, legs)

        if not failed:
            realize(rid, tid, steps, legs)
            continue

        # SAMG says the task failed at e: cut the physical activity there.
        loc = traffic.locate(rid, e)
        assert loc is not None
        k, at = loc
        cell = at.cell
        if at.arrive > e + _EPS and k > 0 and (e - at.t0) / max(at.arrive - at.t0, 1e-9) < 0.5:
            cell = traffic.timeline[rid][k - 1].cell
        if rid in failing_robots:
            _clip(segs[rid], e)
            track = segs[rid]
            if track and track[-1].kind == "move" and track[-1].path:
                while len(track[-1].path) > 1 and track[-1].path[-1] != cell:
                    track[-1].path.pop()
            last = track[-1] if track else None
            batt = last.battery1 if last else occ.battery
            odo = last.odo1 if last else occ.odometer
            track.append(Segment(rid, e, INF, "failed", "FAILED", cell, task=tid, battery0=batt, battery1=batt,
                                 odo0=odo, odo1=odo, note=f"robot failure during {tid}"))
            traffic.mark_failed(rid, e, cell)
            out.states[rid] = replace(st, cell=cell, battery=batt, odometer=odo, free_at=INF, failed=True,
                                      failed_at=e)
            out.physical[tid] = (s, e)
            reroute_around(rid, cell, e)
        else:   # the robot abandoned the task at e: it stops there and returns to the park
            kk, at2 = traffic.locate(rid, e)  # type: ignore[misc]
            restart = max(e, at2.arrive)
            go(rid, at2.cell, kk, restart, [park_leg(rid)])
            tl = traffic.timeline[rid]
            out.states[rid] = replace(st, cell=tl[-1].cell, battery=tl[-1].battery, odometer=tl[-1].odometer,
                                      free_at=e)
            out.physical[tid] = (s, e)

    out.segments = segs
    ends = [p[1] for p in out.physical.values()] + [max(windows[t][1] for t in windows) + t_offset if windows else t_offset]
    out.end_s = max(ends)
    return out
