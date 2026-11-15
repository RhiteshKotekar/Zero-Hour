"""Tests for Warehouse Grid Layout and Obstacle Representation."""

from samg.warehouse.layout import CellType, WarehouseLayout


def test_default_layout_dimensions() -> None:
    layout = WarehouseLayout.from_yaml()
    assert layout.width == 30
    assert layout.height == 20
    assert len(layout.grid) == 20
    assert len(layout.grid[0]) == 30


def test_rack_solid_and_access_points() -> None:
    layout = WarehouseLayout.from_yaml()
    # Check that a rack cell is not walkable
    rack = layout.racks.get("RACK-A01")
    assert rack is not None
    assert layout.grid[rack.y_min][rack.x_min] == CellType.RACK
    assert not layout.is_walkable(rack.x_min, rack.y_min)

    # Check access point is walkable
    access = layout.get_rack_access("RACK-A01")
    assert layout.is_walkable(*access)


def test_stations_and_zones() -> None:
    layout = WarehouseLayout.from_yaml()
    assert "PICK-01" in layout.stations
    assert "PACK-01" in layout.stations
    pick_pos = layout.stations["PICK-01"]
    assert layout.grid[pick_pos[1]][pick_pos[0]] == CellType.PICK_STATION
    assert layout.is_walkable(*pick_pos)


def test_neighbors_exclude_racks() -> None:
    layout = WarehouseLayout.from_yaml()
    rack = layout.racks["RACK-A01"]
    # Access cell right next to the rack
    adj_x, adj_y = rack.x_min - 1, rack.y_min
    if layout.is_walkable(adj_x, adj_y):
        neighbors = layout.get_neighbors(adj_x, adj_y)
        # Neighboring rack cell must not be in neighbors
        assert (rack.x_min, rack.y_min) not in neighbors

