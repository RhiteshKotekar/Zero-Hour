"""Orders -> warehouse tasks -> SAMG ``TaskSpec``s.

Each order becomes ``PICK`` (one per SKU, parallel) -> ``TRANSPORT`` -> ``PACK`` -> ``DISPATCH``.
SAMG task durations are agent-independent, so each duration is a deterministic estimate:
service time plus the A* travel a task needs from its natural start point (the order's
consolidation point for picks/transport, the nearest pack station for dispatch) at the
slowest capable robot's speed. The physical replay later measures the real travel from
each robot's actual position; any overrun is fed back to SAMG execution (see ``adapter``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from samg.domain import TaskSpec
from samg.twin.agents import RobotSpec
from samg.twin.inventory import Inventory
from samg.twin.layout import Cell, Layout
from samg.twin.orders import Order
from samg.twin.path_planning import NoRoute, distance

MS = 1000.0
KINDS = ("PICK", "TRANSPORT", "PACK", "DISPATCH")
CAPABILITY = {"PICK": "picking", "TRANSPORT": "transport", "PACK": "packing", "DISPATCH": "loading"}


@dataclass(frozen=True)
class WarehouseTask:
    task_id: str
    order_id: str
    kind: str
    priority: str
    sku: str | None
    capability: str
    consolidation: str          # order's tote drop point id
    dock: str                   # outbound dock id
    n_items: int
    estimate_s: float
    estimate_travel_m: int
    dependencies: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.kind} {self.sku}" if self.sku else self.kind


@dataclass(frozen=True)
class OrderHold:
    order_id: str
    sku: str
    reason: str


def _slowest(robots: list[RobotSpec], capability: str) -> float:
    speeds = [r.speed for r in robots if capability in r.capabilities and r.mobile]
    if not speeds:
        raise ValueError(f"no mobile robot can do {capability}")
    return min(speeds)


def _nearest(layout: Layout, origin: Cell, cells: list[Cell]) -> Cell:
    return min(cells, key=lambda c: (distance(layout, origin, c), c))


def generate_tasks(orders: list[Order], inventory: Inventory, layout: Layout, robots: list[RobotSpec],
                   cfg: dict[str, Any]) -> tuple[list[WarehouseTask], list[OrderHold]]:
    """Warehouse tasks for every order whose SKUs are in stock; holds for the rest."""
    timing, samg = cfg["timing"], cfg["samg"]
    points = [pid for pid, _ in layout.consolidation]
    pack_access = [s.access for s in layout.stations if s.kind == "pack"]
    pack_out = [s.outbound for s in layout.stations if s.kind == "pack" and s.outbound]
    tasks: list[WarehouseTask] = []
    holds: list[OrderHold] = []
    for i, order in enumerate(orders):
        cp = points[i % len(points)]
        drop = layout.consolidation_point(cp)
        reasons = {}
        for s in order.items:
            if s not in inventory:
                reasons[s] = "UNKNOWN_SKU"
            elif not inventory.available(s):
                reasons[s] = "OUT_OF_STOCK"
            else:
                try:
                    distance(layout, drop, inventory[s].pick_face)
                except NoRoute:
                    reasons[s] = "PICK_FACE_UNREACHABLE"   # e.g. its aisle is blocked
        if reasons:
            holds.extend(OrderHold(order.order_id, s, r) for s, r in reasons.items())
            continue
        dock = samg["dock_by_priority"][order.priority]
        dock_cell = layout.station(dock).access
        common = dict(order_id=order.order_id, priority=order.priority, consolidation=cp, dock=dock,
                      n_items=len(order.items))
        picks = []
        v = _slowest(robots, "picking")
        for sku in order.items:
            face = inventory[sku].pick_face
            travel = distance(layout, drop, face) + distance(layout, face, drop)
            tid = f"{order.order_id}-PICK-{sku.replace('-', '')}"
            picks.append(tid)
            tasks.append(WarehouseTask(task_id=tid, kind="PICK", sku=sku, capability="picking",
                                       estimate_s=travel / v + timing["pick_s"] + timing["drop_s"],
                                       estimate_travel_m=travel, dependencies=(), **common))
        v = _slowest(robots, "transport")
        pack = _nearest(layout, drop, pack_access)
        travel = 2 * distance(layout, drop, pack)
        tasks.append(WarehouseTask(task_id=f"{order.order_id}-TRANSPORT", kind="TRANSPORT", sku=None,
                                   capability="transport", estimate_travel_m=travel,
                                   estimate_s=travel / v + timing["transport_load_s"] + timing["transport_unload_s"],
                                   dependencies=tuple(picks), **common))
        tasks.append(WarehouseTask(task_id=f"{order.order_id}-PACK", kind="PACK", sku=None, capability="packing",
                                   estimate_travel_m=0,
                                   estimate_s=timing["pack_base_s"] + timing["pack_per_item_s"] * len(order.items),
                                   dependencies=(f"{order.order_id}-TRANSPORT",), **common))
        v = _slowest(robots, "loading")
        out = _nearest(layout, dock_cell, pack_out)
        travel = 2 * distance(layout, out, dock_cell)
        tasks.append(WarehouseTask(task_id=f"{order.order_id}-DISPATCH", kind="DISPATCH", sku=None,
                                   capability="loading", estimate_travel_m=travel,
                                   estimate_s=travel / v + timing["dispatch_handover_s"] + timing["dispatch_load_s"],
                                   dependencies=(f"{order.order_id}-PACK",), **common))
    return tasks, holds


def to_task_specs(tasks: list[WarehouseTask], cfg: dict[str, Any], *, done: frozenset[str] = frozenset()) -> tuple[TaskSpec, ...]:
    """SAMG tasks for every not-yet-done warehouse task; dependencies on done tasks are dropped."""
    weights = cfg["samg"]["priority_weight"]
    out = []
    for t in tasks:
        if t.task_id in done:
            continue
        out.append(TaskSpec(
            task_id=t.task_id, name=f"{t.order_id} {t.label}", required_capabilities=[t.capability],
            duration_ms=round(t.estimate_s * MS), resource_demand=1.0, priority_weight=float(weights[t.priority]),
            dependencies=[d for d in t.dependencies if d not in done],
        ))
    return tuple(out)
