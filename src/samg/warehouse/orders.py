"""Warehouse Customer Orders and Lifecycle Tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence
from samg.warehouse.inventory import SKUItem


class OrderPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"

    @property
    def weight(self) -> float:
        weights = {
            OrderPriority.CRITICAL: 3.0,
            OrderPriority.HIGH: 2.0,
            OrderPriority.NORMAL: 1.0,
            OrderPriority.LOW: 0.5,
        }
        return weights[self]


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    ALLOCATED = "ALLOCATED"
    IN_PROGRESS = "IN_PROGRESS"
    FULFILLED = "FULFILLED"
    DELAYED = "DELAYED"
    FAILED = "FAILED"


@dataclass
class OrderItem:
    sku: str
    quantity: int = 1
    rack_id: str = "RACK-A01"
    name: str = ""


@dataclass
class WarehouseOrder:
    order_id: str
    priority: OrderPriority
    items: list[OrderItem]
    created_at_s: float = 0.0
    deadline_s: float = 300.0  # seconds
    pick_station_id: str = "PICK-01"
    pack_station_id: str = "PACK-01"
    status: OrderStatus = OrderStatus.PENDING
    assigned_robots: list[str] = field(default_factory=list)
    completion_time_s: float | None = None
    task_ids: list[str] = field(default_factory=list)

    @property
    def total_weight_kg(self) -> float:
        # 2 kg default per item if unspecified
        return float(len(self.items) * 2.0)

