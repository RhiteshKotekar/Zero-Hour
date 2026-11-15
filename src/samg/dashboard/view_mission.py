"""View 1: Mission Control (brief §15.3). Display only; every value comes from orchestration records."""

from __future__ import annotations

import math
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from samg.dashboard import data
from samg.domain import CoordinationGraph, TopologyName

MIN = data.MIN


def badge(kind: str) -> None:
    """Panel provenance label: live / replayed / aggregate."""
    colours = {"LIVE": "green", "REPLAYED": "blue", "AGGREGATE": "violet", "SHADOW": "orange"}
    st.markdown(f":{colours.get(kind, 'gray')}-background[{kind}]")


def run_header(mission_id: str, config_id: str, seed: int, extra: str = "") -> None:
    st.info(f"**Mission ID** `{mission_id}`  ·  **Config ID** `{config_id}`  ·  **Seed** `{seed}`"
            + (f"  ·  {extra}" if extra else ""))


def graph_figure(graph: CoordinationGraph, title: str = "", agent_order: list[str] | None = None) -> go.Figure:
    """Agents on a fixed circle (same positions across topologies); COORDINATES_WITH links as edges."""
    agents = agent_order or graph.agent_ids()
    n = max(len(agents), 1)
    pos = {a: (math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i, a in enumerate(agents)}
    ex, ey = [], []
    for a, b in graph.coordination_links():
        if a in pos and b in pos:
            ex += [pos[a][0], pos[b][0], None]
            ey += [pos[a][1], pos[b][1], None]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line={"width": 1.5, "color": "#888"},
                             hoverinfo="skip", name="COORDINATES_WITH"))
    coords = set(graph.coordinators) | set(graph.cell_coordinators.values())
    cell_of = {m: c for c, members in graph.cells.items() for m in members}
    for is_coord, label, colour, size in ((False, "agent", "#4C78A8", 22), (True, "coordinator", "#E45756", 30)):
        sel = [a for a in agents if (a in coords) == is_coord and a in pos]
        fig.add_trace(go.Scatter(
            x=[pos[a][0] for a in sel], y=[pos[a][1] for a in sel], mode="markers+text", text=sel,
            textposition="top center", marker={"size": size, "color": colour, "line": {"width": 1, "color": "#222"}},
            hovertext=[f"{a}" + (f" (cell {cell_of[a]})" if a in cell_of else "") for a in sel],
            hoverinfo="text", name=label))
    fig.update_layout(title=title, height=380, margin={"l": 10, "r": 10, "t": 40, "b": 10},
                      xaxis={"visible": False, "range": [-1.4, 1.4]},
                      yaxis={"visible": False, "range": [-1.3, 1.4], "scaleanchor": "x"},
                      legend={"orientation": "h"})
    return fig


def gantt_figure(rows: list[dict[str, Any]]) -> go.Figure:
    fig = go.Figure()
    for kind, s, e, colour in (("planned", "planned start (min)", "planned end (min)", "#9ecae9"),
                               ("simulated", "actual start (min)", "actual end (min)", "#4C78A8")):
        ys, xs, bases, texts = [], [], [], []
        for r in rows:
            if r[s] is None or r[e] is None:
                continue
            ys.append(f"{r['task']} ({r['agent']})")
            bases.append(r[s])
            xs.append(max(r[e] - r[s], 0.01))
            texts.append(f"{kind}: {r[s]:.1f}-{r[e]:.1f} min")
        fig.add_trace(go.Bar(y=ys, x=xs, base=bases, orientation="h", name=kind, marker_color=colour,
                             hovertext=texts, hoverinfo="text"))
    failed = [r for r in rows if r["completed (ground truth)"] is False]
    if failed:
        fig.add_trace(go.Scatter(y=[f"{r['task']} ({r['agent']})" for r in failed],
                                 x=[r["planned start (min)"] for r in failed], mode="markers",
                                 marker={"symbol": "x", "size": 14, "color": "#E45756"}, name="not completed"))
    fig.update_layout(barmode="group", height=40 + 28 * max(len(rows), 1), xaxis_title="simulated minutes",
                      margin={"l": 10, "r": 10, "t": 20, "b": 30}, yaxis={"autorange": "reversed"})
    return fig


def _controls() -> dict[str, Any]:
    d = data.DEMO_DEFAULTS
    ss = st.session_state
    for key, val in d.items():
        ss.setdefault(f"mc_{key}", val)
    if st.button("Reset to saved demo configuration", key="mc_reset"):
        for key, val in d.items():
            ss[f"mc_{key}"] = val
        for f, v in d["factors"].items():
            ss[f"mc_factor_{f}"] = v
        ss.pop("mc_run", None)
        ss.pop("mc_cmp", None)
        st.rerun()
    c1, c2, c3, c4 = st.columns(4)
    seed = c1.number_input("Seed", min_value=0, max_value=10_000_000, step=1, key="mc_seed")
    kind = c2.radio("Scenario", ["judge", "generated"], key="mc_scenario_kind", horizontal=True)
    mode = c3.radio("Run mode", ["adaptive", "fixed"], key="mc_mode", horizontal=True,
                    help="Adaptive: the policy selects the topology. Fixed: operator picks one; LinUCB is not updated.")
    if mode == "adaptive":
        policy = c4.selectbox("Policy", ["linucb", "ucb1"], key="mc_policy")
        fixed = None
    else:
        policy = "fixed"
        fixed = TopologyName(c4.selectbox("Fixed topology", [t.value for t in TopologyName], key="mc_fixed_topology"))
    factors = None
    if kind == "generated":
        st.caption("Generation factors (reporting labels only; the policy sees the numeric context vector below)")
        cols = st.columns(len(data.FACTOR_CHOICES))
        factors = {}
        for col, (name, choices) in zip(cols, data.FACTOR_CHOICES.items(), strict=True):
            st.session_state.setdefault(f"mc_factor_{name}", d["factors"][name])
            factors[name] = col.selectbox(name, choices, key=f"mc_factor_{name}")
    with st.expander("Development settings (not the frozen experiment config)"):
        alpha = st.number_input("LinUCB alpha (demo setting)", min_value=0.0, max_value=5.0, step=0.1, key="mc_alpha")
        cpsat = st.checkbox("Use CP-SAT allocator (else greedy)", key="mc_use_cpsat")
    return {"seed": int(seed), "scenario_kind": kind, "factors": factors, "policy": policy, "mode": mode,
            "alpha": float(alpha), "use_cpsat": bool(cpsat), "fixed_topology": fixed}


def render() -> None:
    st.header("Mission Control")
    st.caption("One mission through `samg.orchestration.run_single_mission` (fresh protected world, in-memory "
               "SQLite). The UI only displays the returned `MissionRunRecord`.")
    params = _controls()
    if st.button("Run mission", type="primary", key="mc_go"):
        try:
            st.session_state["mc_run"] = data.run_mission(**params)
            st.session_state.pop("mc_cmp", None)
        except Exception as exc:  # shown explicitly, never swallowed
            st.session_state.pop("mc_run", None)
            st.error(f"Mission run failed: {type(exc).__name__}: {exc}")
    run: data.MissionRun | None = st.session_state.get("mc_run")
    if run is None:
        st.write("Press **Run mission** to execute one mission live.")
        return
    render_run(run)


def render_run(run: data.MissionRun) -> None:
    rec, sc, settings = run.record, run.scenario, run.settings
    badge("LIVE")
    run_header(rec.mission_id, run.config_id, rec.seed,
               f"scenario `{rec.scenario_id}` · policy `{rec.policy_kind}` ({run.label}) · mode `{rec.mode.value}`")
    st.caption("Config versions: " + ", ".join(f"{k}={v}" for k, v in data.config_versions(settings).items()))

    st.subheader("1. Context features passed to the policy")
    st.dataframe([rec.context.as_dict()], hide_index=True)
    with st.expander("Mission intake: agents and tasks"):
        st.dataframe([{"agent": a.agent_id, "role": a.role, "capabilities": "/".join(a.capabilities),
                       "capacity": a.capacity, "budget": a.resource_budget, "coordinator": a.can_coordinate,
                       "available": a.available} for a in sc.agents], hide_index=True)
        st.dataframe([{"task": t.task_id, "required": ",".join(t.required_capabilities),
                       "match": t.capability_match.value, "duration (min)": t.duration_ms / MIN,
                       "demand": t.resource_demand, "priority": t.priority_weight,
                       "depends on": ",".join(t.dependencies)} for t in sc.mission.tasks], hide_index=True)

    st.subheader("2. Topology eligibility (D030: buildable and allocatable)")
    st.dataframe(data.eligibility_rows(rec), hide_index=True)

    st.subheader("3. Policy decision")
    d = rec.decision
    st.dataframe(data.score_rows(rec), hide_index=True)
    how = "cold-start warm-up (seeded arm order)" if d.warmup else "argmax of score"
    if d.topology is None:
        st.error("No eligible topology: the mission was not run. Reasons: "
                 + ",".join(r.value for r in d.reason_codes))
        return
    st.success(f"Chosen topology: **{d.topology.value}** ({how}). Policy `{d.policy_kind}` {d.policy_version}. "
               + ("Score = mean + bonus as exposed by the policy." if d.bonuses else "Combined score only."))

    g, plan = rec.graph, rec.plan
    assert g is not None and plan is not None
    st.subheader("4. Coordination graph")
    gc1, gc2 = st.columns([3, 2])
    gc1.plotly_chart(graph_figure(g, f"{g.topology.value} (graph {g.graph_version[:12]})",
                                  [a.agent_id for a in sc.agents]), width="stretch", key="mc_graph")
    gc2.markdown(f"**Coordinators:** {', '.join(g.coordinators) or '-'}")
    if g.cells:
        gc2.markdown("**Cells:** " + "; ".join(f"{c}: {', '.join(m)} (lead {g.cell_coordinators.get(c, '-')})"
                                               for c, m in g.cells.items()))
    gc2.markdown(f"**Coordination links ({len(g.coordination_links())}):** "
                 + " ".join(f"`{a}-{b}`" for a, b in g.coordination_links()))

    st.subheader("5. Allocation and execution")
    st.write(f"Solver `{plan.solver.value}` status `{plan.solver_status}` feasible **{plan.feasible}**"
             + (" (fallback used)" if plan.fallback_used else ""))
    if not plan.feasible:
        st.error("Infeasible plan: " + ",".join(r.value for r in plan.reason_codes) + f" {plan.detail}")
    if plan.unassigned_tasks:
        st.warning("Unassigned tasks: " + ", ".join(plan.unassigned_tasks))
    rows = data.assignment_rows(rec, sc)
    st.dataframe(rows, hide_index=True)
    if rows:
        st.plotly_chart(gantt_figure(rows), width="stretch", key="mc_gantt")
    if plan.objective:
        ob = plan.objective
        st.caption(f"Allocator objective: makespan={ob.makespan:.2f} handoff_cost={ob.handoff_cost:.2f} "
                   f"resource_use={ob.resource_use:.2f} max_agent_load={ob.max_agent_load:.2f} "
                   f"unserved_priority={ob.unserved_priority:.2f} weighted_total={ob.weighted_total:.2f} "
                   f"weights={ob.weights}")

    st.subheader("6. Handoffs (graph-derived)")
    c = settings.costs
    st.latex(r"\text{cost} = \begin{cases}0 & \text{same agent}\\ h_0 + h_1\cdot\text{hops} & \text{otherwise}"
             r"\end{cases}\qquad \text{delay} = \text{hops}\cdot d_{hop}")
    st.write(f"h0 = **{c.h0}**, h1 = **{c.h1}**, d_hop = **{c.handoff_delay_ms_per_hop / MIN:.1f} min**, "
             f"link_cost = {c.link_cost}, max_path_hops = {c.max_path_hops}, span_overhead = {c.span_overhead}, "
             f"hop_failure_probability = {c.hop_failure_probability} (same rule for every topology)")
    st.dataframe(data.handoff_rows(rec), hide_index=True)

    if rec.trace is not None:
        m = rec.trace.metrics
        st.caption(f"Simulated execution (seed {rec.trace.seed}): {len(rec.trace.transitions)} transitions, "
                   f"makespan {m.makespan / MIN:.2f} min, retransmissions {m.communication_failures}")
        with st.expander("Task transition timeline (simulator)"):
            st.dataframe([{"t (min)": round(t.sim_time / MIN, 2), "task": t.task_id, "agent": t.agent_id,
                           "from": t.from_state.value, "to": t.to_state.value} for t in rec.trace.transitions],
                         hide_index=True)

    st.subheader("7. Evidence and episode decision (ACP)")
    st.write("validate_event: " + str(data.status_counts(rec.auth_decisions))
             + " · after corroboration: " + str(data.status_counts(rec.final_decisions)))
    with st.expander("Per-event validation trace", expanded=False):
        st.dataframe(data.event_rows(rec), hide_index=True)
    ep = rec.episode
    if ep is not None:
        msg = f"Episode **{ep.status.value}** reasons: {', '.join(r.value for r in ep.reason_codes) or '-'}"
        (st.success if ep.status.value == "ADMITTED" else st.warning)(msg)

    st.subheader("8. Reward breakdown (recomputed by the ACP from witness-verified outcomes)")
    rr = data.reward_rows(rec)
    if rr:
        st.latex(r"r = w_C\,C + w_T(1-T) + w_R(1-R) + w_H(1-H)")
        st.caption("Completion is rewarded; duration, resource use and coordination overhead are penalised "
                   "through 1 - normalised value (normalisation per D033).")
        st.dataframe(rr, hide_index=True)
        assert rec.acp_reward is not None
        st.metric("ACP reward r", f"{rec.acp_reward.reward:.4f}")
    else:
        st.warning("No ACP-recomputed reward (episode not admitted or plan infeasible).")
    gt = rec.ground_truth_reward
    if gt is not None:
        st.caption(f"Evaluation oracle (simulator ground truth, never learned directly): {gt.reward:.4f}"
                   + (f" · failure outcome {gt.failure_label}" if gt.failure_outcome else ""))
    if rec.claimed_reward is not None:
        st.caption(f"Last authenticated REWARD_CLAIM {rec.claimed_reward:.4f}: recorded for audit, not used "
                   "(protected mode).")

    st.subheader("9. Guarded policy update")
    le = rec.learning_event
    if le is None:
        st.write(f"No learning event ({rec.learning_rejection.value if rec.learning_rejection else '-'}).")
    elif rec.learning_applied:
        st.success(f"APPLIED: arm {le.topology.value} learned reward {le.reward:.4f} "
                   f"(source {le.reward_source.value}, episode {le.status.value})")
        b0, b1 = run.policy_before.get("b"), run.policy_after.get("b")
        if b0 and b1:
            st.write(f"b[{le.topology.value}]: {b0[le.topology.value]} → "
                     f"{[round(x, 4) for x in b1[le.topology.value]]}")
        elif rec.policy_kind.startswith("P0") or "Fixed" in rec.policy_kind:
            st.caption("Fixed-topology policy: observe() keeps no learnable state; LinUCB is not updated.")
    else:
        st.warning(f"REFUSED: {rec.learning_rejection.value if rec.learning_rejection else '-'}; "
                   "policy state unchanged.")

    _comparison(run)


def _comparison(run: data.MissionRun) -> None:
    with st.expander("Topology comparison: same mission and seed under every eligible topology"):
        st.markdown(":orange-background[SHADOW EVALUATION] Executed with `execute_mission` and no repository; "
                    "**never fed to the learner**.")
        if st.button("Run comparison", key="mc_cmp_go"):
            try:
                st.session_state["mc_cmp"] = data.compare_topologies(run.scenario, run.record.seed, run.settings)
            except Exception as exc:
                st.error(f"Comparison failed: {type(exc).__name__}: {exc}")
        cmp: data.TopologyComparison | None = st.session_state.get("mc_cmp")
        if cmp is None:
            return
        st.dataframe(data.comparison_rows(cmp), hide_index=True)
        order = [a.agent_id for a in run.scenario.agents]
        cols = st.columns(max(len(cmp.executions), 1))
        for col, (topo, ex) in zip(cols, cmp.executions.items(), strict=False):
            col.plotly_chart(graph_figure(ex.graph, topo.value, order), width="stretch",
                             key=f"cmp_graph_{topo.value}")
