"""Space-time traffic control for the physical replay: no two robots ever occupy the same cell.

Every mobile robot books the cells it will occupy and when (a reservation table shared by all robots
and carried across waves). Robots are planned in the order the replay processes them (SAMG start
order); each one is routed with Safe Interval Path Planning (SIPP, Phillips & Likhachev, ICRA 2011)
around the bookings already made, waiting where it must. Deterministic: ties break on cell order.

Occupancy model: a robot occupies a cell from the moment it starts entering it until it has fully
left it (arrived in the next cell), so two robots are always at least one cell apart and can never
swap places head-on. A narrow pick aisle is one shared resource: at most one moving robot inside it
at a time (the single-lane aisle rule). Idle robots return to their own park cell.

A robot that fails becomes a permanent obstacle on its cell only (not on the whole aisle). Robots
whose planned motion crosses that cell are told immediately and re-planned from that moment along an
alternative route (``reroute``); robots planned afterwards route around it from the start.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

INF = math.inf
EPS = 1e-6
MAX_EXPANSIONS = 60000

Cell = tuple[int, int]


@dataclass
class Occ:
    """One robot occupying one cell over [t0, t1) (t1 = INF: parked or not yet planned to leave)."""

    robot: str
    cell: Cell
    key: object            # reservation resource: the cell, or the aisle id for a pick-aisle cell
    t0: float              # starts entering the cell
    arrive: float          # fully inside the cell
    t1: float              # fully left the cell
    battery: float = 100.0
    odometer: float = 0.0


@dataclass(frozen=True)
class Leg:
    """Go to ``target`` and stay ``service`` seconds (and at least until ``min_end``)."""

    target: Cell
    service: float
    move_status: str
    service_status: str
    place: str = ""
    task: str | None = None
    min_end: float = 0.0
    park: bool = False      # final park leg: the robot may stay there indefinitely


@dataclass
class Step:
    kind: str                       # move | wait | work
    t0: float
    t1: float
    cell: Cell                      # move: from-cell; wait/work: the cell
    to: Cell | None = None
    status: str = ""
    task: str | None = None
    place: str = ""
    waiting_for: Cell | None = None
    blockers: tuple[str, ...] = ()
    leg: int = 0


@dataclass
class ActivePlan:
    """The latest plan of a robot (kept so it can be re-planned when a failure blocks its path)."""

    legs: list[Leg]
    leg_end: list[float]            # time each leg's service ends
    dt: float


@dataclass
class Reroute:
    t: float
    robot: str
    failed: str
    cell: Cell
    aisle: str | None
    delay_s: float
    task: str | None
    replanned: bool = True          # False: planned around an earlier failure from the start (a detour)
    t_fail: float = 0.0             # when the failed robot went down (the signal)


@dataclass
class Traffic:
    occ: dict[object, list[Occ]] = field(default_factory=dict)
    timeline: dict[str, list[Occ]] = field(default_factory=dict)
    blocked: dict[Cell, tuple[float, str]] = field(default_factory=dict)   # failed robot: cell -> (from t, robot)
    plans: dict[str, ActivePlan] = field(default_factory=dict)
    fallbacks: int = 0              # plans that could not be made conflict-free (should stay 0)

    # --- reservations -------------------------------------------------------------------

    @staticmethod
    def key(cell: Cell, aisle_of: dict[Cell, str]) -> object:
        a = aisle_of.get(cell)
        return ("aisle", a) if a else cell

    def place(self, robot: str, cell: Cell, t: float, aisle_of: dict[Cell, str], battery: float = 100.0,
              odometer: float = 0.0) -> None:
        """Register a robot that is not in the table yet, parked on ``cell`` from ``t``."""
        if robot in self.timeline:
            return
        o = Occ(robot, cell, self.key(cell, aisle_of), t, t, INF, battery, odometer)
        self.timeline[robot] = [o]
        self.occ.setdefault(o.key, []).append(o)

    def _remove(self, o: Occ) -> None:
        lst = self.occ.get(o.key)
        if lst is not None:
            for i, x in enumerate(lst):
                if x is o:
                    del lst[i]
                    break

    def safe_intervals(self, cell: Cell, robot: str, aisle_of: dict[Cell, str]) -> list[tuple[float, float]]:
        busy = sorted((o.t0, o.t1) for o in self.occ.get(self.key(cell, aisle_of), ()) if o.robot != robot)
        b = self.blocked.get(cell)
        if b is not None and b[1] != robot:
            busy.append((b[0], INF))
            busy.sort()
        out: list[tuple[float, float]] = []
        t = 0.0
        for a, z in busy:
            if a > t + EPS:
                out.append((t, a))
            t = max(t, z)
            if t == INF:
                break
        if t < INF:
            out.append((t, INF))
        return out

    def who(self, cell: Cell, t0: float, t1: float, robot: str, aisle_of: dict[Cell, str]) -> tuple[str, ...]:
        names = {o.robot for o in self.occ.get(self.key(cell, aisle_of), ())
                 if o.robot != robot and o.t0 < t1 and t0 < o.t1}
        b = self.blocked.get(cell)
        if b is not None and b[1] != robot and b[0] < t1:
            names.add(b[1])
        return tuple(sorted(names))

    # --- position along a robot's timeline -------------------------------------------------

    def locate(self, robot: str, t: float) -> tuple[int, Occ] | None:
        """(index, occupancy) of the cell the robot is in, or entering, at ``t``."""
        tl = self.timeline.get(robot)
        if not tl:
            return None
        j = 0
        for i, o in enumerate(tl):
            if o.t0 <= t + EPS:
                j = i
            else:
                break
        return j, tl[j]

    def truncate(self, robot: str, j: int) -> None:
        """Drop everything after timeline index ``j`` and keep the robot on that cell (until re-planned)."""
        tl = self.timeline[robot]
        for o in tl[j + 1:]:
            self._remove(o)
        del tl[j + 1:]
        tl[j].t1 = INF

    def mark_failed(self, robot: str, t: float, cell: Cell) -> None:
        """The robot is down on ``cell`` from ``t``: a permanent per-cell obstacle (not a whole-aisle hold)."""
        tl = self.timeline.get(robot, [])
        for o in list(tl):
            if o.t1 > t + EPS:
                if o.t0 >= t - EPS and o.cell != cell:
                    self._remove(o)
                    tl.remove(o)
                else:
                    o.t1 = max(o.t0, t)
        self.blocked[cell] = (t, robot)
        self.plans.pop(robot, None)

    def affected_by(self, cell: Cell, t: float, exclude: str) -> list[str]:
        """Robots whose booked motion uses ``cell`` after ``t``."""
        return sorted({o.robot for lst in self.occ.values() for o in lst
                       if o.robot != exclude and o.cell == cell and o.t1 > t + EPS})

    # --- planning -----------------------------------------------------------------------------

    def plan(self, robot: str, start: Cell, t: float, legs: list[Leg], dt: float, *,
             neighbours: Callable[[Cell], Iterable[Cell]], aisle_of: dict[Cell, str]) -> list[Step] | None:
        """SIPP over (cell, safe interval, leg). Returns the timed steps, or None if no plan exists."""
        cache: dict[Cell, list[tuple[float, float]]] = {}

        def safe(c: Cell) -> list[tuple[float, float]]:
            if c not in cache:
                cache[c] = self.safe_intervals(c, robot, aisle_of)
            return cache[c]

        def man(a: Cell, b: Cell) -> int:
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        n = len(legs)
        rest = [0.0] * (n + 1)
        for k in range(n - 1, -1, -1):
            rest[k] = legs[k].service + (man(legs[k].target, legs[k + 1].target) * dt if k + 1 < n else 0.0) + rest[k + 1]

        def h(c: Cell, k: int) -> float:
            return 0.0 if k >= n else man(c, legs[k].target) * dt + rest[k]

        start_iv = next((i for i, (a, z) in enumerate(safe(start)) if a <= t + EPS and t < z - EPS), None)
        if start_iv is None:
            return None
        s0 = (start, start_iv, 0)
        best: dict[tuple, float] = {s0: t}
        parent: dict[tuple, tuple] = {s0: (None, "start", t, t)}
        frontier: list[tuple[float, float, Cell, int, int]] = [(t + h(start, 0), t, start, start_iv, 0)]
        expansions = 0
        goal = None
        while frontier:
            _f, g, c, iv, k = heapq.heappop(frontier)
            st = (c, iv, k)
            if g > best.get(st, INF) + EPS:
                continue
            if k >= n:
                goal = st
                break
            expansions += 1
            if expansions > MAX_EXPANSIONS:
                return None
            a_c, z_c = safe(c)[iv]
            leg = legs[k]
            if c == leg.target:
                end = max(g + leg.service, leg.min_end)
                ok = z_c == INF if leg.park else end + (dt if k + 1 < n and legs[k + 1].target != c else 0.0) <= z_c + EPS
                if ok:
                    nxt = (c, iv, k + 1)
                    if end < best.get(nxt, INF) - EPS:
                        best[nxt] = end
                        parent[nxt] = (st, "work", g, end)
                        heapq.heappush(frontier, (end + h(c, k + 1), end, c, iv, k + 1))
            for v in sorted(neighbours(c)):
                for j, (a_v, z_v) in enumerate(safe(v)):
                    if z_v <= g + dt + EPS:
                        continue
                    dep = max(g, a_v)
                    if dep + dt > z_c + EPS:
                        break
                    if dep + dt >= z_v - EPS:
                        continue
                    arr = dep + dt
                    nxt = (v, j, k)
                    if arr < best.get(nxt, INF) - EPS:
                        best[nxt] = arr
                        parent[nxt] = (st, "move", dep, arr)
                        heapq.heappush(frontier, (arr + h(v, k), arr, v, j, k))
        if goal is None:
            return None

        chain = []
        cur: tuple | None = goal
        while cur is not None:
            prev, kind, a, b = parent[cur]
            chain.append((prev, cur, kind, a, b))
            cur = prev
        chain.reverse()
        steps: list[Step] = []
        ready = t                                    # time the robot is free to act at its cell
        for prev, cur, kind, a, b in chain[1:]:
            c_prev, k_prev = prev[0], prev[2]
            leg = legs[k_prev]
            if kind == "move":
                if a > ready + EPS:
                    steps.append(Step("wait", ready, a, c_prev, status="WAITING", task=leg.task, waiting_for=cur[0],
                                      blockers=self.who(cur[0], ready, a, robot, aisle_of), leg=k_prev))
                steps.append(Step("move", a, b, c_prev, to=cur[0], status=leg.move_status, task=leg.task, leg=k_prev))
            else:   # leg completed here (zero-length services are kept so the leg end is recorded)
                steps.append(Step("work", a, b, c_prev, status=leg.service_status, task=leg.task, place=leg.place,
                                  leg=k_prev))
            ready = b
        return steps

    def commit(self, robot: str, j: int, start_t: float, steps: list[Step], legs: list[Leg], dt: float,
               aisle_of: dict[Cell, str], *, per_m: float, per_s: float) -> None:
        """Book a plan made from timeline index ``j`` (the robot's cell at ``start_t``)."""
        tl = self.timeline[robot]
        for o in tl[j + 1:]:
            self._remove(o)
        del tl[j + 1:]
        cur = tl[j]
        batt, odo = cur.battery, cur.odometer
        leg_end = [INF] * len(legs)
        for s in steps:
            if s.kind == "move":
                cur.t1 = s.t1
                batt -= per_m
                odo += 1
                cur = Occ(robot, s.to, self.key(s.to, aisle_of), s.t0, s.t1, INF, batt, odo)  # type: ignore[arg-type]
                tl.append(cur)
                self.occ.setdefault(cur.key, []).append(cur)
            elif s.kind == "work":
                batt -= per_s * (s.t1 - s.t0)
                leg_end[s.leg] = s.t1
        for k, leg in enumerate(legs):
            if leg_end[k] == INF:
                leg_end[k] = max(leg_end[k - 1] if k else start_t, leg.min_end)
        self.plans[robot] = ActivePlan(list(legs), leg_end, dt)
