"""Tests for AMR A* Path Planning and Aisle Navigation."""

from samg.warehouse.layout import WarehouseLayout
from samg.warehouse.path_planning import astar_path, manhattan_distance


def test_path_trivial_and_direct() -> None:
    layout = WarehouseLayout.from_yaml()
    # Path to same cell
    p = astar_path(layout, (2, 2), (2, 2))
    assert p == [(2, 2)]

    # Short orthogonal step in aisle
    p = astar_path(layout, (2, 2), (2, 4))
    assert len(p) == 3
    assert p[0] == (2, 2)
    assert p[-1] == (2, 4)


def test_path_navigates_around_racks() -> None:
    layout = WarehouseLayout.from_yaml()
    rack = layout.racks["RACK-A01"]

    # Start to left of rack, goal to right of rack
    start = (rack.x_min - 1, rack.y_min)
    goal = (rack.x_max + 1, rack.y_min)

    path = astar_path(layout, start, goal)
    assert len(path) > 0
    assert path[0] == start
    assert path[-1] == goal

    # No step in the path should be unwalkable (inside the rack)
    for pt in path:
        assert layout.is_walkable(*pt)


def test_path_avoids_blocked_cells() -> None:
    layout = WarehouseLayout.from_yaml()
    start = (0, 0)
    goal = (0, 2)
    # Block the direct intermediate cell
    blocked = {(0, 1)}
    path = astar_path(layout, start, goal, blocked_cells=blocked)
    assert len(path) > 0
    assert (0, 1) not in path
    assert path[0] == start
    assert path[-1] == goal

