"""Warehouse robot fleet and its mapping to SAMG ``AgentProfile``s."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from samg.domain import AgentProfile
from samg.twin.layout import Cell, Layout


@dataclass(frozen=True)
class RobotSpec:
    robot_id: str
    role: str                       # fleet role = SAMG role = functional cell
    label: str
    capabilities: tuple[str, ...]
    capacity: int
    coordinator: bool
    lead: bool
    physical: bool                  # False for the WMS hub (software agent)
    home: Cell
    station: str | None             # stationary robots (pack arms) live on a station
    speed: float                    # cells (m) per simulated second; 0 = stationary
    battery: float

    @property
    def mobile(self) -> bool:
        return self.physical and self.speed > 0


def robots_from_config(cfg: dict[str, Any], layout: Layout) -> list[RobotSpec]:
    robots = []
    for r in cfg["robots"]:
        station = r.get("station")
        home = tuple(r["home"]) if "home" in r else layout.station(station).access
        robots.append(RobotSpec(
            robot_id=r["id"], role=r["role"], label=r.get("label", f"{r['role'].title()} robot {r['id']}"),
            capabilities=tuple(r["capabilities"]), capacity=int(r["capacity"]),
            coordinator=bool(r.get("coordinator", False)), lead=bool(r.get("lead", False)),
            physical=bool(r.get("physical", True)), home=home, station=station,
            speed=float(r.get("speed", 0.0)), battery=float(r.get("battery", 100.0)),
        ))
    return robots


def to_agent_profile(robot: RobotSpec, *, resource_budget: float, available: bool = True) -> AgentProfile:
    return AgentProfile(
        agent_id=robot.robot_id, role=robot.role, capabilities=list(robot.capabilities),
        capacity=robot.capacity, resource_budget=0.0 if robot.lead else resource_budget,
        can_coordinate=robot.coordinator, is_mission_lead=robot.lead, available=available,
        public_key_id=f"key-{robot.robot_id}",
    )
