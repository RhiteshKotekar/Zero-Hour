"""Live session (Phase 1-A): engine ``agent_down_at_ms``, scripted demo, preview/commit determinism."""

from __future__ import annotations

import copy
import json

from samg.allocation import feasible_topologies
from samg.domain import TaskState
from samg.simulation.engine import run as simulate
from samg.twin import load_config
from samg.twin.adapter import WarehouseEnv
from samg.twin.live import LiveSession
from samg.twin.orders import orders_from_config
from samg.twin.task_generator import generate_tasks

CFG = load_config()


def test_engine_agent_down_at_ms() -> None:
    env = WarehouseEnv(CFG)
    tasks, _ = generate_tasks(orders_from_config(CFG), env.inventory, env.layout, env.robots, CFG)
    scenario = env.scenario("T-1", tasks, done=frozenset(), seed=3, unavailable=frozenset(), wave=1)
    eligible, _, plans = feasible_topologies(scenario, env.settings.costs, env.settings.allocation)
    graph, plan = plans[eligible[0]]
    base = simulate(scenario, graph, plan, 3, env.settings.costs)
    assert simulate(scenario, graph, plan, 3, env.settings.costs, agent_down_at_ms={}) == base
    # the agent with the most tasks goes down in the middle of its first one
    agent = max({a.agent_id for a in plan.assignments}, key=lambda r: sum(a.agent_id == r for a in plan.assignments))
    first = min((o for o in base.outcomes if o.agent_id == agent and o.start is not None), key=lambda o: o.start)
    down = (first.start + first.end) / 2
    trace = simulate(scenario, graph, plan, 3, env.settings.costs, agent_down_at_ms={agent: down})
    out = {o.task_id: o for o in trace.outcomes}
    assert out[first.task_id].failure_reason == "AGENT_BREAKDOWN" and out[first.task_id].end == round(down)
    later = [o for o in base.outcomes if o.agent_id == agent and o.task_id != first.task_id]
    assert later and all(not out[o.task_id].completed for o in later)
    before = [tr for tr in base.transitions if tr.sim_time < round(down)]
    assert [tr for tr in trace.transitions if tr.sim_time < round(down)] == before


def test_judge_demo_script_runs_live() -> None:
    s = LiveSession("judge_demo", experience=2)
    while not s.complete and s.t < 2000:
        s.advance(10)
    st = s.state()
    assert s.complete and all(w["status"] == "committed" for w in st["waves"])
    assert [i["kind"] for i in st["live"]["injections"]] == ["malicious_report", "robot_failure"]
    assert all(step["fired"] for step in st["live"]["script"])
    assert st["kpis"]["security_violations"] > 0                        # ACP disputed the false claims
    failed = [r["id"] for r in st["robots"] if r["failed_at"] is not None]
    assert failed and set(failed) <= set(st["waves"][-1]["excluded"])   # replanned without the failed robot
    assert not any("differs" in n["text"] for n in s.drain_notices())   # every commit == its preview
    assert st["witness_events"] and {"t", "task", "from", "to", "wave"} <= set(st["witness_events"][0])
    hand = [h for w in st["waves"] for h in w["allocation"]["handoffs"] if h["depart_s"] is not None]
    assert hand and all(h["arrive_s"] > h["depart_s"] for h in hand)
    assert next(o for o in st["orders"] if o["id"] == "W004")["arrival_s"] == 45


def test_live_session_is_deterministic_and_injections_keep_the_past() -> None:
    def play() -> dict:
        s = LiveSession("clean", policy="P0-F", script=[])
        s.advance(30)
        before = [x for x in s.state()["tasks"] if x["states"] and x["states"][-1]["t"] <= 30]
        res = s.inject("delayed_task", task="auto", delay_s=20)
        assert res["accepted"] and res["wave"] == 1
        after = {x["id"]: x for x in s.state()["tasks"]}
        for x in before:   # history up to t is unchanged by the re-run
            assert [h for h in after[x["id"]]["states"] if h["t"] <= 30] == [h for h in x["states"] if h["t"] <= 30]
        assert s.inject("aisle_blockage", aisle="AI-3")["accepted"]
        assert not s.inject("robot_failure", robot="NOPE")["accepted"]
        while not s.complete and s.t < 2000:
            s.advance(15)
        st = s.state()
        st.pop("live")
        return st

    a, b = play(), play()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["kpis"]["orders_dispatched"] == len(a["orders"])
    assert any(t["states"] and t["states"][-1]["state"] == TaskState.VERIFIED_COMPLETE.value for t in a["tasks"])


def test_operator_topology_override_forces_every_wave_and_never_trains_the_learner() -> None:
    s = LiveSession("clean", script=[], topology="FUNCTIONAL_CELL")
    before = s.world.policy.snapshot()
    while not s.complete and s.t < 3000:
        s.advance(20)
    st = s.state()
    assert s.complete and st["waves"]
    assert all(w["topology"] == "FUNCTIONAL_CELL" and w["policy"] == "P0-OPERATOR" for w in st["waves"])
    assert all(w["status"] == "committed" for w in st["waves"])
    assert s.world.policy.snapshot() == before                       # operator decisions are not learned from
    assert st["live"]["forced_topology"] == "FUNCTIONAL_CELL"
    assert not any("differs" in n["text"] for n in s.drain_notices())  # commit == preview


def test_operator_topology_override_mid_session_applies_from_the_next_wave() -> None:
    s = LiveSession("judge_demo", experience=2)
    s.advance(30)
    first = s.state()["waves"][0]["topology"]
    target = "FUNCTIONAL_CELL" if first != "FUNCTIONAL_CELL" else "HIERARCHICAL"
    r = s.set_topology(target)
    assert r["topology"] == target and r["applies_from_wave"] == 2
    assert s.state()["waves"][0]["topology"] == first                # the executing wave keeps its plan
    while not s.complete and s.t < 3000:
        s.advance(20)
    later = s.state()["waves"][1:]
    assert later and all(w["topology"] == target and w["policy"] == "P0-OPERATOR" for w in later)
    assert s.set_topology("auto")["topology"] is None and s.state()["live"]["forced_topology"] is None


def test_operator_topology_override_rejects_unknown_and_falls_back_when_infeasible() -> None:
    s = LiveSession("clean", script=[])
    try:
        s.set_topology("STAR")
    except ValueError as e:
        assert "unknown topology" in str(e)
    else:
        raise AssertionError("unknown topology accepted")
    # an override the wave cannot plan (here: DISTRIBUTED with the core degree cap of 3) falls back and says so
    cfg = copy.deepcopy(CFG)
    cfg["samg"]["distributed_max_degree"] = 3
    f = LiveSession("clean", script=[], topology="DISTRIBUTED", cfg=cfg)
    assert f.state()["waves"][0]["topology"] in ("HIERARCHICAL", "FUNCTIONAL_CELL")
    assert any("not feasible" in n["text"] for n in f.drain_notices())


def test_distributed_is_eligible_for_the_twin_fleet_and_survives_a_robot_loss() -> None:
    s = LiveSession("judge_demo", experience=2, topology="DISTRIBUTED")
    while not s.complete and s.t < 3000:
        s.advance(20)
    st = s.state()
    assert s.complete and [w["topology"] for w in st["waves"]] == ["DISTRIBUTED"] * len(st["waves"])
    assert len(st["waves"]) >= 2                                      # incl. the re-plan after the robot failure
    assert not any("not feasible" in n["text"] or "differs" in n["text"] for n in s.drain_notices())


# --- traffic: collision-free motion, failure signal and alternative paths ------------------------------


def _positions(state: dict, t: float) -> dict[str, tuple[float, float]]:
    """Every mobile robot's interpolated position at ``t`` (as the 3D view draws it)."""
    out = {}
    for r in state["robots"]:
        if not r["mobile"]:
            continue
        cur = None
        for sg in r["segments"]:
            if sg["t0"] <= t:
                cur = sg
            else:
                break
        if cur is None:
            continue
        if cur["kind"] == "move" and cur.get("path") and cur["t1"] is not None and t < cur["t1"]:
            p, n = cur["path"], len(cur["path"]) - 1
            x = (t - cur["t0"]) / max(cur["t1"] - cur["t0"], 1e-9) * n
            i = min(int(x), n - 1)
            f = x - i
            out[r["id"]] = (p[i][0] + (p[i + 1][0] - p[i][0]) * f, p[i][1] + (p[i + 1][1] - p[i][1]) * f)
        elif cur["kind"] == "move" and cur.get("path"):
            out[r["id"]] = tuple(cur["path"][-1])
        else:
            out[r["id"]] = tuple(cur["cell"])
    return out


def _min_gap(state: dict, dt: float = 0.1) -> tuple[float, float, tuple[str, str] | None]:
    best, when, pair = float("inf"), 0.0, None
    t = 0.0
    while t <= state["end_s"]:
        pos = sorted(_positions(state, t).items())
        for i, (a, pa) in enumerate(pos):
            for b, pb in pos[i + 1:]:
                d = ((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2) ** 0.5
                if d < best:
                    best, when, pair = d, t, (a, b)
        t += dt
    return best, when, pair


def _play(s: LiveSession) -> dict:
    while not s.complete and s.t < 5000:
        s.advance(20)
    return s.state()


def test_robots_never_overlap_in_any_live_scenario() -> None:
    for scenario in ("clean", "judge_demo", "aisle_failure"):
        s = LiveSession(scenario)
        st = _play(s)
        gap, when, pair = _min_gap(st)
        assert gap >= 0.8 - 1e-6, (scenario, gap, when, pair)      # always at least ~one cell apart
        assert s.locks.traffic.fallbacks == 0, scenario               # every plan was conflict-free
        assert st["kpis"]["order_completion_rate"] == 1.0, scenario


def test_robot_failing_in_an_aisle_blocks_it_and_others_take_an_alternative_path() -> None:
    s = LiveSession("aisle_failure")
    st = _play(s)
    inj = st["live"]["injections"]
    assert inj and inj[0]["kind"] == "robot_failure"
    signal = [e for e in st["events"] if e["title"].startswith("Failure signal")]
    rerouted = [e for e in st["events"] if " rerouted around " in e["title"] or " routes around failed " in e["title"]]
    assert signal and rerouted and signal[0]["aisle"].startswith("AI-")
    failed = inj[0]["target"]
    assert all(e["robot"] != failed for e in rerouted)
    assert any(c[1] == failed for c in s.locks.traffic.blocked.values())   # its cell is a permanent obstacle


def test_auto_aisle_is_rejected_when_no_robot_is_inside_an_aisle() -> None:
    s = LiveSession("clean", script=[])
    res = s.inject("robot_failure", robot="auto:AISLE")      # t = 0: nobody has reached an aisle yet
    assert not res["accepted"] and "aisle" in res["effect"]


def test_topology_can_be_switched_between_waves_of_a_continuous_session() -> None:
    s = LiveSession("continuous")
    switches = [(150, "FUNCTIONAL_CELL"), (500, "DISTRIBUTED")]
    while not s.complete and s.t < 5000:
        if switches and s.t >= switches[0][0]:
            s.set_topology(switches.pop(0)[1])
        s.advance(10)
    topo = [w["topology"] for w in s.state()["waves"]]
    assert len(topo) >= 4 and "FUNCTIONAL_CELL" in topo and "DISTRIBUTED" in topo
