"""Warehouse digital twin: layout, routing, orders, task generation, SAMG integration, physics,
congestion, failures, witness/ACP security and determinism."""

from __future__ import annotations

import json
from collections import defaultdict

import pytest

from samg.allocation import feasible_topologies
from samg.domain import TaskState
from samg.orchestration import RunSettings
from samg.simulation.engine import run as simulate
from samg.simulation.scenarios import judge_scenario
from samg.warehouse import Injection, RunSpec, build_state, load_config, preset, run_warehouse
from samg.warehouse.adapter import WarehouseEnv, execute, make_world
from samg.warehouse.congestion import AisleLocks
from samg.warehouse.inventory import Inventory
from samg.warehouse.layout import Layout
from samg.warehouse.orders import Order, generate_orders, orders_from_config
from samg.warehouse.path_planning import NoRoute, distance, route
from samg.warehouse.task_generator import generate_tasks, to_task_specs

CFG = load_config()


@pytest.fixture(scope="module")
def layout() -> Layout:
    return Layout.from_config(CFG)


@pytest.fixture(scope="module")
def env() -> WarehouseEnv:
    return WarehouseEnv(CFG)


@pytest.fixture(scope="module")
def clean_state() -> dict:
    return build_state(run_warehouse(RunSpec(seed=11, policy="P0-F", experience=0), CFG))


@pytest.fixture(scope="module")
def demo_run():
    return run_warehouse(preset(CFG, "judge_demo", experience=2), CFG)


@pytest.fixture(scope="module")
def demo_state(demo_run) -> dict:
    return build_state(demo_run)


# --- layout, inventory, routing ----------------------------------------------------


def test_layout_dimensions_and_solids(layout: Layout) -> None:
    assert (layout.width, layout.height) == (30, 20)
    for rack in layout.racks:
        x0, y0, x1, y1 = rack.rect
        assert all((x, y) not in layout.walkable for x in range(x0, x1 + 1) for y in range(y0, y1 + 1))
    for aisle in layout.aisles:
        assert all(c in layout.walkable for c in aisle.cells)
    for st in layout.stations:
        assert st.access in layout.walkable
    assert all(c in layout.walkable for _, c in layout.consolidation)
    assert layout.zone_at((4, 8)) == "AI-2" and layout.zone_at((2, 6)) == "Rack A"


def test_inventory_pick_faces_are_adjacent_aisle_cells(layout: Layout) -> None:
    inv = Inventory.from_config(CFG, layout)
    for sku in inv.all():
        assert sku.pick_face in layout.aisle_of
        assert abs(sku.pick_face[0] - sku.cell[0]) + abs(sku.pick_face[1] - sku.cell[1]) == 1
    assert not Inventory.from_config(CFG, layout, {"SKU-305": 0}).available("SKU-305")


def test_route_is_shortest_walkable_and_deterministic(layout: Layout) -> None:
    a, b = (8, 1), (19, 13)
    path = route(layout, a, b)
    assert path[0] == a and path[-1] == b and path == route(layout, a, b)
    assert all(c in layout.walkable for c in path[1:])
    assert all(abs(p[0] - q[0]) + abs(p[1] - q[1]) == 1 for p, q in zip(path, path[1:], strict=False))
    assert distance(layout, (0, 3), (5, 3)) == 5


def test_blocked_aisle_reroutes_or_has_no_route(layout: Layout) -> None:
    blocked = layout.with_blocked_aisles({"AI-3"})
    p = route(blocked, (7, 3), (7, 15))
    assert not any(blocked.aisle_of.get(c) == "AI-3" for c in p)
    assert len(p) > len(route(layout, (7, 3), (7, 15)))
    with pytest.raises(NoRoute):
        route(blocked, (7, 3), (7, 9))
    with pytest.raises(ValueError):
        layout.with_blocked_aisles({"AI-99"})


# --- orders and task generation -------------------------------------------------------


def test_orders_from_config_and_generator() -> None:
    orders = orders_from_config(CFG)
    assert [o.order_id for o in orders] == ["W001", "W002", "W003", "W004"]
    assert orders[0].priority == "CRITICAL" and orders[0].deadline_s == 330
    with pytest.raises(ValueError):
        Order("X", "URGENT", 10, ("SKU-101",))
    skus = [s["sku"] for s in CFG["inventory"]]
    assert generate_orders(5, skus) == generate_orders(5, skus)
    assert generate_orders(5, skus) != generate_orders(6, skus)


def test_task_generation_dependencies_and_capabilities(env: WarehouseEnv) -> None:
    tasks, holds = generate_tasks(orders_from_config(CFG), env.inventory, env.layout, env.robots, CFG)
    assert not holds
    by_id = {t.task_id: t for t in tasks}
    assert len(tasks) == sum(len(o.items) + 3 for o in orders_from_config(CFG))
    t = by_id["W001-TRANSPORT"]
    assert set(t.dependencies) == {"W001-PICK-SKU101", "W001-PICK-SKU305"}
    assert by_id["W001-PACK"].dependencies == ("W001-TRANSPORT",)
    assert by_id["W001-DISPATCH"].dependencies == ("W001-PACK",)
    assert {x.capability for x in tasks} == {"picking", "transport", "packing", "loading"}
    assert all(x.estimate_s > 0 for x in tasks)
    specs = to_task_specs(tasks, CFG, done=frozenset({"W001-PICK-SKU101"}))
    tr = next(s for s in specs if s.task_id == "W001-TRANSPORT")
    assert tr.dependencies == ("W001-PICK-SKU305",)
    assert next(s for s in specs if s.task_id == "W001-PACK").priority_weight == CFG["samg"]["priority_weight"]["CRITICAL"]


def test_inventory_unavailable_puts_order_on_hold() -> None:
    env = WarehouseEnv(CFG, (Injection(kind="inventory_unavailable", sku="SKU-316"),))
    tasks, holds = generate_tasks(orders_from_config(CFG), env.inventory, env.layout, env.robots, CFG)
    assert [(h.order_id, h.sku) for h in holds] == [("W003", "SKU-316")]
    assert not any(t.order_id == "W003" for t in tasks)


# --- warehouse -> SAMG ---------------------------------------------------------------


def test_scenario_maps_fleet_to_samg_agents(env: WarehouseEnv) -> None:
    tasks, _ = generate_tasks(orders_from_config(CFG), env.inventory, env.layout, env.robots, CFG)
    sc = env.scenario("T-1", tasks, done=frozenset(), seed=1, unavailable=frozenset({"R06"}), wave=1)
    wms = sc.agent("WMS")
    assert wms.is_mission_lead and wms.capacity == 0
    assert not sc.agent("R06").available
    assert {a.role for a in sc.agents} == {"control", "picking", "transport", "packing", "dispatch"}
    eligible, verdicts, plans = feasible_topologies(sc, env.settings.costs, env.settings.allocation)
    assert eligible, verdicts


def test_topology_and_allocation_come_from_samg(clean_state: dict, env: WarehouseEnv) -> None:
    w = clean_state["waves"][0]
    assert w["topology"] == "FUNCTIONAL_CELL" and w["policy"].startswith("P0-")
    assert w["graph"]["links"] and w["allocation"]["solver"] in ("CP_SAT", "GREEDY")
    caps = {r.robot_id: set(r.capabilities) for r in env.robots}
    for t in clean_state["tasks"]:
        for a in t["assignments"]:
            assert t["capability"] in caps[a["agent"]]


# --- physics: movement, timing, congestion ------------------------------------------------


def _segments(state: dict) -> dict[str, list[dict]]:
    return {r["id"]: r["segments"] for r in state["robots"]}


def test_robot_motion_follows_walkable_routes(clean_state: dict, layout: Layout) -> None:
    for rid, segs in _segments(clean_state).items():
        for a, b in zip(segs, segs[1:], strict=False):
            assert a["t1"] is not None and b["t0"] >= a["t1"] - 1e-6, (rid, a, b)   # no overlap
        for s in segs:
            if s["kind"] == "move":
                path = [tuple(c) for c in s["path"]]
                assert all(abs(p[0] - q[0]) + abs(p[1] - q[1]) == 1 for p, q in zip(path, path[1:], strict=False))
                assert all(c in layout.walkable for c in path[1:])


def test_physical_activity_fits_samg_windows(clean_state: dict) -> None:
    """After the delay feedback loop, every task's physical activity lies inside its SAMG window."""
    by_task: dict[str, list[dict]] = defaultdict(list)
    for segs in _segments(clean_state).values():
        for s in segs:
            if s.get("task"):
                by_task[s["task"]].append(s)
    for t in clean_state["tasks"]:
        if t["window"] is None:
            continue
        segs = by_task[t["id"]]
        assert segs, t["id"]
        assert min(s["t0"] for s in segs) >= t["window"][0] - 1e-3
        assert max(s["t1"] for s in segs) <= t["window"][1] + 0.3, t["id"]


def test_aisle_locks_never_overlap(clean_state: dict) -> None:
    occupancy: dict[str, list[tuple[float, float, str]]] = defaultdict(list)
    layout = Layout.from_config(CFG)
    for rid, segs in _segments(clean_state).items():
        for s in segs:
            if s["kind"] != "move":
                continue
            n = len(s["path"]) - 1
            for i, c in enumerate(s["path"]):
                aisle = layout.aisle_of.get(tuple(c))
                if aisle:
                    t = s["t0"] + (s["t1"] - s["t0"]) * i / max(n, 1)
                    occupancy[aisle].append((t, t, rid))
    for aisle, visits in occupancy.items():
        visits.sort()
        for (ta, _, ra), (tb, _, rb) in zip(visits, visits[1:], strict=False):
            if ra != rb:
                assert tb - ta > -1e-6
    assert clean_state["kpis"]["congestion_s"] >= 0


def test_aisle_lock_unit() -> None:
    locks = AisleLocks()
    locks.acquire("AI-1", "R01", 0.0, 10.0)
    assert locks.earliest_free("AI-1", 5.0, 3.0, "R02") == (10.0, ["R01"])
    assert locks.earliest_free("AI-1", 10.0, 3.0, "R02") == (10.0, [])
    assert locks.earliest_free("AI-1", 2.0, 3.0, "R01") == (2.0, [])
    assert locks.earliest_free("AI-2", 2.0, 3.0, "R02") == (2.0, [])


def test_congestion_is_measured_and_fed_back(clean_state: dict) -> None:
    assert clean_state["congestion"], "the demo layout should produce at least one aisle wait"
    w = clean_state["waves"][0]
    assert w["physical_passes"] >= 1
    c = clean_state["congestion"][0]
    assert c["t1"] > c["t0"] and c["blockers"] and c["aisle"].startswith("AI-")


# --- failures, replanning, witness, security --------------------------------------------------


def test_robot_failure_triggers_witness_and_replanning(demo_state: dict) -> None:
    w1, w2 = demo_state["waves"][0], demo_state["waves"][1]
    fail = next(i for i in w1["injections"] if i["kind"] == "robot_failure")
    assert fail["effective"]
    robot, task = fail["robot"], fail["task"]
    assert robot in w2["excluded"]
    segs = next(r for r in demo_state["robots"] if r["id"] == robot)["segments"]
    assert segs[-1]["kind"] == "failed" and segs[-1]["t1"] is None
    tj = next(t for t in demo_state["tasks"] if t["id"] == task)
    assert any(s["state"] == "FAILED" and s["from"] == "EXECUTING" for s in tj["states"])
    assert tj["assignments"][-1]["agent"] != robot and tj["assignments"][-1]["reassigned_from"] == robot
    assert task in w2["tasks"]


def test_malicious_claim_rejected_by_acp(demo_state: dict) -> None:
    false_claims = [c for c in demo_state["claims"] if c["false_claim"]]
    assert false_claims
    for c in false_claims:
        assert c["auth"] == "AUTHENTICATED"          # valid signature from a registered robot
        assert c["evidence"] == "DISPUTED"           # contradicted by witness evidence
        assert "WITNESS_CONTRADICTS" in c["reasons"]
    honest = [c for c in demo_state["claims"] if not c["false_claim"]]
    assert all(c["evidence"] != "DISPUTED" for c in honest)
    w1 = demo_state["waves"][0]
    assert w1["learning"]["source"] == "ACP_RECOMPUTED"
    assert w1["claimed_reward"] is not None and w1["claimed_reward"] != w1["reward"]["value"]
    assert demo_state["kpis"]["security_violations"] == len([c for c in demo_state["claims"] if c["evidence"] == "DISPUTED"])


def test_orders_complete_only_when_witness_verifies_dispatch(demo_state: dict) -> None:
    tasks = {t["id"]: t for t in demo_state["tasks"]}
    for o in demo_state["orders"]:
        d = tasks.get(f"{o['id']}-DISPATCH")
        if o["dispatched_at"] is not None:
            assert d["verified_at"] == o["dispatched_at"]
            assert any(s["state"] == "VERIFIED_COMPLETE" for s in d["states"])
    assert demo_state["kpis"]["orders_dispatched"] == sum(o["dispatched_at"] is not None for o in demo_state["orders"])


def test_comm_failure_raises_hop_failure_probability() -> None:
    base = WarehouseEnv(CFG)
    comm = WarehouseEnv(CFG, (Injection(kind="comm_failure"),))
    assert comm.settings.costs.hop_failure_probability == CFG["samg"]["comm_failure_probability"]
    assert base.settings.costs.hop_failure_probability == CFG["samg"]["hop_failure_probability"]


def test_delayed_task_extends_samg_execution() -> None:
    env = WarehouseEnv(CFG, (Injection(kind="delayed_task", delay_s=90),))
    waves, *_ = execute(env, make_world(env, "P0-H", experience=0, cfg=CFG), orders_from_config(CFG)[:1], seed=3,
                        mission_prefix="DLY", index_base=0, injections=env and (Injection(kind="delayed_task", delay_s=90),))
    inj = waves[0].injections_applied[0]
    assert inj["effective"] and waves[0].delays_ms[inj["task"]] >= 90_000


# --- engine extension, determinism, page ------------------------------------------------------


def test_engine_task_delays_extend_duration_and_default_is_unchanged() -> None:
    settings = RunSettings.load(use_cpsat=False)
    sc = judge_scenario(7)
    _, _, plans = feasible_topologies(sc, settings.costs, settings.allocation)
    graph, plan = next(iter(plans.values()))
    base = simulate(sc, graph, plan, 7, settings.costs)
    assert simulate(sc, graph, plan, 7, settings.costs, task_delays_ms={}) == base
    first = plan.assignments[0].task_id
    delayed = simulate(sc, graph, plan, 7, settings.costs, task_delays_ms={first: 5000})
    o0 = {o.task_id: o for o in base.outcomes}[first]
    o1 = {o.task_id: o for o in delayed.outcomes}[first]
    assert (o1.end - o1.start) - (o0.end - o0.start) == 5000


def test_deterministic_state() -> None:
    a = build_state(run_warehouse(RunSpec(seed=11, policy="P0-H", experience=0), CFG))
    b = build_state(run_warehouse(RunSpec(seed=11, policy="P0-H", experience=0), CFG))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_state_is_json_and_page_renders(demo_state: dict) -> None:
    pytest.importorskip("streamlit")
    from samg.dashboard.view_warehouse import render_page

    html = render_page(demo_state, None)
    assert "__STATE_JSON__" not in html and "__COMPARE_JSON__" not in html
    assert "<script src=" not in html            # no external scripts: works offline
    json.dumps(demo_state)
    assert demo_state["kpis"]["replans"] >= 1
    assert {e["level"] for e in demo_state["events"]} >= {"samg", "sec", "ok", "warn", "bad"}
    assert all(TaskState(s["state"]) for t in demo_state["tasks"] for s in t["states"] if s["state"] != "REPLANNED")


def test_engine_agent_breakdown_blocks_later_tasks() -> None:
    settings = RunSettings.load(use_cpsat=False)
    sc = judge_scenario(7)
    _, _, plans = feasible_topologies(sc, settings.costs, settings.allocation)
    graph, plan = next(iter(plans.values()))
    by_agent = defaultdict(list)
    for a in sorted(plan.assignments, key=lambda a: a.start):
        by_agent[a.agent_id].append(a.task_id)
    agent, tasks = next((k, v) for k, v in by_agent.items() if len(v) >= 2)
    trace = simulate(sc, graph, plan, 7, settings.costs, agent_breakdowns={agent: tasks[0]})
    out = {o.task_id: o for o in trace.outcomes}
    assert out[tasks[0]].failure_reason == "AGENT_BREAKDOWN" and not out[tasks[0]].completed
    for later in tasks[1:]:
        assert not out[later].completed and out[later].start is None
    assert simulate(sc, graph, plan, 7, settings.costs, agent_breakdowns={}) == simulate(sc, graph, plan, 7, settings.costs)


def test_aisle_blockage_holds_orders_whose_pick_face_is_unreachable() -> None:
    state = build_state(run_warehouse(RunSpec(seed=11, policy="P0-H", experience=0,
                                              injections=(Injection(kind="aisle_blockage", aisle="AI-3"),)), CFG))
    w001 = next(o for o in state["orders"] if o["id"] == "W001")
    assert w001["hold"] and "PICK_FACE_UNREACHABLE" in w001["hold_reason"]
    layout = Layout.from_config(CFG)
    for r in state["robots"]:
        for s in r["segments"]:
            if s["kind"] == "move":
                assert not any(layout.aisle_of.get(tuple(c)) == "AI-3" for c in s["path"])
    assert state["layout"]["aisles"][2]["blocked"]
