"""Integration Test for End-to-End Warehouse Digital Twin Pipeline."""

from samg.domain import TopologyName
from samg.warehouse.adapter import WarehouseSimulationRunner
from samg.warehouse.orders import OrderStatus
from samg.warehouse.scenarios import scenario_standard


def test_standard_warehouse_mission_end_to_end() -> None:
    runner = WarehouseSimulationRunner()
    orders = scenario_standard()

    final_state, rec, steps = runner.run_mission(
        orders,
        seed=7,
        policy_name="linucb",
        mode="adaptive",
        use_cpsat=True,
    )

    # 1. Verify SAMG decision
    assert rec.decision.topology in (
        TopologyName.HIERARCHICAL,
        TopologyName.FUNCTIONAL_CELL,
        TopologyName.DISTRIBUTED,
    )
    assert rec.plan is not None
    assert rec.plan.feasible

    # 2. Verify physical warehouse state
    assert final_state.status == "COMPLETED"
    assert len(steps) > 1
    assert final_state.kpis.order_completion_rate > 0
    assert final_state.kpis.reward > 0

    # 3. Verify event timeline recorded chronological steps
    assert len(final_state.event_timeline) >= 3
    cats = {e["category"] for e in final_state.event_timeline}
    assert "MISSION" in cats
    assert "COORDINATION" in cats
    assert "ALLOCATION" in cats

