"""The Streamlit app renders and runs a mission without exceptions."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("plotly")

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parents[3] / "src" / "samg" / "dashboard" / "app.py"


def _app() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def test_app_renders_four_tabs() -> None:
    at = _app()
    assert [t.label for t in at.tabs] == ["Warehouse Digital Twin", "Mission Control", "Adaptive Evaluation Lab",
                                          "Security & Attack Lab"]
    assert any("Mission Control" in h.value for h in at.header)


def test_mission_run_shows_ids() -> None:
    at = _app()
    at.session_state["mc_use_cpsat"] = False
    at.button(key="mc_go").click().run()
    assert not at.exception, at.exception
    info = " ".join(i.value for i in at.info)
    assert "Mission ID" in info and "Config ID" in info and "Seed" in info
    assert not at.error


def test_reset_button() -> None:
    at = _app()
    at.number_input(key="mc_seed").set_value(42).run()
    at.button(key="mc_reset").click().run()
    assert not at.exception, at.exception
    assert at.number_input(key="mc_seed").value == 7
