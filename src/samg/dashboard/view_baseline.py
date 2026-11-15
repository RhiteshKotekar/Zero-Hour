"""SAMG vs conventional baseline (D042): AGGREGATE view over saved multi-seed results.

Reads ``artifacts/experiments/baseline/<run>/results.json`` written by
``python -m samg.experiments.compare``. Shows only measured values; with no saved run it says so
and shows the command instead of placeholder numbers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from samg.experiments.compare import METRICS, OUT_DIR
from samg.experiments.scenarios import RUNGS, SCENARIOS

CHART_METRICS = {
    "truly_fulfilled_rate": "Orders truly fulfilled (share)",
    "avg_fulfilment_s": "Average fulfilment (s)",
    "avg_task_latency_s": "Average task latency (s)",
    "makespan_s": "Makespan (s)",
    "robot_utilization": "Robot utilization",
    "congestion_s": "Congestion wait (s)",
    "retransmissions": "Message retransmissions",
    "task_failures": "Task failures",
    "corrupted_tasks": "Tasks believed done but not done",
    "false_claims_accepted": "False claims accepted",
    "orders_shipped_incomplete": "Orders shipped incomplete",
    "runtime_s": "Wall-clock per run (s)",
}
CAPABILITIES = pd.DataFrame(
    [
        ["Coordination", "Centralized greedy", "Centralized greedy", "SAMG pipeline, fixed star", "SAMG (adaptive)"],
        ["Topology selection", "No", "No", "No (fixed)", "LinUCB"],
        ["Allocator", "Greedy", "CP-SAT", "CP-SAT", "CP-SAT"],
        ["Witness / evidence gate", "No", "No", "Yes", "Yes"],
        ["Learning from outcomes", "No", "No", "No", "Yes (admitted only)"],
    ],
    columns=["", "B0 baseline", "B1 + CP-SAT", "B2 + witness", "SAMG"],
)


def saved_runs(root: Path | None = None) -> list[Path]:
    root = root or OUT_DIR
    if not root.exists():
        return []
    return sorted((p for p in root.iterdir() if (p / "results.json").exists()), key=lambda p: p.name, reverse=True)


def load_result(path: Path) -> dict[str, Any]:
    data = json.loads((path / "results.json").read_text(encoding="utf-8"))
    if not {"manifest", "rows", "summary"} <= set(data):
        raise ValueError(f"{path} is not a samg.experiments.compare result")
    return data


def summary_frame(result: dict[str, Any], scenario: str) -> pd.DataFrame:
    rungs = result["summary"][scenario]["rungs"]
    rows = []
    for metric in METRICS:
        row = {"metric": metric, "better": METRICS[metric] or "—"}
        for rung, stats in rungs.items():
            s = stats.get(metric) or {}
            row[rung] = None if s.get("mean") is None else round(s["mean"], 4)
        rows.append(row)
    return pd.DataFrame(rows)


def render() -> None:
    st.subheader("SAMG vs conventional baseline")
    st.caption("AGGREGATE · identical warehouse, orders, robots, seeds and faults; only the coordination "
               "architecture differs. The ladder separates the optimiser (B1), the witness/evidence gate (B2) and "
               "adaptive topology selection (SAMG). Measured values only.")
    st.table(CAPABILITIES.set_index(""))
    runs = saved_runs()
    if not runs:
        st.info("No saved comparison found. Run: `python -m samg.experiments.compare --all --n-seeds 30 "
                "--doc docs/RESULTS_BASELINE.md`")
        return
    choice = st.selectbox("Saved comparison", runs, format_func=lambda p: p.name)
    try:
        result = load_result(choice)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        st.error(f"Cannot load {choice}: {exc}")
        return
    man = result["manifest"]
    st.caption(f"Seeds {man['seeds'][0]}–{man['seeds'][-1]} (n = {len(man['seeds'])}) · commit "
               f"{(man.get('git_commit') or '?')[:8]} · model v2 + common random numbers · "
               f"{man['environment']['platform']}")
    scenarios = list(result["summary"])
    scenario = st.radio("Scenario", scenarios, horizontal=True,
                        format_func=lambda s: f"{s} · {SCENARIOS[s].title}" if s in SCENARIOS else s)
    st.write(SCENARIOS[scenario].description if scenario in SCENARIOS else "")

    rows = pd.DataFrame([r for r in result["rows"] if r["scenario"] == scenario])
    order = [r for r in RUNGS if r in set(rows["rung"])]
    metric = st.selectbox("Metric", list(CHART_METRICS), format_func=lambda m: CHART_METRICS[m])
    col1, col2 = st.columns(2)
    with col1:
        means = rows.groupby("rung", sort=False)[metric].mean().reindex(order).reset_index()
        st.plotly_chart(px.bar(means, x="rung", y=metric, title=f"Mean {CHART_METRICS[metric]}",
                               category_orders={"rung": order}), width="stretch")
    with col2:
        st.plotly_chart(px.box(rows, x="rung", y=metric, points="all", title="Per-seed distribution",
                               category_orders={"rung": order}), width="stretch")

    st.markdown("**Means by rung** (95% intervals and paired differences are in the results file and "
                "`docs/RESULTS_BASELINE.md`)")
    st.dataframe(summary_frame(result, scenario), hide_index=True, width="stretch")

    steps = result["summary"][scenario]["steps"]
    st.markdown("**What each mechanism changes** (paired per seed, first minus second)")
    st.dataframe(pd.DataFrame([
        {"step": f"{k} ({v['label']})", "metric": m, "mean diff": round(c["mean_diff"], 4),
         "95% CI": f"[{c['ci95_low']:+.4f}, {c['ci95_high']:+.4f}]" if c["ci95_low"] is not None else "—",
         "seeds higher/lower/tie": f"{c['wins']}/{c['losses']}/{c['ties']}"}
        for k, v in steps.items() for m, c in v["metrics"].items()
        if m in ("truly_fulfilled_rate", "avg_fulfilment_s", "corrupted_tasks", "runtime_s") and c["mean_diff"] is not None
    ]), hide_index=True, width="stretch")
