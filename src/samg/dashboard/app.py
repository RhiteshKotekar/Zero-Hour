"""SAMG judge-facing dashboard (brief §15). Run: ``streamlit run src/samg/dashboard/app.py``.

A thin Streamlit shell over the existing orchestration and evaluation functions.
No business logic lives in the UI; see ``samg.dashboard.data``.
"""

from __future__ import annotations

import streamlit as st

from samg.dashboard import view_eval, view_mission, view_security, view_warehouse


def main() -> None:
    st.set_page_config(page_title="SAMG Warehouse Digital Twin & Dashboard", layout="wide")
    st.title("SAMG: Secure Adaptive Mission Graphs")
    st.caption("Industrial Digital Twin & Autonomous Fleet Control Room. All randomness seeded; simulated time. "
               "Panels are labelled LIVE (computed now), REPLAYED (loaded from a saved deterministic run), "
               "AGGREGATE (saved evaluation) or SHADOW (evaluation-only, never learned). Trust boundary: the simulated witness is assumed honest.")
    tab0, tab1, tab2, tab3 = st.tabs([
        "Warehouse Digital Twin",
        "Mission Control",
        "Adaptive Evaluation Lab",
        "Security & Attack Lab",
    ])
    with tab0:
        view_warehouse.render()
    with tab1:
        view_mission.render()
    with tab2:
        view_eval.render()
    with tab3:
        view_security.render()


main()
