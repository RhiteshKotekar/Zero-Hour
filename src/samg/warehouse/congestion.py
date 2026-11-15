"""Warehouse Aisle Congestion, Conflict Detection and Delay Calculation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence
from samg.warehouse.agents import RobotStatus, WarehouseRobot
from samg.warehouse.layout import WarehouseLayout


@dataclass
class CongestionAlert:
    aisle: str
    location: tuple[int, int]
    robots: list[str]
    delay_s: float
    description: str


class CongestionManager:
    """Detects multi-robot spatial conflicts and aisle capacity bottlenecks."""

    def __init__(self, penalty_per_robot_s: float = 4.0) -> None:
        self.penalty_per_robot_s = penalty_per_robot_s
        self.active_alerts: list[CongestionAlert] = []
        self.total_congestion_delay_s: float = 0.0

    def evaluate_congestion(
        self,
        robots: Sequence[WarehouseRobot],
        layout: WarehouseLayout,
    ) -> list[CongestionAlert]:
        """Detect conflicts where multiple robots attempt to occupy the same cell or bottleneck aisle."""
        alerts: list[CongestionAlert] = []

        # 1. Direct cell collision/contention
        cell_occupants: dict[tuple[int, int], list[WarehouseRobot]] = {}
        for r in robots:
            if r.status in (RobotStatus.MOVING, RobotStatus.TRANSPORTING, RobotStatus.WAITING):
                cell_occupants.setdefault(r.current_position, []).append(r)

        for cell, occupants in cell_occupants.items():
            if len(occupants) > 1:
                # Cell contention: first robot proceeds, others wait
                r_ids = [r.robot_id for r in occupants]
                delay = (len(occupants) - 1) * self.penalty_per_robot_s
                alert = CongestionAlert(
                    aisle=f"Cell ({cell[0]},{cell[1]})",
                    location=cell,
                    robots=r_ids,
                    delay_s=delay,
                    description=f"{len(occupants)} AMRs contested cell ({cell[0]},{cell[1]}). Delayed +{delay:.1f}s",
                )
                alerts.append(alert)
                for r in occupants[1:]:
                    r.status = RobotStatus.WAITING
                    r.wait_time_s += delay
                self.total_congestion_delay_s += delay

        # 2. Designated bottleneck aisle occupancy
        for name, bn in layout.bottlenecks.items():
            bn_set = set(bn.cells)
            occupants = [r for r in robots if r.current_position in bn_set and r.status != RobotStatus.IDLE]
            if len(occupants) > bn.capacity:
                r_ids = [r.robot_id for r in occupants]
                excess = len(occupants) - bn.capacity
                delay = excess * self.penalty_per_robot_s
                alert = CongestionAlert(
                    aisle=name,
                    location=bn.cells[0],
                    robots=r_ids,
                    delay_s=delay,
                    description=f"Bottleneck {bn.label}: {len(occupants)} AMRs present (capacity {bn.capacity}). Delay +{delay:.1f}s",
                )
                alerts.append(alert)
                # Mark excess robots as waiting
                for r in occupants[bn.capacity:]:
                    r.status = RobotStatus.WAITING
                    r.wait_time_s += delay
                self.total_congestion_delay_s += delay

        self.active_alerts = alerts
        return alerts

