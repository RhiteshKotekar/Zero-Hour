"""SAMG-vs-baseline experiment framework (D042): scenarios, ladder, determinism, summaries, dashboard tab."""

from __future__ import annotations

import json

import pytest

from samg.experiments import compare
from samg.experiments.scenarios import LADDER, RUNGS, SCENARIOS
from samg.twin.layout import load_config

CFG = load_config()
FIELDS = {"truly_fulfilled_rate", "avg_fulfilment_s", "corrupted_tasks", "false_claims_accepted", "runtime_s"}


def _strip(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "runtime_s"}  # wall-clock is the only non-deterministic field


def test_six_scenarios_and_ladder_defined() -> None:
    assert sorted(SCENARIOS) == ["W1", "W2", "W3", "W4", "W5", "W6"]
    assert [r.name for r in LADDER][:4] == ["B0", "B1", "B2", "SAMG"]


def test_every_rung_sees_the_identical_mission() -> None:
    spec = SCENARIOS["W6"].spec(1001, CFG)
    from samg.experiments.scenarios import with_rung
    specs = [with_rung(spec, r) for r in LADDER]
    assert len({(s.seed, s.orders, s.injections) for s in specs}) == 1


@pytest.mark.parametrize("rung", ["B0", "B1"])
def test_single_run_is_deterministic(rung: str) -> None:
    a = compare.run_one("W5", RUNGS[rung], 1001, CFG)
    b = compare.run_one("W5", RUNGS[rung], 1001, CFG)
    assert FIELDS <= set(a) and _strip(a) == _strip(b)


def test_training_seed_overlap_is_refused() -> None:
    base = int(CFG["learning"]["training_seed_base"])
    with pytest.raises(ValueError, match="overlap"):
        compare.run(["W1"], [base], ["B0"], progress=False)


def test_summary_pairs_by_seed_and_renders(tmp_path) -> None:
    result = compare.run(["W5"], [1001, 1002], ["B0", "B2"], progress=False)
    summ = result["summary"]["W5"]
    assert set(summ["rungs"]) == {"B0", "B2"}
    assert summ["rungs"]["B0"]["false_claims_accepted"]["mean"] > 0
    assert summ["rungs"]["B2"]["false_claims_accepted"]["mean"] == 0
    md = compare.render_markdown(result)
    assert "## W5" in md and "truly_fulfilled_rate" in md
    json.dumps(result, default=str)  # serialisable


def test_dashboard_tab_renders_saved_result(tmp_path, monkeypatch) -> None:
    st_testing = pytest.importorskip("streamlit.testing.v1")
    result = compare.run(["W1"], [1001, 1002], ["B0", "B1"], progress=False)
    run_dir = tmp_path / "unit-run"
    run_dir.mkdir()
    (run_dir / "results.json").write_text(json.dumps(result, default=str), encoding="utf-8")
    import samg.dashboard.view_baseline as vb
    monkeypatch.setattr(vb, "OUT_DIR", tmp_path)
    assert vb.saved_runs() == [run_dir]
    frame = vb.summary_frame(vb.load_result(run_dir), "W1")
    assert {"B0", "B1"} <= set(frame.columns)

    def app() -> None:
        import samg.dashboard.view_baseline as v
        v.render()

    at = st_testing.AppTest.from_function(app)
    at.run(timeout=60)
    assert not at.exception
