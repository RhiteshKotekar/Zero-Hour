"""A* Path Planning and Aisle-Aligned Navigation for Warehouse AMRs."""

from __future__ import annotations

import heapq
import math
from typing import Collection
from samg.warehouse.layout import WarehouseLayout


def manhattan_distance(p1: tuple[int, int], p2: tuple[int, int]) -> float:
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def euclidean_distance(p1: tuple[int, int], p2: tuple[int, int]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def astar_path(
    layout: WarehouseLayout,
    start: tuple[int, int],
    goal: tuple[int, int],
    *,
    blocked_cells: Collection[tuple[int, int]] = (),
    turn_penalty: float = 0.25,
) -> list[tuple[int, int]]:
    """Compute optimal grid route from start to goal.

    Penalizes direction turns slightly to encourage straight travel down warehouse aisles.
    """
    if start == goal:
        return [start]

    if not layout.is_walkable(*start) or not layout.is_walkable(*goal):
        return []

    blocked = set(blocked_cells) - {start, goal}

    # Open set stores: (f_score, tie_breaker, current_node, current_direction)
    counter = 0
    open_set: list[tuple[float, int, tuple[int, int], tuple[int, int] | None]] = []
    heapq.heappush(open_set, (manhattan_distance(start, goal), counter, start, None))

    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], float] = {start: 0.0}

    visited: set[tuple[int, int]] = set()

    while open_set:
        _, _, current, prev_dir = heapq.heappop(open_set)

        if current == goal:
            # Reconstruct path
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        if current in visited:
            continue
        visited.add(current)

        for neighbor in layout.get_neighbors(*current):
            if neighbor in blocked:
                continue

            dx, dy = neighbor[0] - current[0], neighbor[1] - current[1]
            curr_dir = (dx, dy)

            # Step cost: base distance 1.0 + turn penalty if direction changes
            step_cost = 1.0
            if prev_dir is not None and prev_dir != curr_dir:
                step_cost += turn_penalty

            tentative_g = g_score[current] + step_cost
            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + manhattan_distance(neighbor, goal)
                counter += 1
                heapq.heappush(open_set, (f, counter, neighbor, curr_dir))

    return []  # No path found

