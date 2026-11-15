"""Normalized Warehouse State representation for the Digital Twin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from samg.domain import AllocationPlan, CoordinationGraph, ExecutionTrace, TopologyName
from samg.warehouse.agents import WarehouseRobot
from samg.warehouse.congestion import CongestionAlert
from samg.warehouse.layout import WarehouseLayout
from samg.warehouse.orders import WarehouseOrder


@dataclass
class WarehouseKPIs:
    order_completion_rate: float = 0.0
    avg_fulfilment_time_s: float = 0.0
    avg_task_latency_s: float = 0.0
    robot_utilization: float = 0.0
    total_travel_distance: float = 0.0
    congestion_delay_s: float = 0.0
    failed_tasks: int = 0
    security_violations: int = 0
    reward: float = 0.0


@dataclass
class WarehouseState:
    simulation_time_s: float = 0.0
    layout: WarehouseLayout = field(default_factory=WarehouseLayout)
    robots: dict[str, WarehouseRobot] = field(default_factory=dict)
    orders: dict[str, WarehouseOrder] = field(default_factory=dict)
    active_mission_id: str = "M-warehouse-001"
    current_topology: TopologyName | None = None
    policy_kind: str = "P3-LinUCB"
    context_features: dict[str, float] = field(default_factory=dict)
    policy_scores: dict[str, float] = field(default_factory=dict)
    graph: CoordinationGraph | None = None
    allocation_plan: AllocationPlan | None = None
    execution_trace: ExecutionTrace | None = None
    congestion_alerts: list[CongestionAlert] = field(default_factory=list)
    security_events: list[dict[str, Any]] = field(default_factory=list)
    kpis: WarehouseKPIs = field(default_factory=WarehouseKPIs)
    event_timeline: list[dict[str, Any]] = field(default_factory=list)
    status: str = "RUNNING"  # "IDLE", "RUNNING", "PAUSED", "COMPLETED"

    def add_event(self, timestamp_s: float, category: str, message: str, level: str = "INFO") -> None:
        self.event_timeline.append({
            "time_s": round(timestamp_s, 1),
            "category": category,
            "message": message,
            "level": level,
        })

