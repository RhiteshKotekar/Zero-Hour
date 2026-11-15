"""Single-lane aisle locks: at most one robot inside a narrow pick aisle at a time.

A robot must hold an aisle's lock for the whole time it is inside (driving, picking,
driving out). Requests are granted in the order the physical replay processes tasks
(SAMG start order), so the result is deterministic and deadlock-free: a robot that
cannot get the lock waits at the aisle entrance until it is free.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Hold:
    aisle: str
    robot: str
    t0: float
    t1: float


class AisleLocks:
    def __init__(self) -> None:
        self._holds: dict[str, list[Hold]] = defaultdict(list)

    def earliest_free(self, aisle: str, t: float, duration: float, robot: str) -> tuple[float, list[str]]:
        """Earliest start >= ``t`` at which ``robot`` can hold ``aisle`` for ``duration`` seconds.

        Returns the start and the robots whose holds forced a wait (empty if none).
        """
        start = t
        blockers: list[str] = []
        changed = True
        while changed:
            changed = False
            for h in sorted(self._holds[aisle], key=lambda h: h.t0):
                if h.robot == robot:
                    continue
                if h.t0 < start + duration and start < h.t1:
                    start = h.t1
                    if h.robot not in blockers:
                        blockers.append(h.robot)
                    changed = True
        return start, blockers

    def acquire(self, aisle: str, robot: str, t0: float, t1: float) -> None:
        self._holds[aisle].append(Hold(aisle, robot, t0, t1))

    def holds(self) -> list[Hold]:
        return sorted((h for hs in self._holds.values() for h in hs), key=lambda h: (h.t0, h.aisle, h.robot))
