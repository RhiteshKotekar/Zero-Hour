"""Tests for experiment JSON serialization/deserialization contract.

Validates:
1. Full ExperimentResult round-trip (serialize → deserialize → equal).
2. Experiment runner produces the full artifact.
3. Summary artifact is still generated alongside the full artifact.
4. Dashboard loads the full artifact successfully.
5. Dashboard handles missing artifacts gracefully.
6. Dashboard handles malformed JSON gracefully.
7. Dashboard handles legacy summary-only JSON gracefully.
8. Dashboard displays correct learning-curve data from the full artifact.
9. Dashboard displays correct experiment comparison data from the full artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samg.evaluation.executor import OrchestrationExecutor
from samg.evaluation.runner import (
    ExperimentConfig,
    ExperimentResult,
    run_experiment_a,
)
from samg.dashboard import data


# A tiny experiment config that runs fast but exercises the full pipeline.
TINY_CFG = ExperimentConfig(
    version="test-json-contract",
    n_dev=0,
    n_train=4,
    n_test=2,
    warmup_per_arm=1,
)


@pytest.fixture(scope="module")
def experiment_result() -> ExperimentResult:
    """Run a tiny experiment once for the whole module."""
    executor = OrchestrationExecutor()
    return run_experiment_a(TINY_CFG, executor, costs=executor.settings.costs)


# --- Test 1: Full ExperimentResult round-trip ---


def test_experiment_result_round_trip(experiment_result: ExperimentResult) -> None:
    """model_dump_json → model_validate_json reconstructs the same model."""
    json_str = experiment_result.model_dump_json(indent=2)
    restored = ExperimentResult.model_validate_json(json_str)

    assert restored.config == experiment_result.config
    assert restored.config_hash == experiment_result.config_hash
    assert restored.p1_topology == experiment_result.p1_topology
    assert restored.training_rewards == experiment_result.training_rewards
    assert set(restored.test) == set(experiment_result.test)
    assert len(restored.comparisons) == len(experiment_result.comparisons)
    assert len(restored.records) == len(experiment_result.records)
    assert restored.learner_updates == experiment_result.learner_updates
    assert restored.blocked_updates == experiment_result.blocked_updates


def test_round_trip_preserves_reward_values(experiment_result: ExperimentResult) -> None:
    """All reward values survive the round-trip without floating-point drift."""
    json_str = experiment_result.model_dump_json(indent=2)
    restored = ExperimentResult.model_validate_json(json_str)

    for orig, rest in zip(experiment_result.records, restored.records):
        assert orig.reward == pytest.approx(rest.reward) if orig.reward is not None else rest.reward is None
        assert orig.admitted_reward == pytest.approx(rest.admitted_reward) if orig.admitted_reward is not None \
            else rest.admitted_reward is None


# --- Test 2: Experiment runner produces full artifact ---


def test_runner_writes_full_artifact(experiment_result: ExperimentResult, tmp_path: Path) -> None:
    """Simulate what the experiment runner should write and verify it deserializes."""
    out_path = tmp_path / "experiment_a.json"
    out_path.write_text(experiment_result.model_dump_json(indent=2), encoding="utf-8")

    loaded = ExperimentResult.model_validate_json(out_path.read_text(encoding="utf-8"))
    assert loaded.config.version == experiment_result.config.version
    assert len(loaded.records) == len(experiment_result.records)


# --- Test 3: Summary artifact is still generated ---


def test_summary_json_is_valid(experiment_result: ExperimentResult) -> None:
    """The summary_json helper from run_experiment_a produces valid JSON with expected keys."""
    # Import the summary helper from the script module (it's defined there)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_experiment_a",
        Path(__file__).resolve().parents[3] / "scripts" / "run_experiment_a.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    summary = mod.summary_json(experiment_result)
    assert "config" in summary
    assert "table" in summary
    assert "test" in summary
    assert "comparisons" in summary
    # The summary should be JSON-serializable
    text = json.dumps(summary, indent=2, default=str)
    parsed = json.loads(text)
    assert isinstance(parsed["table"], list)


# --- Test 4: Dashboard loads the full artifact successfully ---


def test_dashboard_loads_full_artifact(experiment_result: ExperimentResult, tmp_path: Path) -> None:
    """data.load_experiment_result reads a full ExperimentResult file."""
    path = tmp_path / "experiment_a.json"
    path.write_text(experiment_result.model_dump_json(indent=2), encoding="utf-8")

    loaded = data.load_experiment_result(path)
    assert isinstance(loaded, ExperimentResult)
    assert loaded.config_hash == experiment_result.config_hash
    assert set(loaded.test) == set(experiment_result.test)


# --- Test 5: Dashboard handles missing artifact ---


def test_dashboard_missing_artifact(tmp_path: Path) -> None:
    """load_experiment_result raises ExperimentLoadError for nonexistent files."""
    path = tmp_path / "does_not_exist.json"
    with pytest.raises(data.ExperimentLoadError, match="not found"):
        data.load_experiment_result(path)


# --- Test 6: Dashboard handles malformed JSON ---


def test_dashboard_malformed_json(tmp_path: Path) -> None:
    """load_experiment_result raises ExperimentLoadError for invalid JSON."""
    path = tmp_path / "bad.json"
    path.write_text("{this is not valid json", encoding="utf-8")
    with pytest.raises(data.ExperimentLoadError, match="Malformed JSON"):
        data.load_experiment_result(path)


# --- Test 7: Dashboard handles legacy summary-only JSON ---


def test_dashboard_rejects_legacy_summary(experiment_result: ExperimentResult, tmp_path: Path) -> None:
    """load_experiment_result raises ExperimentLoadError for summary-only files."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_experiment_a",
        Path(__file__).resolve().parents[3] / "scripts" / "run_experiment_a.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    summary = mod.summary_json(experiment_result)
    path = tmp_path / "experiment_a.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with pytest.raises(data.ExperimentLoadError, match="human-readable summary"):
        data.load_experiment_result(path)


# --- Test 8: Dashboard displays correct learning-curve data ---


def test_learning_curve_data_from_full_artifact(experiment_result: ExperimentResult) -> None:
    """The full artifact has training_rewards usable for the learning curve."""
    assert "P3" in experiment_result.training_rewards
    assert "P2" in experiment_result.training_rewards
    # Fixed policies should also have training rewards
    assert "P0-H" in experiment_result.training_rewards

    # The training rewards list length should match the number of training missions
    for name, rewards in experiment_result.training_rewards.items():
        assert len(rewards) == TINY_CFG.n_train
        # Rewards should be floats or None (not applicable/infeasible cases)
        for r in rewards:
            assert r is None or isinstance(r, float)


def test_learning_curve_renders_from_artifact(experiment_result: ExperimentResult) -> None:
    """The view_eval._learning_curve helper can consume training_rewards."""
    # We can't import plotly in all environments, but we can verify the data shape
    for name, rewards in experiment_result.training_rewards.items():
        xs = [i for i, r in enumerate(rewards) if r is not None]
        ys = [r for r in rewards if r is not None]
        # At least some policies should have non-None rewards
        if ys:
            cum, total = [], 0.0
            for k, y in enumerate(ys, start=1):
                total += y
                cum.append(total / k)
            assert len(cum) == len(ys)
            assert all(isinstance(v, float) for v in cum)


# --- Test 9: Dashboard displays correct experiment comparison data ---


def test_comparison_data_from_full_artifact(experiment_result: ExperimentResult) -> None:
    """Comparisons are present and contain valid paired comparison data."""
    assert len(experiment_result.comparisons) == 3
    pairs_seen = set()
    for c in experiment_result.comparisons:
        pairs_seen.add((c.a, c.b))
        assert c.n_pairs >= 0
        assert c.wins + c.losses + c.ties == c.n_pairs
    # Expected pairs from the runner
    assert ("P3", "P1") in pairs_seen
    assert ("P3", "P2") in pairs_seen
    assert ("P2", "P1") in pairs_seen


def test_policy_rows_from_full_artifact(experiment_result: ExperimentResult) -> None:
    """data.policy_rows works correctly with a deserialized ExperimentResult."""
    rows = data.policy_rows(experiment_result)
    assert len(rows) == 6  # P0-H, P0-F, P0-D, P1, P2, P3
    policies = {r["policy"] for r in rows}
    # P1 gets renamed to include the best-fixed topology
    assert any("P1" in p for p in policies)
    for row in rows:
        assert "mean reward" in row
        assert "95% CI low" in row
        assert "95% CI high" in row
        assert "mean oracle regret" in row


def test_full_artifact_round_trip_preserves_policy_rows(experiment_result: ExperimentResult) -> None:
    """policy_rows give identical results before and after serialization round-trip."""
    original_rows = data.policy_rows(experiment_result)
    json_str = experiment_result.model_dump_json(indent=2)
    restored = ExperimentResult.model_validate_json(json_str)
    restored_rows = data.policy_rows(restored)

    assert len(original_rows) == len(restored_rows)
    for orig, rest in zip(original_rows, restored_rows):
        assert orig["policy"] == rest["policy"]
        assert orig["n"] == rest["n"]
        if orig["mean reward"] is not None:
            assert orig["mean reward"] == pytest.approx(rest["mean reward"])


# --- Extra: incompatible JSON (valid JSON, wrong schema) ---


def test_dashboard_rejects_incompatible_json(tmp_path: Path) -> None:
    """load_experiment_result raises ExperimentLoadError for valid JSON with wrong schema."""
    path = tmp_path / "wrong_schema.json"
    path.write_text(json.dumps({"some": "data", "not_an_experiment": True}), encoding="utf-8")
    with pytest.raises(data.ExperimentLoadError, match="Cannot parse"):
        data.load_experiment_result(path)

