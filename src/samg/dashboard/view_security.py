"""View 3: Security & Attack Lab (brief §15.5). Uses ``evaluation.attacks`` through ``run_single_mission``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from samg.dashboard import data
from samg.dashboard.view_mission import badge, run_header
from samg.domain import TopologyName

TRUST_BOUNDARY = """
**Trust boundary (brief §8.5).** A valid signature proves *who* sent a report, not that it is true.
The ACP checks signature, role authorisation and freshness (seq/nonce/time), then corroborates each claim
against independent, signed witness transitions and recomputes the reward from witness-verified outcomes.
Assumed honest: the simulated witness and the ACP host. Out of scope: a compromised witness, collusion with
the witness, key theft from the ACP. `VulnerableLinUCB` (S1) exists for Experiment C only and learns the last
authenticated `REWARD_CLAIM`; it is never the default wiring.
"""


def _divergence_fig(rows: list[dict[str, Any]]) -> go.Figure:
    fig = go.Figure()
    for key in ("||A_S1-A_S2||_F", "||b_S1-b_S2||", "||theta_S1-theta_S2||"):
        fig.add_trace(go.Bar(x=[r["arm"] for r in rows], y=[r[key] for r in rows], name=key))
    fig.update_layout(barmode="group", height=320, margin={"l": 10, "r": 10, "t": 20, "b": 30})
    return fig


def render_live(run: data.AttackRun) -> None:
    badge("LIVE")
    a = run.attack
    rec = run.anatomy_s2
    run_header(rec.mission_id, run.config_id, run.judge_seed,
               f"stream seeds from `{run.stream_seed_base}` · pre-attack protected updates {run.pre_updates}")
    st.subheader("Attack setup")
    st.write(f"Attacker **{a.compromised_agent}**: registered, authorised, signs with its real key and fresh "
             f"sequence numbers. Preferred topology fixed in advance: **{a.preferred_topology.value}**. "
             f"False REWARD_CLAIM = true reward + {a.inflation} on the preferred topology, true reward - "
             f"{a.deflation} otherwise. Attacked mission indices: {sorted(a.schedule)}; sabotage (fault injection) "
             f"on {sorted(a.sabotage_schedule)}.")

    st.subheader("Anatomy: judge mission, attacked, on throwaway clones of the pre-attack state")
    sab = [o.task_id for o in (rec.trace.outcomes if rec.trace else ()) if o.failure_reason == "TASK_FAILED"]
    st.write(f"Topology S2={rec.decision.topology.value if rec.decision.topology else '-'} · "
             f"S1={run.anatomy_s1.decision.topology.value if run.anatomy_s1.decision.topology else '-'} · "
             f"ground-truth FAILED task(s) from fault injection: {', '.join(sab) or '-'}")
    rows = data.event_rows(rec)
    only_false = st.checkbox("Show only the attacker's false events", value=True, key="sec_only_false")
    st.caption("Per-event validation trace (S2 world). `auth stage` = signature + role authorisation + freshness; "
               "`evidence stage` = corroboration against the witness.")
    st.dataframe([r for r in rows if r["false claim (oracle)"] or not only_false], hide_index=True)
    ep = rec.episode
    if ep is not None:
        st.write(f"Episode (S2): **{ep.status.value}** [{', '.join(r.value for r in ep.reason_codes) or '-'}] · "
                 f"ACP reward {ep.reward if ep.reward is None else round(ep.reward, 4)}")
    c1, c2 = st.columns(2)
    for col, r, name in ((c1, rec, "S2 protected"), (c2, run.anatomy_s1, "S1 vulnerable")):
        le = r.learning_event
        col.markdown(f"**{name}**")
        if r.learning_applied and le is not None:
            col.write(f"update APPLIED: {le.reward:.4f} from {le.reward_source.value}")
        else:
            col.write(f"update refused: {r.learning_rejection.value if r.learning_rejection else '-'}")
        if r.ground_truth_reward is not None:
            col.caption(f"simulator ground truth {r.ground_truth_reward.reward:.4f}; claimed "
                        f"{r.claimed_reward if r.claimed_reward is None else round(r.claimed_reward, 4)}")

    st.subheader("Attack window: S1 vs S2 from the identical pre-attack state")
    st.dataframe(data.window_rows(run), hide_index=True)
    st.dataframe([data.attack_summary(run, data.load_settings(False).security.witness.identity_id)],
                 hide_index=True)
    st.subheader("Parameter divergence after the window (0 at the start: identical clones)")
    st.plotly_chart(_divergence_fig(run.divergence), width="stretch", key="sec_div")
    st.dataframe(run.divergence, hide_index=True)
    st.subheader("Next choice (probe on clones; state unchanged)")
    st.dataframe([{"mission": label, "S2 next": v["S2"]["topology"], "S1 next": v["S1"]["topology"],
                   "S2 scores": v["S2"]["scores"], "S1 scores": v["S1"]["scores"],
                   "differs": v["S2"]["topology"] != v["S1"]["topology"]} for label, v in run.next_choice.items()],
                 hide_index=True)


def render() -> None:
    st.header("Security & Attack Lab")
    st.info(TRUST_BOUNDARY)
    saved = data.saved_files("experiment_c*.json")
    if saved:
        choice = st.selectbox("Saved Experiment C run", [f.name for f in saved], key="sec_file")
        badge("REPLAYED")
        try:
            st.json(data.load_saved_json(Path(data.ARTIFACTS) / choice), expanded=False)
        except Exception as exc:
            st.error(f"Could not load {choice}: {type(exc).__name__}: {exc}")
    else:
        st.caption(f"No saved `experiment_c*.json` in `{data.ARTIFACTS}`; use the live small run below.")

    st.subheader("Live small attack run")
    d = data.DEMO_DEFAULTS
    for k in ("attack_agent", "attack_preferred", "n_pre", "n_attack"):
        st.session_state.setdefault(f"sec_{k}", d[k])
    if st.button("Reset to saved demo configuration", key="sec_reset"):
        for k in ("attack_agent", "attack_preferred", "n_pre", "n_attack"):
            st.session_state[f"sec_{k}"] = d[k]
        st.session_state.pop("sec_run", None)
        st.rerun()
    c1, c2, c3, c4 = st.columns(4)
    agent = c1.text_input("Compromised agent", key="sec_attack_agent")
    pref = c2.selectbox("Attacker's preferred topology", [t.value for t in TopologyName], key="sec_attack_preferred")
    n_pre = c3.number_input("Pre-attack missions", min_value=3, max_value=40, step=1, key="sec_n_pre")
    n_att = c4.number_input("Attacked missions", min_value=1, max_value=20, step=1, key="sec_n_attack")
    if st.button("Run attack comparison", type="primary", key="sec_go"):
        with st.spinner("running S1 and S2..."):
            try:
                st.session_state["sec_run"] = data.run_attack_comparison(
                    n_pre=int(n_pre), n_attack=int(n_att), compromised=agent, preferred=TopologyName(pref))
            except Exception as exc:
                st.session_state.pop("sec_run", None)
                st.error(f"Attack run failed: {type(exc).__name__}: {exc}")
    run = st.session_state.get("sec_run")
    if run is not None:
        render_live(run)
