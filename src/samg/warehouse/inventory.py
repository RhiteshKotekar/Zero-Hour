"""SKU catalogue: where each SKU is stored, its pick face, and stock on hand."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from samg.warehouse.layout import Cell, Layout


@dataclass(frozen=True)
class Sku:
    sku: str
    name: str
    cell: Cell          # rack cell holding the SKU
    pick_face: Cell     # aisle cell a robot stands on to pick it
    aisle: str
    rack: str
    stock: int


class Inventory:
    def __init__(self, skus: dict[str, Sku]) -> None:
        self._skus = skus

    @classmethod
    def from_config(cls, cfg: dict[str, Any], layout: Layout, stock_overrides: dict[str, int] | None = None) -> Inventory:
        rack_of = {}
        for r in layout.racks:
            x0, y0, x1, y1 = r.rect
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    rack_of[(x, y)] = r.rack_id
        skus = {}
        for item in cfg["inventory"]:
            cell = tuple(item["cell"])
            if cell not in rack_of:
                raise ValueError(f"{item['sku']} is not stored on a rack cell: {cell}")
            faces = [(cell[0] + dx, cell[1]) for dx in (-1, 1) if (cell[0] + dx, cell[1]) in layout.aisle_of]
            if not faces:
                raise ValueError(f"{item['sku']} has no adjacent aisle pick face")
            face = faces[0]
            stock = int((stock_overrides or {}).get(item["sku"], item["stock"]))
            skus[item["sku"]] = Sku(item["sku"], item["name"], cell, face, layout.aisle_of[face], rack_of[cell], stock)
        return cls(skus)

    def __getitem__(self, sku: str) -> Sku:
        return self._skus[sku]

    def __contains__(self, sku: object) -> bool:
        return sku in self._skus

    def available(self, sku: str, qty: int = 1) -> bool:
        return sku in self._skus and self._skus[sku].stock >= qty

    def all(self) -> list[Sku]:
        return [self._skus[k] for k in sorted(self._skus)]

    def to_json(self) -> list[dict[str, Any]]:
        return [{"sku": s.sku, "name": s.name, "cell": list(s.cell), "pick_face": list(s.pick_face),
                 "aisle": s.aisle, "rack": s.rack, "stock": s.stock} for s in self.all()]
