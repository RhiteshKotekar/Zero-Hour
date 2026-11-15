"""Tests for Warehouse Failure Injection and ACP Malicious Report Quarantining."""

from samg.domain import EpisodeStatus
from samg.warehouse.adapter import WarehouseSimulationRunner
from samg.warehouse.orders import OrderItem, OrderPriority, WarehouseOrder


def test_malicious_robot_attack_quarantined_by_acp() -> None:
    runner = WarehouseSimulationRunner()
    orders = [
        WarehouseOrder(
            order_id="ORD-SEC01",
            priority=OrderPriority.HIGH,
            items=[OrderItem("SKU-101", 1, "RACK-A01", "Sensor")],
        )
    ]

    # Compromise robot R05 (mapped to A4 in SAMG)
    final_state, rec, steps = runner.run_mission(
        orders,
        seed=7,
        attack_agent="R05",
        use_cpsat=True,
    )

    assert rec.attacked
    assert len(rec.false_claim_event_ids) > 0
    # Physical witness contradicts the falsified claim
    assert rec.episode is not None
    assert rec.episode.status is EpisodeStatus.ADMITTED

    # Security event must be recorded in final_state
    assert len(final_state.security_events) > 0
    ev = final_state.security_events[0]
    assert ev["signature"].startswith("VALID")
    assert "DISPUTED" in ev["acp_verdict"]
    assert "BLOCKED" in ev["policy_update"]


def test_forced_failure_simulation() -> None:
    runner = WarehouseSimulationRunner()
    orders = [
        WarehouseOrder(
            order_id="ORD-FAIL01",
            priority=OrderPriority.NORMAL,
            items=[OrderItem("SKU-101", 1, "RACK-A01", "Sensor")],
        )
    ]

    # Force failure on task T1
    final_state, rec, steps = runner.run_mission(
        orders,
        seed=7,
        forced_failure_task="T1",
        use_cpsat=True,
    )

    assert rec.trace is not None
    # Ground truth FAILED task must be recorded
    failed = [o for o in rec.trace.outcomes if o.failure_reason is not None]
    assert len(failed) > 0
    assert failed[0].task_id == "T1"

