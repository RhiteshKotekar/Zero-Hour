"""Customer orders: the deterministic order book and a seeded generator for training."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

PRIORITIES = ("CRITICAL", "HIGH", "NORMAL", "LOW")


def clock_to_s(clock: str) -> int:
    h, m, s = (int(x) for x in clock.split(":"))
    return h * 3600 + m * 60 + s


def s_to_clock(start_clock: str, t: float) -> str:
    total = clock_to_s(start_clock) + int(t)
    return f"{total // 3600 % 24:02d}:{total // 60 % 60:02d}:{total % 60:02d}"


@dataclass(frozen=True)
class Order:
    order_id: str
    priority: str
    deadline_s: float          # seconds after simulated t = 0
    items: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.priority not in PRIORITIES:
            raise ValueError(f"unknown priority {self.priority}")
        if not self.items:
            raise ValueError(f"order {self.order_id} has no items")
        if len(set(self.items)) != len(self.items):
            raise ValueError(f"order {self.order_id} lists an SKU twice")

    def to_json(self, start_clock: str) -> dict[str, Any]:
        return {"id": self.order_id, "priority": self.priority, "deadline_s": self.deadline_s,
                "deadline": s_to_clock(start_clock, self.deadline_s), "items": list(self.items)}


def orders_from_config(cfg: dict[str, Any]) -> list[Order]:
    start = clock_to_s(cfg["start_clock"])
    return [Order(o["id"], o["priority"], float(clock_to_s(o["deadline"]) - start), tuple(o["items"]))
            for o in cfg["orders"]]


def generate_orders(seed: int, skus: list[str], *, n_min: int = 2, n_max: int = 5,
                    items_max: int = 3, prefix: str = "G") -> list[Order]:
    """Seeded order book for learner warm-up and evaluation streams (never the demo book)."""
    rng = np.random.default_rng(seed)
    n = int(rng.integers(n_min, n_max + 1))
    orders = []
    for i in range(n):
        k = int(rng.integers(1, items_max + 1))
        items = tuple(str(s) for s in rng.choice(sorted(skus), size=k, replace=False))
        priority = PRIORITIES[int(rng.integers(0, len(PRIORITIES)))]
        deadline = float(240 + 60 * int(rng.integers(0, 6)))
        orders.append(Order(f"{prefix}{seed % 1000:03d}-{i + 1}", priority, deadline, items))
    return orders
