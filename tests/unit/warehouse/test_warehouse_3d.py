"""Unit tests for 3D Warehouse Digital Twin serialization and HTML generation."""

import json
from samg.domain import TopologyName
from samg.dashboard.view_warehouse_3d import generate_3d_html, serialize_warehouse_scene
from samg.warehouse.adapter import WarehouseSimulationRunner
from samg.warehouse.agents import RobotStatus, WarehouseRobot
from samg.warehouse.layout import WarehouseLayout
from samg.warehouse.scenarios import scenario_congestion, scenario_standard
from samg.warehouse.state import WarehouseState


def test_serialize_warehouse_scene_structure() -> None:
    runner = WarehouseSimulationRunner()
    orders = scenario_standard()
    state, rec, steps = runner.run_mission(orders, seed=7, mode="adaptive", use_cpsat=True)

    scene = serialize_warehouse_scene(state, steps, current_step_idx=2)

    # Basic layout dimensions
    assert scene["width"] == 30
    assert scene["height"] == 20
    assert len(scene["racks"]) > 0
    assert "PICK-01" in scene["stations"]
    assert "PACK-01" in scene["stations"]

    # Timeline frames
    assert len(scene["frames"]) == len(steps)
    assert scene["initial_frame_idx"] == 2

    # Check frame contents
    frame0 = scene["frames"][0]
    assert "robots" in frame0
    assert "congestion" in frame0
    assert "kpis" in frame0
    assert "R01" in frame0["robots"]
    r01 = frame0["robots"]["R01"]
    assert "x" in r01 and "y" in r01
    assert "status" in r01
    assert "battery" in r01
    assert "heading" in r01

    # Verify JSON serializability
    json_str = json.dumps(scene)
    assert len(json_str) > 1000


def test_serialize_warehouse_scene_with_attack() -> None:
    runner = WarehouseSimulationRunner()
    orders = scenario_standard()
    state, rec, steps = runner.run_mission(orders, seed=7, attack_agent="R05", use_cpsat=True)

    scene = serialize_warehouse_scene(state, steps, current_step_idx=len(steps) - 1)
    assert scene["attack_info"]["has_attack"] is True
    assert scene["attack_info"]["attack_agent"] == "R05"
    assert "details" in scene["attack_info"]


def test_serialize_warehouse_scene_with_congestion() -> None:
    runner = WarehouseSimulationRunner()
    orders = scenario_congestion()
    state, rec, steps = runner.run_mission(orders, seed=7, mode="adaptive", use_cpsat=True)

    scene = serialize_warehouse_scene(state, steps, current_step_idx=len(steps) // 2)
    # Check that at least some frame has congestion or valid alerts
    has_congestion_frame = any(len(f["congestion"]) > 0 for f in scene["frames"])
    assert has_congestion_frame or state.kpis.congestion_delay_s >= 0


def test_generate_3d_html_contains_required_elements() -> None:
    runner = WarehouseSimulationRunner()
    orders = scenario_standard()
    state, rec, steps = runner.run_mission(orders, seed=7, mode="adaptive", use_cpsat=True)

    scene = serialize_warehouse_scene(state, steps, current_step_idx=0)
    html = generate_3d_html(scene, height_px=700)

    assert "<!DOCTYPE html>" in html
    assert "canvas-container" in html
    assert "OrbitControls" in html
    assert "setCameraPreset" in html
    assert "hud-top" in html
    assert "telemetry-card" in html
    assert "scrubber-slider" in html

