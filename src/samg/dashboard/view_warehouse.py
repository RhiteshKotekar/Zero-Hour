"""View: Warehouse digital twin — SAMG operating inside a warehouse (owner: Dev B).

Streamlit only collects the run settings and triggers the backend
(``samg.warehouse.run_warehouse`` / ``compare_policies``). Every number, position and verdict
in the page comes from the returned ``WarehouseState``; the browser interpolates between
simulation ticks and never decides topology, allocation, rewards or security results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from samg.warehouse import INJECTION_KINDS, POLICY_KINDS, Injection, RunSpec, build_state, compare_policies, load_config, preset, run_warehouse
from samg.warehouse.layout import Layout

TEMPLATE = Path(__file__).parent / "static" / "warehouse.html"
HEIGHT = 2050


def render_page(state: dict[str, Any], comparison: dict[str, Any] | None = None) -> str:
    """Self-contained HTML page (no external scripts) for a ``WarehouseState``."""
    def payload(x: Any) -> str:
        return json.dumps(x, separators=(",", ":")).replace("</", "<\\/")
    return (TEMPLATE.read_text(encoding="utf-8").replace("__STATE_JSON__", payload(state))
            .replace("__COMPARE_JSON__", payload(comparison)))


def _spec_key(spec: RunSpec) -> str:
    return json.dumps({"seed": spec.seed, "policy": spec.policy, "experience": spec.experience,
                       "cpsat": spec.use_cpsat, "replan": spec.replan, "scenario": spec.scenario,
                       "inj": [vars(i) for i in spec.injections]}, sort_keys=True)


@st.cache_data(show_spinner=False, max_entries=24)
def _run_cached(key: str) -> dict[str, Any]:
    d = json.loads(key)
    cfg = load_config()
    label = cfg["scenarios"].get(d["scenario"], {}).get("label", "Custom scenario")
    spec = RunSpec(seed=d["seed"], policy=d["policy"], experience=d["experience"], use_cpsat=d["cpsat"],
                   replan=d["replan"], scenario=d["scenario"], label=label,
                   injections=tuple(Injection(**i) for i in d["inj"]))
    return build_state(run_warehouse(spec, cfg))


@st.cache_data(show_spinner=False, max_entries=4)
def _compare_cached(seeds: tuple[int, ...], use_cpsat: bool) -> dict[str, Any]:
    return compare_policies(load_config(), seeds=seeds, use_cpsat=use_cpsat)


def _custom_injections(cfg: dict[str, Any]) -> tuple[Injection, ...]:
    layout = Layout.from_config(cfg)
    robots = [r["id"] for r in cfg["robots"] if r.get("physical", True)]
    skus = [s["sku"] for s in cfg["inventory"]]
    chosen = st.multiselect("Failure injection", list(INJECTION_KINDS), format_func=INJECTION_KINDS.get,
                            key="wh_inj", placeholder="none: clean operations")
    out = []
    cols = st.columns(max(len(chosen), 1))
    for col, kind in zip(cols, chosen, strict=False):
        with col:
            if kind in ("robot_failure", "malicious_report"):
                opts = ["auto:TRANSPORT", "auto:PICK"] + robots
                default = "auto:TRANSPORT" if kind == "robot_failure" else "auto:PICK"
                r = st.selectbox(f"{INJECTION_KINDS[kind]}: robot", opts, index=opts.index(default), key=f"wh_{kind}_r",
                                 help="auto:KIND = the robot SAMG assigns the earliest task of that kind")
                out.append(Injection(kind=kind, robot=r))
            elif kind == "aisle_blockage":
                a = st.selectbox("Blocked aisle", [a.aisle_id for a in layout.aisles], index=2, key="wh_aisle")
                out.append(Injection(kind=kind, aisle=a))
            elif kind == "inventory_unavailable":
                s = st.selectbox("Out-of-stock SKU", skus, index=skus.index("SKU-316") if "SKU-316" in skus else 0,
                                 key="wh_sku")
                out.append(Injection(kind=kind, sku=s))
            elif kind == "delayed_task":
                d = st.number_input("Delay (s) on the first PACK task", 10, 300, 60, 10, key="wh_delay")
                out.append(Injection(kind=kind, delay_s=float(d)))
            else:
                st.caption(f"{INJECTION_KINDS[kind]}: per-hop message failure probability → "
                           f"{cfg['samg']['comm_failure_probability']}")
                out.append(Injection(kind=kind))
    return tuple(out)


def render() -> None:
    cfg = load_config()
    ss = st.session_state
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([2.2, 2.2, 1, 1.6, 1.2])
        scenario = c1.radio("Scenario", ["judge_demo", "clean", "custom"], horizontal=True, key="wh_scn",
                            format_func={"judge_demo": "Judge demo", "clean": "Clean operations",
                                         "custom": "Custom"}.get)
        policy = c2.selectbox("Coordination policy", list(POLICY_KINDS), format_func=POLICY_KINDS.get, key="wh_pol")
        seed = int(c3.number_input("Seed", 0, 99999, int(cfg["scenarios"]["judge_demo"]["seed"]), key="wh_seed"))
        experience = int(c4.select_slider("Learner experience (missions)", [0, 4, 8, 12, 20],
                                          value=int(cfg["learning"]["experience"]), key="wh_exp",
                                          disabled=policy not in ("adaptive", "ucb1")))
        use_cpsat = c5.toggle("CP-SAT", value=True, key="wh_cpsat", help="off = deterministic greedy allocator")
        if scenario == "custom":
            injections = _custom_injections(cfg)
        else:
            injections = preset(cfg, scenario).injections
            st.caption("Injections: " + ("; ".join(i.describe() for i in injections) or "none"))
        b1, b2, b3 = st.columns([1.3, 1.6, 4])
        go = b1.button("Run simulation", type="primary", key="wh_go")
        cmp_go = b2.button("Run topology comparison", key="wh_cmp",
                           help="Same orders, layout, fleet and seeds under P0-H, P0-F, P0-D and adaptive LinUCB")
        b3.caption("SAMG runs once per click (cached); the page then replays the recorded run. "
                   "Use ▶ Start or ◉ Auto demo inside the control room.")

    spec = RunSpec(seed=seed, policy=policy, experience=experience, use_cpsat=use_cpsat, scenario=scenario,
                   injections=injections)
    key = _spec_key(spec)
    if go or "wh_state_key" not in ss:
        try:
            with st.spinner("SAMG is planning the warehouse mission (topology, CP-SAT, execution, witness, ACP)…"):
                _run_cached(key)
            ss["wh_state_key"] = key
        except Exception as exc:  # shown, never swallowed
            st.error(f"Warehouse run failed: {type(exc).__name__}: {exc}")
            return
    if cmp_go:
        seeds = tuple(int(s) for s in cfg["learning"]["comparison_seeds"])
        with st.spinner(f"Running {4 * len(seeds)} warehouse missions for the comparison…"):
            ss["wh_cmp_result"] = _compare_cached(seeds, use_cpsat)
    state = _run_cached(ss["wh_state_key"])
    if ss["wh_state_key"] != key:
        st.info("Settings changed: press **Run simulation** to apply them. Showing the previous run.")
    st.iframe(render_page(state, ss.get("wh_cmp_result")), height=HEIGHT)
