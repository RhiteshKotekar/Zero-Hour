"""Converts Warehouse Customer Orders into SAMG MissionSpec, TaskSpecs and Scenarios."""

from __future__ import annotations

from typing import Sequence
from samg.domain import (
    AgentProfile,
    CapabilityMatch,
    MissionSpec,
    Scenario,
    TaskSpec,
)
from samg.warehouse.agents import WarehouseRobot
from samg.warehouse.orders import OrderPriority, WarehouseOrder


def orders_to_samg_mission(
    orders: Sequence[WarehouseOrder],
    *,
    mission_id: str = "M-warehouse-001",
    scenario_id: str = "wh-fulfillment-v1",
    deadline_ms: float = 300_000.0,  # 5 simulated minutes
) -> MissionSpec:
    """Translate warehouse customer orders into an executable SAMG DAG MissionSpec.

    Preserves strict operational dependencies:
      [PICK Items] -> [TRANSPORT to Pack Station] -> [PACK / VERIFY] -> [DISPATCH]
    """
    tasks: list[TaskSpec] = []
    task_counter = 1

    for order in orders:
        order_tasks: list[str] = []
        pick_task_ids: list[str] = []

        # 1. Picking tasks for each line item
        for idx, item in enumerate(order.items, start=1):
            t_id = f"T{task_counter}"
            task_counter += 1
            pick_task_ids.append(t_id)
            order_tasks.append(t_id)

            # Different SKU categories map to required capabilities
            caps = ("inspection",)
            if "Diagnostic" in item.name or "Sensor" in item.name:
                caps = ("diagnostics",)
            elif "Motor" in item.name or "Gearbox" in item.name:
                caps = ("survey",)

            tasks.append(
                TaskSpec(
                    task_id=t_id,
                    name=f"PICK {item.sku} ({item.rack_id})",
                    required_capabilities=caps,
                    capability_match=CapabilityMatch.ANY,
                    duration_ms=25_000.0,  # 25 seconds
                    resource_demand=1.5,
                    priority_weight=order.priority.weight,
                    mandatory=True,
                    reward_critical=True,
                    dependencies=(),
                )
            )

        # 2. Transport task: picks -> transport to packing station
        transport_id = f"T{task_counter}"
        task_counter += 1
        order_tasks.append(transport_id)
        tasks.append(
            TaskSpec(
                task_id=transport_id,
                name=f"TRANSPORT {order.order_id} -> {order.pack_station_id}",
                required_capabilities=("transport",),
                capability_match=CapabilityMatch.ANY,
                duration_ms=35_000.0,  # 35 seconds
                resource_demand=3.0,
                priority_weight=order.priority.weight,
                mandatory=True,
                reward_critical=True,
                dependencies=tuple(pick_task_ids),
            )
        )

        # 3. Packing & verification task
        pack_id = f"T{task_counter}"
        task_counter += 1
        order_tasks.append(pack_id)
        tasks.append(
            TaskSpec(
                task_id=pack_id,
                name=f"PACK & VERIFY {order.order_id}",
                required_capabilities=("verification",),
                capability_match=CapabilityMatch.ANY,
                duration_ms=20_000.0,
                resource_demand=2.0,
                priority_weight=order.priority.weight,
                mandatory=True,
                reward_critical=True,
                dependencies=(transport_id,),
            )
        )

        # 4. Dispatch task to loading bay
        dispatch_id = f"T{task_counter}"
        task_counter += 1
        order_tasks.append(dispatch_id)
        tasks.append(
            TaskSpec(
                task_id=dispatch_id,
                name=f"DISPATCH {order.order_id} to Bay",
                required_capabilities=("transport",),
                capability_match=CapabilityMatch.ANY,
                duration_ms=25_000.0,
                resource_demand=2.5,
                priority_weight=order.priority.weight,
                mandatory=True,
                reward_critical=True,
                dependencies=(pack_id,),
            )
        )

        order.task_ids = order_tasks

    return MissionSpec(
        mission_id=mission_id,
        scenario_id=scenario_id,
        tasks=tuple(tasks),
        deadline_ms=deadline_ms,
        family="warehouse_fulfillment",
    )


def create_warehouse_scenario(
    orders: Sequence[WarehouseOrder],
    robots: Sequence[WarehouseRobot],
    *,
    seed: int = 7,
    scenario_id: str = "wh-scenario-001",
    mission_id: str = "M-warehouse-001",
    deadline_ms: float = 300_000.0,
) -> Scenario:
    """Create a fully typed, valid SAMG Scenario from warehouse entities."""
    mission = orders_to_samg_mission(
        orders,
        mission_id=mission_id,
        scenario_id=scenario_id,
        deadline_ms=deadline_ms,
    )
    agent_profiles = tuple(r.to_agent_profile() for r in robots)
    return Scenario(
        scenario_id=scenario_id,
        seed=seed,
        mission=mission,
        agents=agent_profiles,
        permitted_links=None,  # All physical wireless links permissible
    )

