"""View 2: Adaptive Evaluation Lab (brief §15.4). Loads saved ``ExperimentResult`` JSON; never invents numbers."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from samg.dashboard import data
from samg.dashboard.view_mission import badge


def _learning_curve(result: Any) -> go.Figure:
    fig = go.Figure()
    for name, rewards in result.training_rewards.items():
        xs = [i for i, r in enumerate(rewards) if r is not None]
        ys = [r for r in rewards if r is not None]
        # cumulative mean of measured rewards: a display transform of the saved series
        cum, total = [], 0.0
        for k, y in enumerate(ys, start=1):
            total += y
            cum.append(total / k)
        fig.add_trace(go.Scatter(x=xs, y=cum, mode="lines", name=name))
    fig.update_layout(height=360, xaxis_title="training mission", yaxis_title="running mean ground-truth reward",
                      margin={"l": 10, "r": 10, "t": 20, "b": 30})
    return fig


def _selection_by_family(result: Any) -> list[dict[str, Any]]:
    rows = []
    for name, pr in result.test.items():
        for fam, counts in pr.selection_by_family.items():
            rows.append({"policy": name, "family": fam, **counts})
    return rows


def _held_out_rows(result: Any) -> list[dict[str, Any]]:
    by: dict[tuple[str, bool], list[float]] = defaultdict(list)
    for r in result.records:
        if r.split == "test" and r.reward is not None:
            by[(r.policy, r.held_out_combo)].append(r.reward)
    return [{"policy": p, "held-out factor combo": h, "n": len(v), "mean reward": sum(v) / len(v)}
            for (p, h), v in sorted(by.items())]


def render_result(result: Any, label: str, source: str) -> None:
    badge(label)
    cfg = result.config
    st.info(f"**Config ID (hash)** `{result.config_hash}` · experiment `{cfg.version}` · master seed "
            f"`{cfg.master_seed}` · n_train={cfg.n_train} n_test={cfg.n_test} holdout={cfg.holdout_fraction} "
            f"frozen={cfg.frozen} · source: {source}")
    st.caption(f"P1 (best fixed) chosen on training data only: **{result.p1_topology.value}**. "
               f"Learner updates: {result.learner_updates} · blocked: {result.blocked_updates}")
    st.subheader("Held-out test: policies")
    st.caption("Variation: std = sample standard deviation; CI = 95% bootstrap confidence interval of the mean "
               f"(bootstrap seed {cfg.bootstrap_seed}). Regret = simulator-oracle regret vs best fixed arm.")
    st.dataframe(data.policy_rows(result), hide_index=True)
    st.subheader("Paired comparisons (same missions and seeds)")
    st.dataframe([c.model_dump() for c in result.comparisons], hide_index=True)
    st.subheader("Learning curve (training)")
    st.plotly_chart(_learning_curve(result), width="stretch", key=f"lc_{label}")
    st.subheader("Selection frequency by family (test)")
    st.dataframe(_selection_by_family(result), hide_index=True)
    st.subheader("Seen vs held-out factor combinations (test)")
    st.dataframe(_held_out_rows(result), hide_index=True)
    with st.expander("Experiment config"):
        st.json(cfg.model_dump(mode="json"))


def render() -> None:
    st.header("Adaptive Evaluation Lab")
    files = data.saved_files("experiment_a*.json") + data.saved_files("experiment_ab*.json")
    files = sorted(set(files))
    if not files:
        st.warning(f"No saved run found in `{data.ARTIFACTS}` — run `scripts/run_experiment_a.py` to produce "
                   "`artifacts/experiments/experiment_a*.json` (an `ExperimentResult.model_dump_json()` file). "
                   "No numbers are shown until a real run exists.")
    else:
        choice = st.selectbox("Saved experiment", [f.name for f in files], key="ev_file")
        path = Path(data.ARTIFACTS) / choice
        try:
            render_result(data.load_experiment_result(path), "AGGREGATE", f"saved file {choice}")
        except Exception as exc:
            st.error(f"Could not load {choice}: {type(exc).__name__}: {exc}")

    st.divider()
    st.subheader("Development mode")
    st.markdown(":red-background[DEVELOPMENT MODE] A tiny live Experiment A/B (6 train, 4 test missions, greedy "
                "allocator). It is **not** the frozen held-out evaluation and must not be presented as one.")
    _, source = data.find_executor()
    st.caption(f"Executor: `{source}`")
    if st.button("Run small live experiment (development mode)", key="ev_dev"):
        with st.spinner("running..."):
            try:
                st.session_state["ev_dev_result"] = data.run_dev_experiment()
            except Exception as exc:
                st.error(f"Development run failed: {type(exc).__name__}: {exc}")
    dev = st.session_state.get("ev_dev_result")
    if dev is not None:
        result, src = dev
        render_result(result, "LIVE", f"development run via {src}")
