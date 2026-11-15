"""SAMG judge-facing dashboard (brief §15). Run: ``streamlit run src/samg/dashboard/app.py``.

A thin Streamlit shell over the existing orchestration and evaluation functions.
No business logic lives in the UI; see ``samg.dashboard.data``.
"""

from __future__ import annotations

import streamlit as st

from samg.dashboard import view_eval, view_mission, view_security


def main() -> None:
    st.set_page_config(page_title="SAMG dashboard", layout="wide")
    st.title("SAMG: Secure Adaptive Mission Graphs")
    st.caption("All randomness seeded; simulated time. Panels are labelled LIVE (computed now), REPLAYED "
               "(loaded from a saved deterministic run), AGGREGATE (saved evaluation) or SHADOW "
               "(evaluation-only, never learned). Trust boundary: the simulated witness is assumed honest.")
    tab1, tab2, tab3 = st.tabs(["Mission Control", "Adaptive Evaluation Lab", "Security & Attack Lab"])
    with tab1:
        view_mission.render()
    with tab2:
        view_eval.render()
    with tab3:
        view_security.render()


main()
