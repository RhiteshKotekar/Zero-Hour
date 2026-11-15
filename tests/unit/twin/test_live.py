"""Live session (Phase 1-A): engine ``agent_down_at_ms``, scripted demo, preview/commit determinism."""

from __future__ import annotations

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
