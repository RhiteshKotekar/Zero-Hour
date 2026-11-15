"""The Experiment C ``attack:`` section rides in security_policy.yaml without changing the ACP policy."""

from __future__ import annotations

from samg.assurance.policy import load_security_policy
from samg.evaluation.experiment_c import ExperimentCConfig, load_experiment_c


def test_attack_section_is_optional_and_typed_by_the_harness() -> None:
    policy = load_security_policy()
    assert policy.attack is not None and policy.attack["compromised_agent"] == "A1"
    without = policy.model_copy(update={"attack": None})
    assert without.roles == policy.roles and without.admission == policy.admission
    cfg = load_experiment_c()
    assert isinstance(cfg, ExperimentCConfig) and not cfg.frozen


def test_attack_hash_ignores_freeze_bookkeeping_but_not_magnitude() -> None:
    cfg = load_experiment_c()
    frozen = cfg.model_copy(update={"frozen": True, "frozen_hash": "x"})
    assert frozen.attack_hash() == cfg.attack_hash()
    assert cfg.model_copy(update={"inflation": 0.5}).attack_hash() != cfg.attack_hash()
