"""Tests for Warehouse Orders and SAMG Mission Conversion."""

from samg.domain import CapabilityMatch
from samg.warehouse.agents import WarehouseRobot
from samg.warehouse.orders import OrderItem, OrderPriority, WarehouseOrder
from samg.warehouse.task_generator import create_warehouse_scenario, orders_to_samg_mission


def test_order_creation_and_properties() -> None:
    order = WarehouseOrder(
        order_id="ORD-T01",
        priority=OrderPriority.HIGH,
        items=[OrderItem("SKU-101", 1, "RACK-A01", "Sensor")],
    )
    assert order.priority.weight == 2.0
    assert order.total_weight_kg > 0


def test_orders_to_samg_dag_conversion() -> None:
    orders = [
        WarehouseOrder(
            order_id="ORD-01",
            priority=OrderPriority.HIGH,
            items=[OrderItem("SKU-101", 1, "RACK-A01", "Sensor")],
        )
    ]
    mission = orders_to_samg_mission(orders)

    # 1 item -> 1 pick + 1 transport + 1 pack + 1 dispatch = 4 tasks
    assert len(mission.tasks) == 4
    # Check topological sort works without circular dependencies
    order_ids = mission.topological_order()
    assert len(order_ids) == 4

    # Verify dependency chain
    task_map = {t.task_id: t for t in mission.tasks}
    # Transport depends on pick
    assert "T1" in task_map["T2"].dependencies
    # Pack depends on transport
    assert "T2" in task_map["T3"].dependencies
    # Dispatch depends on pack
    assert "T3" in task_map["T4"].dependencies


def test_create_warehouse_scenario() -> None:
    fleet = list(WarehouseRobot.load_fleet().values())
    orders = [
        WarehouseOrder(
            order_id="ORD-01",
            priority=OrderPriority.NORMAL,
            items=[OrderItem("SKU-101", 1, "RACK-A01", "Sensor")],
        )
    ]
    scenario = create_warehouse_scenario(orders, fleet, seed=42)
    assert scenario.seed == 42
    assert len(scenario.agents) == len(fleet)
    assert len(scenario.mission.tasks) == 4

