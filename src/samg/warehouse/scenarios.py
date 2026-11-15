"""Preset Warehouse Scenarios for Judge Demonstrations and Experiments."""

from __future__ import annotations

from samg.warehouse.orders import OrderItem, OrderPriority, WarehouseOrder


def scenario_standard() -> list[WarehouseOrder]:
    """Standard warehouse fulfillment: 2 customer orders, 8 tasks."""
    return [
        WarehouseOrder(
            order_id="ORD-01",
            priority=OrderPriority.HIGH,
            items=[
                OrderItem("SKU-101", quantity=1, rack_id="RACK-A01", name="LiDAR Sensor Module"),
            ],
            deadline_s=240.0,
            pick_station_id="PICK-01",
            pack_station_id="PACK-01",
        ),
        WarehouseOrder(
            order_id="ORD-02",
            priority=OrderPriority.NORMAL,
            items=[
                OrderItem("SKU-205", quantity=1, rack_id="RACK-B03", name="Reinforced Chassis Arm"),
            ],
            deadline_s=300.0,
            pick_station_id="PICK-02",
            pack_station_id="PACK-02",
        ),
    ]


def scenario_high_demand() -> list[WarehouseOrder]:
    """High-demand fulfillment: 3 orders, 12 tasks across multiple aisles."""
    return [
        WarehouseOrder(
            order_id="ORD-H01",
            priority=OrderPriority.CRITICAL,
            items=[
                OrderItem("SKU-101", quantity=1, rack_id="RACK-A01", name="LiDAR Sensor Module"),
            ],
            deadline_s=180.0,
            pick_station_id="PICK-01",
            pack_station_id="PACK-01",
        ),
        WarehouseOrder(
            order_id="ORD-H02",
            priority=OrderPriority.HIGH,
            items=[
                OrderItem("SKU-105", quantity=1, rack_id="RACK-A03", name="High-Torque Drive Motor"),
            ],
            deadline_s=220.0,
            pick_station_id="PICK-02",
            pack_station_id="PACK-02",
        ),
        WarehouseOrder(
            order_id="ORD-H03",
            priority=OrderPriority.NORMAL,
            items=[
                OrderItem("SKU-201", quantity=1, rack_id="RACK-B01", name="Thermal Imaging Scanner"),
            ],
            deadline_s=280.0,
            pick_station_id="PICK-03",
            pack_station_id="PACK-03",
        ),
    ]


def scenario_congestion() -> list[WarehouseOrder]:
    """Congestion stress: Multiple orders targeting adjacent racks in narrow aisle B1."""
    return [
        WarehouseOrder(
            order_id="ORD-C01",
            priority=OrderPriority.CRITICAL,
            items=[
                OrderItem("SKU-201", quantity=1, rack_id="RACK-B01", name="Thermal Imaging Scanner"),
            ],
            deadline_s=200.0,
            pick_station_id="PICK-02",
            pack_station_id="PACK-02",
        ),
        WarehouseOrder(
            order_id="ORD-C02",
            priority=OrderPriority.HIGH,
            items=[
                OrderItem("SKU-203", quantity=1, rack_id="RACK-B02", name="Structural Fastener Set"),
            ],
            deadline_s=220.0,
            pick_station_id="PICK-02",
            pack_station_id="PACK-02",
        ),
    ]

