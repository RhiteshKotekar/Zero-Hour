"""Warehouse Autonomous Mobile Robots (AMRs) and SAMG Agent Mapping."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import yaml

from samg.domain import AgentProfile


class RobotStatus(str, Enum):
    IDLE = "IDLE"
    MOVING = "MOVING"
    PICKING = "PICKING"
    TRANSPORTING = "TRANSPORTING"
    PACKING = "PACKING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CHARGING = "CHARGING"
    COMPLETED = "COMPLETED"


@dataclass
class WarehouseRobot:
    robot_id: str
    samg_agent_id: str
    name: str
    role: str
    capabilities: tuple[str, ...]
    capacity: int
    resource_budget: float
    home_position: tuple[int, int]
    current_position: tuple[int, int]
    destination: tuple[int, int] | None = None
    route: list[tuple[int, int]] = field(default_factory=list)
    status: RobotStatus = RobotStatus.IDLE
    battery: float = 100.0
    carrying_load_kg: float = 0.0
    assigned_task_id: str | None = None
    current_order_id: str | None = None
    can_coordinate: bool = False
    is_mission_lead: bool = False
    color: str = "#3498DB"
    speed: float = 1.0  # cells per second
    total_travel_distance: float = 0.0
    wait_time_s: float = 0.0

    def to_agent_profile(self) -> AgentProfile:
        """Convert to canonical immutable SAMG AgentProfile."""
        return AgentProfile(
            agent_id=self.samg_agent_id,
            role=self.role,
            capabilities=self.capabilities,
            capacity=self.capacity,
            resource_budget=self.resource_budget,
            can_coordinate=self.can_coordinate,
            is_mission_lead=self.is_mission_lead,
            available=(self.status != RobotStatus.FAILED),
            public_key_id=f"{self.samg_agent_id}#key0",
        )

    def set_position(self, pos: tuple[int, int]) -> None:
        if self.current_position != pos:
            dx = abs(pos[0] - self.current_position[0])
            dy = abs(pos[1] - self.current_position[1])
            self.total_travel_distance += dx + dy
            # Battery consumption: 0.1% per cell travelled
            self.battery = max(0.0, self.battery - 0.1 * (dx + dy))
            self.current_position = pos

    @classmethod
    def load_fleet(cls, config_path: str | Path | None = None) -> dict[str, WarehouseRobot]:
        if config_path is None:
            config_path = Path(__file__).resolve().parents[3] / "config" / "warehouse.yaml"
        else:
            config_path = Path(config_path)

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        fleet: dict[str, WarehouseRobot] = {}
        for r_cfg in cfg.get("robots", []):
            home = (r_cfg["home"][0], r_cfg["home"][1])
            robot = cls(
                robot_id=r_cfg["id"],
                samg_agent_id=r_cfg.get("samg_agent_id", r_cfg["id"]),
                name=r_cfg.get("name", r_cfg["id"]),
                role=r_cfg.get("role", "transport"),
                capabilities=tuple(r_cfg.get("capabilities", ["transport"])),
                capacity=r_cfg.get("capacity", 3),
                resource_budget=float(r_cfg.get("budget", 10.0)),
                home_position=home,
                current_position=home,
                speed=float(r_cfg.get("speed", 1.0)),
                battery=float(r_cfg.get("battery", 100.0)),
                can_coordinate=bool(r_cfg.get("can_coordinate", False)),
                is_mission_lead=bool(r_cfg.get("is_mission_lead", False)),
                color=r_cfg.get("color", "#3498DB"),
            )
            fleet[robot.robot_id] = robot
        return fleet

