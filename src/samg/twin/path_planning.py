"""Deterministic A* routing on the static warehouse grid (4-connected, unit cost).

Ties are broken by (f, h, cell) so the same request always yields the same route.
Routes are cached per (layout, start, goal); the layout is immutable.
"""

from __future__ import annotations

import heapq
from functools import lru_cache

from samg.twin.layout import Cell, Layout


class NoRoute(Exception):
    def __init__(self, start: Cell, goal: Cell) -> None:
        super().__init__(f"no walkable route {start} -> {goal}")
        self.start, self.goal = start, goal


def _h(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


@lru_cache(maxsize=65536)
def _astar(layout: Layout, start: Cell, goal: Cell) -> tuple[Cell, ...] | None:
    if start == goal:
        return (start,)
    walk = layout.walkable
    if goal not in walk:
        return None
    frontier: list[tuple[int, int, Cell]] = [(_h(start, goal), _h(start, goal), start)]
    came: dict[Cell, Cell | None] = {start: None}
    g: dict[Cell, int] = {start: 0}
    while frontier:
        _, _, cur = heapq.heappop(frontier)
        if cur == goal:
            path = [cur]
            while came[path[-1]] is not None:
                path.append(came[path[-1]])  # type: ignore[arg-type]
            return tuple(reversed(path))
        for n in layout.neighbours(cur):
            cost = g[cur] + 1
            if cost < g.get(n, 1 << 30):
                g[n] = cost
                came[n] = cur
                heapq.heappush(frontier, (cost + _h(n, goal), _h(n, goal), n))
    return None


def route(layout: Layout, start: Cell, goal: Cell) -> list[Cell]:
    """Shortest walkable route including both endpoints. Raises ``NoRoute``.

    ``start`` may be a non-walkable cell (e.g. a robot that is parked on a station):
    the search begins from it regardless.
    """
    path = _astar(layout, tuple(start), tuple(goal))
    if path is None:
        raise NoRoute(start, goal)
    return list(path)


def distance(layout: Layout, start: Cell, goal: Cell) -> int:
    """Route length in cells (metres)."""
    return len(route(layout, start, goal)) - 1
