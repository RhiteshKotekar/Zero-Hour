"""Physical replay: SAMG's allocation + execution trace -> robot motion on the warehouse floor.

SAMG decides *who* does each task and *when* it starts and ends (``AllocationPlan`` and
``ExecutionTrace``). This module turns each executed task into physical activity for its
robot: an A* route from the robot's actual position, service at the pick face / station,
and waits at narrow-aisle entrances when another robot holds the aisle lock.

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

from dataclasses import dataclass, field, replace
from typing import Any

from samg.domain import AllocationPlan, ExecutionTrace, TaskState
from samg.twin.agents import RobotSpec
from samg.twin.congestion import AisleLocks
from samg.twin.inventory import Inventory
from samg.twin.layout import Cell, Layout
from samg.twin.path_planning import route
from samg.twin.task_generator import WarehouseTask

MS = 1000.0
INF = float("inf")


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
    """Replay one SAMG wave physically. ``locks`` is shared across waves and mutated."""
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

    for tid in order:
        s_rel, e_rel, failed = windows[tid]
        s, e = s_rel + t_offset, e_rel + t_offset
        rid = assignee[tid]
        robot, st, task = robots[rid], out.states[rid], tasks[tid]
        track: list[Segment] = []
        if st.free_at < s:
            segs[rid].append(Segment(rid, st.free_at, s, "idle", "IDLE", st.cell, battery0=st.battery,
                                     battery1=st.battery, odo0=st.odometer, odo1=st.odometer))
        t, cell, batt, odo = s, st.cell, st.battery, st.odometer

        if not robot.mobile:   # stationary pack arm: works in place for the SAMG window
            track.append(Segment(rid, s, e, "work", "PACKING", cell, task=tid, battery0=batt, battery1=batt,
                                 odo0=odo, odo1=odo, note=f"{task.order_id} at {robot.station}"))
            finish = e
        else:
            steps: list[tuple] = []
            for target, mstatus, service, sstatus, place in _legs(task, layout, inventory,
                                                                  pack_of_order[task.order_id], timing):
                path = route(layout, cell, target)
                steps += [("move", a, b, mstatus) for a, b in zip(path, path[1:], strict=False)]
                steps.append(("work", target, float(service), sstatus, place))
                cell = target
            cell = st.cell
            dt_move = 1.0 / robot.speed
            aisle_of = layout.aisle_of
            i = 0
            while i < len(steps):
                step = steps[i]
                if step[0] == "move":
                    _, a, b, mstatus = step
                    entering = aisle_of.get(b)
                    if entering and aisle_of.get(a) != entering:
                        dur, j = 0.0, i
                        while j < len(steps):
                            s2 = steps[j]
                            dur += dt_move if s2[0] == "move" else s2[2]
                            if s2[0] == "move" and aisle_of.get(s2[2]) != entering:
                                break
                            j += 1
                        start, blockers = locks.earliest_free(entering, t, dur, rid)
                        if start > t + 1e-9:
                            track.append(Segment(rid, t, start, "wait", "WAITING", a, task=tid, battery0=batt,
                                                 battery1=batt, odo0=odo, odo1=odo, aisle=entering,
                                                 blockers=tuple(blockers),
                                                 note=f"waiting for {entering} ({', '.join(blockers)} inside)"))
                            out.waits.append(Wait(rid, tid, entering, a, t, start, tuple(blockers)))
                            t = start
                        locks.acquire(entering, rid, t, t + dur)
                    last = track[-1] if track else None
                    if last and last.kind == "move" and last.status == mstatus and last.t1 == t:
                        last.path.append(b)  # type: ignore[union-attr]
                        last.t1 = t + dt_move
                        last.battery1 -= per_m
                        last.odo1 += 1
                    else:
                        track.append(Segment(rid, t, t + dt_move, "move", mstatus, a, task=tid, path=[a, b],
                                             battery0=batt, battery1=batt - per_m, odo0=odo, odo1=odo + 1))
                    t += dt_move
                    batt -= per_m
                    odo += 1
                    cell = b
                else:
                    _, at, service, sstatus, place = step
                    out.arrivals.append(Arrival(t, rid, tid, place))
                    track.append(Segment(rid, t, t + service, "work", sstatus, at, task=tid, battery0=batt,
                                         battery1=batt - per_s * service, odo0=odo, odo1=odo, note=place))
                    t += service
                    batt -= per_s * service
                    cell = at
                i += 1
            finish = t

        if failed:
            # SAMG says the task failed at e: cut the physical activity there.
            kept: list[Segment] = []
            for sg in track:
                if sg.t0 >= e:
                    break
                if sg.t1 > e:
                    frac = (e - sg.t0) / max(sg.t1 - sg.t0, 1e-9)
                    if sg.kind == "move" and sg.path:
                        n = max(1, int(frac * (len(sg.path) - 1)))
                        sg.path = sg.path[: n + 1]
                    sg.battery1 = sg.battery0 + (sg.battery1 - sg.battery0) * frac
                    sg.odo1 = sg.odo0 + (sg.odo1 - sg.odo0) * frac
                    sg.t1 = e
                kept.append(sg)
            track = kept
            if track:
                lastseg = track[-1]
                cell = lastseg.path[-1] if lastseg.kind == "move" and lastseg.path else lastseg.cell
                batt, odo = lastseg.battery1, lastseg.odo1
            if rid in failing_robots:
                track.append(Segment(rid, e, INF, "failed", "FAILED", cell, task=tid, battery0=batt, battery1=batt,
                                     odo0=odo, odo1=odo, note=f"robot failure during {tid}"))
                out.states[rid] = replace(st, cell=cell, battery=batt, odometer=odo, free_at=INF, failed=True,
                                          failed_at=e)
            else:
                out.states[rid] = replace(st, cell=cell, battery=batt, odometer=odo, free_at=e)
            out.physical[tid] = (s, e)
        else:
            if finish < e and track:
                track[-1].t1 = e   # keeps servicing until SAMG's end (duration jitter)
                if track[-1].kind != "work":
                    track.append(Segment(rid, finish, e, "work", "TRANSPORTING", cell, task=tid, battery0=batt,
                                         battery1=batt, odo0=odo, odo1=odo))
            elif finish > e + 1e-6:
                out.overruns_ms[tid] = (finish - e) * MS
            out.physical[tid] = (s, max(finish, e))
            out.states[rid] = replace(st, cell=cell, battery=batt, odometer=odo, free_at=max(finish, e))
        segs[rid].extend(track)

    out.segments = segs
    ends = [p[1] for p in out.physical.values()] + [max(windows[t][1] for t in windows) + t_offset if windows else t_offset]
    out.end_s = max(ends)
    return out
