"""Static warehouse layout: grid, zones, racks, narrow aisles, stations (owner: Dev B).

Loaded once from ``config/twin.yaml`` and never mutated during a run. Blocking an
aisle (failure injection) produces a new ``Layout`` via ``with_blocked_aisles``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path
from typing import Any

Cell = tuple[int, int]
Rect = tuple[int, int, int, int]

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "config" / "twin.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    import yaml

    with Path(path or DEFAULT_CONFIG).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def rect_cells(rect: Rect) -> list[Cell]:
    x0, y0, x1, y1 = rect
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


@dataclass(frozen=True)
class Zone:
    zone_id: str
    label: str
    rect: Rect


@dataclass(frozen=True)
class Rack:
    rack_id: str
    rect: Rect


@dataclass(frozen=True)
class Aisle:
    aisle_id: str
    rect: Rect

    @property
    def cells(self) -> list[Cell]:
        return rect_cells(self.rect)


@dataclass(frozen=True)
class Station:
    station_id: str
    kind: str          # pack | dock | charger
    label: str
    rect: Rect
    access: Cell
    outbound: Cell | None = None


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    zones: tuple[Zone, ...]
    racks: tuple[Rack, ...]
    aisles: tuple[Aisle, ...]
    stations: tuple[Station, ...]
    walls: tuple[Rect, ...]
    consolidation: tuple[tuple[str, Cell], ...]
    blocked_aisles: frozenset[str] = field(default=frozenset())

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> Layout:
        w = cfg["warehouse"]
        return cls(
            width=int(w["width"]), height=int(w["height"]),
            zones=tuple(Zone(z["id"], z["label"], tuple(z["rect"])) for z in w["zones"]),
            racks=tuple(Rack(r["id"], tuple(r["rect"])) for r in w["racks"]),
            aisles=tuple(Aisle(a["id"], tuple(a["rect"])) for a in w["aisles"]),
            stations=tuple(Station(s["id"], s["kind"], s["label"], tuple(s["rect"]), tuple(s["access"]),
                                   tuple(s["outbound"]) if s.get("outbound") else None) for s in w["stations"]),
            walls=tuple(tuple(r) for r in w.get("walls", [])),
            consolidation=tuple((c["id"], tuple(c["cell"])) for c in w["consolidation_points"]),
        )

    def with_blocked_aisles(self, aisle_ids: set[str] | frozenset[str]) -> Layout:
        unknown = set(aisle_ids) - {a.aisle_id for a in self.aisles}
        if unknown:
            raise ValueError(f"unknown aisles {sorted(unknown)}")
        return replace(self, blocked_aisles=frozenset(aisle_ids))

    # --- derived, cached ----------------------------------------------------

    @cached_property
    def solid(self) -> frozenset[Cell]:
        """Cells nothing can drive through: racks, station footprints, walls."""
        cells: set[Cell] = set()
        for r in self.racks:
            cells.update(rect_cells(r.rect))
        for s in self.stations:
            cells.update(rect_cells(s.rect))
        for wall in self.walls:
            cells.update(rect_cells(wall))
        return frozenset(cells)

    @cached_property
    def aisle_of(self) -> dict[Cell, str]:
        return {c: a.aisle_id for a in self.aisles for c in a.cells}

    @cached_property
    def walkable(self) -> frozenset[Cell]:
        blocked = {c for a in self.aisles if a.aisle_id in self.blocked_aisles for c in a.cells}
        return frozenset((x, y) for x in range(self.width) for y in range(self.height)
                         if (x, y) not in self.solid and (x, y) not in blocked)

    def station(self, station_id: str) -> Station:
        for s in self.stations:
            if s.station_id == station_id:
                return s
        raise KeyError(station_id)

    def consolidation_point(self, point_id: str) -> Cell:
        return dict(self.consolidation)[point_id]

    def zone_at(self, cell: Cell) -> str:
        """Most specific zone label for a cell (aisle and rack names win over area names)."""
        if cell in self.aisle_of:
            return self.aisle_of[cell]
        for r in self.racks:
            if cell in rect_cells(r.rect):
                return f"Rack {r.rack_id}"
        for s in self.stations:
            if cell in rect_cells(s.rect) or cell == s.access:
                return s.label
        for z in self.zones:
            x0, y0, x1, y1 = z.rect
            if x0 <= cell[0] <= x1 and y0 <= cell[1] <= y1:
                return z.label
        return "Floor"

    def neighbours(self, cell: Cell) -> list[Cell]:
        x, y = cell
        out = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in self.walkable:
                out.append(n)
        return out

    def to_json(self) -> dict[str, Any]:
        return {
            "width": self.width, "height": self.height,
            "zones": [{"id": z.zone_id, "label": z.label, "rect": list(z.rect)} for z in self.zones],
            "racks": [{"id": r.rack_id, "rect": list(r.rect)} for r in self.racks],
            "aisles": [{"id": a.aisle_id, "rect": list(a.rect), "blocked": a.aisle_id in self.blocked_aisles}
                       for a in self.aisles],
            "stations": [{"id": s.station_id, "kind": s.kind, "label": s.label, "rect": list(s.rect),
                          "access": list(s.access), "outbound": list(s.outbound) if s.outbound else None}
                         for s in self.stations],
            "walls": [list(w) for w in self.walls],
            "consolidation": [{"id": i, "cell": list(c)} for i, c in self.consolidation],
        }
