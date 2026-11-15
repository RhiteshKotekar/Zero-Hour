"""Tests for Aisle Congestion, Conflict Detection, and Delay Penalties."""

from samg.warehouse.agents import RobotStatus, WarehouseRobot
from samg.warehouse.congestion import CongestionManager
from samg.warehouse.layout import WarehouseLayout


def test_cell_contention_detection() -> None:
    layout = WarehouseLayout.from_yaml()
    mgr = CongestionManager(penalty_per_robot_s=5.0)

    # Place two active robots in the exact same cell
    r1 = WarehouseRobot(
        robot_id="R01", samg_agent_id="A0", name="R1", role="transport", capabilities=("transport",),
        capacity=1, resource_budget=5.0, home_position=(0, 0), current_position=(5, 5), status=RobotStatus.MOVING
    )
    r2 = WarehouseRobot(
        robot_id="R02", samg_agent_id="A1", name="R2", role="transport", capabilities=("transport",),
        capacity=1, resource_budget=5.0, home_position=(0, 0), current_position=(5, 5), status=RobotStatus.MOVING
    )

    alerts = mgr.evaluate_congestion([r1, r2], layout)
    assert len(alerts) >= 1
    assert alerts[0].delay_s == 5.0
    assert "R01" in alerts[0].robots and "R02" in alerts[0].robots
    # Second robot should have been put into WAITING status
    assert r2.status == RobotStatus.WAITING
    assert r2.wait_time_s == 5.0


def test_bottleneck_capacity_overflow() -> None:
    layout = WarehouseLayout.from_yaml()
    mgr = CongestionManager(penalty_per_robot_s=3.0)

    # Aisle B1 bottleneck capacity is 1
    cell_in_b1 = (9, 13)
    r1 = WarehouseRobot(
        robot_id="R01", samg_agent_id="A0", name="R1", role="transport", capabilities=("transport",),
        capacity=1, resource_budget=5.0, home_position=(0, 0), current_position=cell_in_b1, status=RobotStatus.MOVING
    )
    r2 = WarehouseRobot(
        robot_id="R02", samg_agent_id="A1", name="R2", role="transport", capabilities=("transport",),
        capacity=1, resource_budget=5.0, home_position=(0, 0), current_position=cell_in_b1, status=RobotStatus.MOVING
    )

    alerts = mgr.evaluate_congestion([r1, r2], layout)
    assert any("B1" in a.aisle or "Cell" in a.aisle for a in alerts)
    assert mgr.total_congestion_delay_s > 0

