"""Experiment C harness on a small deterministic config (brief §12.5, §12.6)."""

from __future__ import annotations

import pytest

from samg.evaluation.experiment_c import (
    ExperimentCConfig,
    attack_schedule,
    load_experiment_c,
    run_experiment_c,
)

pytestmark = pytest.mark.integration

SMALL = ExperimentCConfig(n_warmup=8, n_dev_attack=4, n_dev_followup=4, n_attack=6, n_followup=5,
                          n_missing_evidence=3, n_replay=2, use_cpsat=False,
                          tuning_magnitudes=((0.4, 0.5),), corruption_levels=(0.0, 0.5))


@pytest.fixture(scope="module")
def result() -> dict:
    return run_experiment_c(SMALL)


def _level(result: dict, level: float) -> dict:
    return next(x for x in result["levels"] if x["corruption_level"] == level)


def test_config_section_loads_and_schedule_is_seeded() -> None:
    cfg = load_experiment_c()
    assert cfg.corruption_levels == (0.0, 0.2, 0.4)
    assert attack_schedule(0.4, 30, 17) == attack_schedule(0.4, 30, 17)
    assert len(attack_schedule(0.4, 30, 17)) == 12
    assert attack_schedule(0.2, 30, 17) <= attack_schedule(0.4, 30, 17)  # nested across levels


def test_run_is_deterministic(result: dict) -> None:
    again = run_experiment_c(SMALL)
    assert again["frozen_attack_hash"] == result["frozen_attack_hash"]
    assert again["levels"] == result["levels"]
    assert again["missing_evidence"] == result["missing_evidence"]


def test_protected_admits_zero_unsupported_reports(result: dict) -> None:
    lv = _level(result, 0.5)
    s2 = lv["counts"]["S2"]
    assert s2["unsupported_submitted"] > 0
    assert s2["unsupported_authenticated"] == s2["unsupported_submitted"]  # validly signed, authorised, fresh
    assert s2["unsupported_admitted"] == 0 and s2["manipulated_updates"] == 0
    assert s2["updates_from_agent_claim"] == 0
    assert all(lv["s2_state_equals_reference"].values())


def test_vulnerable_state_changes_under_attack(result: dict) -> None:
    lv = _level(result, 0.5)
    s1 = lv["counts"]["S1"]
    assert s1["unsupported_admitted"] > 0 and s1["manipulated_updates"] > 0
    assert max(v["b_l2"] for v in lv["divergence"]["S1_vs_R"].values()) > 1e-3
    # at 0 % corruption S1 learns honest claims: no manipulated update
    assert _level(result, 0.0)["counts"]["S1"]["manipulated_updates"] == 0


def test_frr_has_denominators(result: dict) -> None:
    for lv in result["levels"]:
        for name in ("S1", "S2"):
            c = lv["counts"][name]
            assert c["legit_submitted"] > 0
            assert c["frr"] == pytest.approx(c["legit_blocked"] / c["legit_submitted"])


def test_missing_evidence_is_safe_non_learning(result: dict) -> None:
    me = result["missing_evidence"]
    assert me["counts"]["missions"] > 0
    assert me["counts"]["episode_PROVISIONAL"] == me["counts"]["missions"]
    assert me["counts"]["protected_updates"] == 0 and me["protected_state_unchanged"]


def test_replay_causes_no_second_update(result: dict) -> None:
    rp = result["replay"]["counts"]
    assert rp["replayed_events"] > 0 and rp["duplicate_updates_applied"] == 0
    assert rp["obsolete_epoch_events"] > 0
    assert sum(v for k, v in rp.items() if k.startswith("obsolete_STALE:OBSOLETE_EPOCH")) == rp["obsolete_epoch_events"]
    assert result["replay"]["policy_state_unchanged"]
