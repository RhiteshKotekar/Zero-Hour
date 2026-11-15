"""Order sources for live sessions: where customer orders come from and when they arrive.

``OrderSource`` is the seam for a real order feed later: anything that can say which orders
arrive in a simulated-time interval. Two implementations exist:

* ``ConfigOrderSource``: the deterministic order book in ``config/twin.yaml``; each order may
  carry ``arrival: "HH:MM:SS"`` (default: ``start_clock``, i.e. t = 0).
* ``GeneratedOrderSource``: synthetic demand, ``generate_orders`` with a seed per batch at a
  fixed interval (deadlines relative to the arrival). Simulated, flagged as such in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol

from samg.twin.orders import Order, clock_to_s, generate_orders, orders_from_config


@dataclass(frozen=True)
class Arrival:
    """One order and the simulated second it arrives."""

    at_s: float
    order: Order


class OrderSource(Protocol):
    """Yields orders by simulated arrival time."""

    kind: str

    def arrivals(self, t0: float, t1: float) -> list[Arrival]:
        """Orders arriving in ``(t0, t1]`` (``t0 < 0`` includes t = 0), in arrival order."""
        ...

    def next_arrival(self, t: float) -> float | None:
        """Time of the first arrival strictly after ``t``, or ``None`` when exhausted."""
        ...


class _ScheduleSource:
    """Shared logic for a source backed by a precomputed, time-sorted schedule."""

    kind = "schedule"

    def __init__(self, schedule: list[Arrival]) -> None:
        self.schedule = sorted(schedule, key=lambda a: (a.at_s, a.order.order_id))

    def arrivals(self, t0: float, t1: float) -> list[Arrival]:
        return [a for a in self.schedule if t0 < a.at_s <= t1]

    def next_arrival(self, t: float) -> float | None:
        return next((a.at_s for a in self.schedule if a.at_s > t), None)


class ConfigOrderSource(_ScheduleSource):
    """The order book of ``config/twin.yaml`` with optional per-order ``arrival`` clock times."""

    kind = "config"

    def __init__(self, cfg: dict[str, Any]) -> None:
        start = clock_to_s(cfg["start_clock"])
        at = {o["id"]: float(max(clock_to_s(o["arrival"]) - start, 0)) if o.get("arrival") else 0.0
              for o in cfg["orders"]}
        super().__init__([Arrival(at[o.order_id], o) for o in orders_from_config(cfg)])


class GeneratedOrderSource(_ScheduleSource):
    """Seeded synthetic demand: batch ``k`` = ``generate_orders(seed + k)`` arriving at ``k * interval_s``."""

    kind = "generated"

    def __init__(self, skus: list[str], *, seed: int, interval_s: float, batches: int, prefix: str = "R") -> None:
        schedule = []
        for k in range(batches):
            at = float(k * interval_s)
            for o in generate_orders(seed + k, skus, n_min=1, n_max=3, prefix=prefix):
                schedule.append(Arrival(at, replace(o, deadline_s=o.deadline_s + at)))
        super().__init__(schedule)


def source_for(cfg: dict[str, Any], scenario: str, skus: list[str]) -> OrderSource:
    """The order source a scenario declares (``orders: {source: generated, ...}``), else the config book."""
    spec = cfg["scenarios"][scenario].get("orders") or {}
    if spec.get("source") == "generated":
        return GeneratedOrderSource(skus, seed=int(spec["seed"]), interval_s=float(spec["interval_s"]),
                                    batches=int(spec["batches"]))
    return ConfigOrderSource(cfg)
