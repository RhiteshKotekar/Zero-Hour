"""2D Warehouse Grid Layout and Zone Definitions (SAMG Digital Twin)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import yaml


class CellType(str, Enum):
    WALKABLE = "WALKABLE"
    RACK = "RACK"
    PICK_STATION = "PICK_STATION"
    PACK_STATION = "PACK_STATION"
    RECEIVING = "RECEIVING"
    STAGING = "STAGING"
    DISPATCH = "DISPATCH"
    OBSTACLE = "OBSTACLE"


@dataclass(frozen=True)
class RackInfo:
    rack_id: str
    aisle: str
    x_min: int
    x_max: int
    y_min: int
    y_max: int
    access_points: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class BottleneckInfo:
    name: str
    cells: tuple[tuple[int, int], ...]
    capacity: int
    label: str


@dataclass
class WarehouseLayout:
    width: int = 30
    height: int = 20
    cell_size_m: float = 1.5
    racks: dict[str, RackInfo] = field(default_factory=dict)
    stations: dict[str, tuple[int, int]] = field(default_factory=dict)
    zones: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    bottlenecks: dict[str, BottleneckInfo] = field(default_factory=dict)
    grid: list[list[CellType]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.grid:
            self._build_grid()

    def _build_grid(self) -> None:
        self.grid = [[CellType.WALKABLE for _ in range(self.width)] for _ in range(self.height)]

        # Apply zones
        for zone_name, (x1, x2, y1, y2) in self.zones.items():
            ctype = CellType.WALKABLE
            if zone_name == "receiving":
                ctype = CellType.RECEIVING
            elif zone_name == "staging":
                ctype = CellType.STAGING
            elif zone_name == "dispatch":
                ctype = CellType.DISPATCH
            for y in range(max(0, y1), min(self.height, y2 + 1)):
                for x in range(max(0, x1), min(self.width, x2 + 1)):
                    self.grid[y][x] = ctype

        # Apply racks (solid obstacles)
        for rack in self.racks.values():
            for y in range(max(0, rack.y_min), min(self.height, rack.y_max + 1)):
                for x in range(max(0, rack.x_min), min(self.width, rack.x_max + 1)):
                    self.grid[y][x] = CellType.RACK

        # Apply stations
        for st_id, (x, y) in self.stations.items():
            if 0 <= x < self.width and 0 <= y < self.height:
                if "PICK" in st_id:
                    self.grid[y][x] = CellType.PICK_STATION
                else:
                    self.grid[y][x] = CellType.PACK_STATION

    def is_walkable(self, x: int, y: int) -> bool:
        """True if the cell is on the board and not a rack obstacle."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        return self.grid[y][x] != CellType.RACK

    def get_neighbors(self, x: int, y: int) -> list[tuple[int, int]]:
        """4-directional orthogonal neighbors that are walkable."""
        neighbors = []
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = x + dx, y + dy
            if self.is_walkable(nx, ny):
                neighbors.append((nx, ny))
        return neighbors

    def get_rack_access(self, rack_id: str) -> tuple[int, int]:
        """Find the nearest walkable cell to access the rack."""
        rack = self.racks.get(rack_id)
        if not rack:
            return (self.width // 2, self.height // 2)
        if rack.access_points:
            return rack.access_points[0]
        # Fallback to left or right of rack
        for x in (rack.x_min - 1, rack.x_max + 1):
            y = (rack.y_min + rack.y_max) // 2
            if self.is_walkable(x, y):
                return (x, y)
        return (rack.x_min, rack.y_min)

    @classmethod
    def from_yaml(cls, config_path: str | Path | None = None) -> WarehouseLayout:
        if config_path is None:
            config_path = Path(__file__).resolve().parents[3] / "config" / "warehouse.yaml"
        else:
            config_path = Path(config_path)

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        dims = cfg.get("dimensions", {})
        width = dims.get("width", 30)
        height = dims.get("height", 20)
        cell_size = dims.get("cell_size_m", 1.5)

        zones: dict[str, tuple[int, int, int, int]] = {}
        for z_key in ("receiving", "staging", "dispatch"):
            if z_key in cfg.get("zones", {}):
                b = cfg["zones"][z_key]["bounds"]
                zones[z_key] = (b[0], b[1], b[2], b[3])

        stations: dict[str, tuple[int, int]] = {}
        pick_cfg = cfg.get("zones", {}).get("picking_stations", {}).get("stations", [])
        for st in pick_cfg:
            stations[st["id"]] = (st["pos"][0], st["pos"][1])
        pack_cfg = cfg.get("zones", {}).get("packing_stations", {}).get("stations", [])
        for st in pack_cfg:
            stations[st["id"]] = (st["pos"][0], st["pos"][1])

        racks: dict[str, RackInfo] = {}
        for r in cfg.get("racks", []):
            b = r["bounds"]
            access = []
            # Calculate aisle access on both lateral flanks
            for y_pt in range(b[2], b[3] + 1):
                if b[0] - 1 >= 0:
                    access.append((b[0] - 1, y_pt))
                if b[1] + 1 < width:
                    access.append((b[1] + 1, y_pt))
            racks[r["id"]] = RackInfo(
                rack_id=r["id"],
                aisle=r.get("aisle", "A1"),
                x_min=b[0],
                x_max=b[1],
                y_min=b[2],
                y_max=b[3],
                access_points=tuple(access),
            )

        bottlenecks: dict[str, BottleneckInfo] = {}
        for bn in cfg.get("aisles", {}).get("bottlenecks", []):
            cells = tuple(tuple(c) for c in bn["cells"])
            bottlenecks[bn["aisle"]] = BottleneckInfo(
                name=bn["aisle"],
                cells=cells,
                capacity=bn.get("capacity", 1),
                label=bn.get("label", bn["aisle"]),
            )

        layout = cls(
            width=width,
            height=height,
            cell_size_m=cell_size,
            racks=racks,
            stations=stations,
            zones=zones,
            bottlenecks=bottlenecks,
        )
        return layout

