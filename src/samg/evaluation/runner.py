"""Experiments A and B: adaptive topology selection vs baselines (brief §12.1-12.4; owner: Dev A).

Protocol
1. Scenarios: disjoint dev/train/test seeds (``seed_splits``). Dev and train
   missions draw factor combinations only from the *seen* set; test missions draw
   from the whole grid, so held-out combinations appear only at test time.
2. Training: every fixed topology (P0-H/F/D) runs on every training mission; P1 is
   the best of them **on training data only**. P2 (UCB1) and P3 (LinUCB) learn
   online on the same training stream, updating only from ``ADMITTED`` episodes.
3. Test: all six policies run on the same held-out missions with the same
   simulator seed (paired). Learners are frozen (no ``observe``), so test
   reward is not learned from. Fixed-topology test runs double as the shadow
   counterfactual for simulator-oracle regret; they never reach a learner.

Mission execution is injected through ``MissionExecutor`` so this module stays
independent of the simulator/ACP implementation. The executor returns simulator
ground truth (used for evaluation) and the ACP ``EpisodeRecord`` (used for learning).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from samg.context import extract_features
from samg.domain import (
    EpisodeRecord,
    EpisodeStatus,
    LearningEvent,
    RewardSource,
    Scenario,
    SamgModel,
    TopologyCostConfig,
    TopologyName,
    config_hash,
)
from samg.domain.config import load_config
from samg.evaluation.metrics import PairedComparison, Summary, oracle_regret, paired_comparison, summarize
from samg.learning import best_fixed_from_training, make_policy
from samg.learning.base import PolicyDecision, TopologyPolicy
from samg.simulation.scenarios import generate_scenario, seed_splits, split_factor_combos
from samg.topology import eligible_topologies

PERFORMANCE_POLICIES = ("P0-H", "P0-F", "P0-D", "P1", "P2", "P3")
FIXED = {"P0-H": TopologyName.HIERARCHICAL, "P0-F": TopologyName.FUNCTIONAL_CELL,
         "P0-D": TopologyName.DISTRIBUTED}


class ExperimentConfig(SamgModel):
    """``config/experiment.yaml``. Hash it and freeze it before the held-out run (brief §12.2)."""

    version: str = "exp-v1"
    master_seed: int = 2026
    n_dev: int = Field(default=10, ge=0)
    n_train: int = Field(default=60, ge=1)
    n_test: int = Field(default=20, ge=1)
    holdout_fraction: float = Field(default=0.2, gt=0, lt=1)
    alpha: float = Field(default=0.5, ge=0)
    lam: float = Field(default=1.0, gt=0)
    warmup_per_arm: int = Field(default=2, ge=0)
    ucb_c: float = Field(default=1.0, ge=0)
    bootstrap_seed: int = 7
    frozen: bool = False


def load_experiment(config_dir: Path | None = None) -> ExperimentConfig:
    return load_config(ExperimentConfig, "experiment.yaml", config_dir)


class MissionResult(BaseModel):
    """What one mission execution returns to the runner."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    feasible: bool
    ground_truth_reward: float | None = Field(description="Simulator ground truth; evaluation only.")
    episode: EpisodeRecord | None = Field(default=None, description="ACP admission result; learning only.")
    metrics: dict[str, float] = Field(default_factory=dict)
    detail: str = ""


class MissionExecutor(Protocol):
    def execute(self, scenario: Scenario, topology: TopologyName, *, seed: int, decision_id: str) -> MissionResult:
        """Build the graph, allocate, simulate, collect evidence and run ACP admission."""


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    split: str
    policy: str
    step: int
    scenario_id: str
    mission_id: str
    family: str | None
    held_out_combo: bool
    eligible: tuple[TopologyName, ...]
    topology: TopologyName | None
    applicable: bool
    feasible: bool
    reward: float | None
    admitted_reward: float | None
    episode_status: EpisodeStatus | None
    learned: bool
    warmup: bool
    scores: dict[TopologyName, float]
    metrics: dict[str, float]


class PolicyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: str
    reward: Summary
    not_applicable: int
    infeasible: int
    selection_counts: dict[str, int]
    selection_by_family: dict[str, dict[str, int]]
    regret: Summary
    reward_by_family: dict[str, Summary]


class ExperimentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    config: ExperimentConfig
    config_hash: str
    p1_topology: TopologyName
    training_rewards: dict[str, list[float | None]]
    test: dict[str, PolicyResult]
    comparisons: list[PairedComparison]
    learner_updates: dict[str, int]
    blocked_updates: dict[str, int]
    records: list[RunRecord]

    def table(self) -> list[dict[str, Any]]:
        """Rows for the brief §12.11 results table (measured values only)."""
        rows = []
        for policy in PERFORMANCE_POLICIES:
            r = self.test[policy]
            rows.append({
                "policy": policy if policy != "P1" else f"P1 (best fixed = {self.p1_topology.value})",
                "n": r.reward.n, "mean_reward": r.reward.mean, "std": r.reward.std,
                "ci95": (r.reward.ci95_low, r.reward.ci95_high),
                "not_applicable": r.not_applicable, "infeasible": r.infeasible,
                "mean_regret": r.regret.mean,
            })
        return rows


# --- scenarios --------------------------------------------------------------

def build_splits(cfg: ExperimentConfig) -> dict[str, list[tuple[Scenario, bool]]]:
    """``split -> [(scenario, uses_held_out_combo)]``, deterministic in ``cfg``."""
    seeds = seed_splits(cfg.master_seed, cfg.n_dev, cfg.n_train, cfg.n_test)
    combos = split_factor_combos(cfg.master_seed, cfg.holdout_fraction)
    held = {f.key() for f in combos["held_out"]}
    grid = combos["seen"] + combos["held_out"]
    rng = np.random.default_rng(cfg.master_seed + 1)
    out: dict[str, list[tuple[Scenario, bool]]] = {}
    for split in ("dev", "train", "test"):
        pool = grid if split == "test" else combos["seen"]
        picks = rng.integers(0, len(pool), size=len(seeds[split]))
        out[split] = [(generate_scenario(seed, pool[int(i)]), pool[int(i)].key() in held)
                      for seed, i in zip(seeds[split], picks)]
    return out


# --- running ----------------------------------------------------------------

def _learning_event(episode: EpisodeRecord, decision: PolicyDecision, decision_id: str) -> LearningEvent:
    return LearningEvent(
        event_id=f"le-{episode.episode_id}",
        episode_id=episode.episode_id,
        decision_id=decision_id,
        topology=episode.topology,
        feature_schema_version=decision.feature_schema_version,
        context=decision.context,
        reward=episode.reward,
        reward_source=RewardSource.ACP_RECOMPUTED,
        status=episode.status,
    )


class _Runner:
    def __init__(self, executor: MissionExecutor, costs: TopologyCostConfig) -> None:
        self.executor = executor
        self.costs = costs
        self.updates: Counter[str] = Counter()
        self.blocked: Counter[str] = Counter()
        self._eligible_cache: dict[str, list[TopologyName]] = {}

    def eligible(self, scenario: Scenario) -> list[TopologyName]:
        if scenario.scenario_id not in self._eligible_cache:
            self._eligible_cache[scenario.scenario_id] = eligible_topologies(scenario, self.costs)[0]
        return self._eligible_cache[scenario.scenario_id]

    def step(self, *, split: str, name: str, policy: TopologyPolicy, step: int, scenario: Scenario,
             held_out: bool, learn: bool) -> RunRecord:
        context = extract_features(scenario)
        eligible = self.eligible(scenario)
        decision = policy.select(context.features, eligible, context.feature_schema_version)
        decision_id = f"dec-{split}-{name}-{step}-{scenario.scenario_id}"
        result: MissionResult | None = None
        learned = False
        if decision.topology is not None:
            result = self.executor.execute(scenario, decision.topology, seed=scenario.seed, decision_id=decision_id)
            episode = result.episode
            if learn and episode is not None:
                # Orchestration guard (INV-05): only ADMITTED episodes reach observe();
                # the protected policy re-checks via its own gate.
                if episode.status is EpisodeStatus.ADMITTED:
                    policy.observe(_learning_event(episode, decision, decision_id))
                    self.updates[name] += 1
                    learned = True
                else:
                    self.blocked[name] += 1
        episode = result.episode if result else None
        return RunRecord(
            split=split, policy=name, step=step, scenario_id=scenario.scenario_id,
            mission_id=scenario.mission.mission_id, family=scenario.mission.family, held_out_combo=held_out,
            eligible=tuple(eligible), topology=decision.topology, applicable=decision.topology is not None,
            feasible=bool(result and result.feasible),
            reward=result.ground_truth_reward if result else None,
            admitted_reward=episode.reward if episode else None,
            episode_status=episode.status if episode else None,
            learned=learned, warmup=decision.warmup, scores=dict(decision.scores),
            metrics=dict(result.metrics) if result else {},
        )


def _policy_result(name: str, records: list[RunRecord], counterfactual: dict[str, dict[str, float]],
                   seed: int) -> PolicyResult:
    mine = [r for r in records if r.policy == name]
    rewards = [r.reward for r in mine if r.applicable and r.feasible and r.reward is not None]
    selected = {r.mission_id: r.reward for r in mine if r.applicable and r.feasible and r.reward is not None}
    by_family: dict[str, list[float]] = defaultdict(list)
    sel_family: dict[str, Counter] = defaultdict(Counter)
    for r in mine:
        fam = r.family or "unknown"
        if r.topology is not None:
            sel_family[fam][r.topology.value] += 1
        if r.applicable and r.feasible and r.reward is not None:
            by_family[fam].append(r.reward)
    regret = oracle_regret(selected, counterfactual)
    return PolicyResult(
        policy=name,
        reward=summarize(rewards, seed=seed),
        not_applicable=sum(not r.applicable for r in mine),
        infeasible=sum(r.applicable and not r.feasible for r in mine),
        selection_counts=dict(Counter(r.topology.value for r in mine if r.topology is not None)),
        selection_by_family={f: dict(c) for f, c in sorted(sel_family.items())},
        regret=summarize(list(regret.values()), seed=seed),
        reward_by_family={f: summarize(v, seed=seed) for f, v in sorted(by_family.items())},
    )


def run_experiment_a(
    cfg: ExperimentConfig,
    executor: MissionExecutor,
    *,
    costs: TopologyCostConfig | None = None,
    extra_hash_configs: Sequence[SamgModel] = (),
    progress: Callable[[str], None] | None = None,
) -> ExperimentResult:
    """Run Experiment A (P3 vs P1) and B (P3 vs P2) on one shared protocol."""
    costs = costs or TopologyCostConfig()
    splits = build_splits(cfg)
    runner = _Runner(executor, costs)
    records: list[RunRecord] = []
    say = progress or (lambda _msg: None)

    # Training: fixed topologies on every training mission (P1 selection data).
    train = splits["train"]
    training_rewards: dict[str, list[float | None]] = {}
    fixed_train: dict[TopologyName, list[float]] = {t: [] for t in TopologyName}
    for name, topology in FIXED.items():
        say(f"train {name}")
        policy = make_policy(name)
        recs = [runner.step(split="train", name=name, policy=policy, step=i, scenario=s, held_out=h, learn=False)
                for i, (s, h) in enumerate(train)]
        records.extend(recs)
        training_rewards[name] = [r.reward for r in recs]
        fixed_train[topology] = [r.reward for r in recs if r.reward is not None]
    p1_topology = best_fixed_from_training({t: v for t, v in fixed_train.items() if v})

    # Training: online learners on the same stream.
    learners: dict[str, TopologyPolicy] = {
        "P2": make_policy("P2", {"c": cfg.ucb_c}),
        "P3": make_policy("P3", {"alpha": cfg.alpha, "lam": cfg.lam, "warmup_per_arm": cfg.warmup_per_arm},
                          seed=cfg.master_seed),
    }
    for name, policy in learners.items():
        say(f"train {name}")
        recs = [runner.step(split="train", name=name, policy=policy, step=i, scenario=s, held_out=h, learn=True)
                for i, (s, h) in enumerate(train)]
        records.extend(recs)
        training_rewards[name] = [r.reward for r in recs]

    # Held-out test: all policies, paired seeds, learners frozen.
    policies: dict[str, TopologyPolicy] = {name: make_policy(name) for name in FIXED}
    policies["P1"] = make_policy("P1", {"topology": p1_topology.value})
    policies.update(learners)
    test_records: list[RunRecord] = []
    for name in PERFORMANCE_POLICIES:
        say(f"test {name}")
        for i, (s, h) in enumerate(splits["test"]):
            test_records.append(runner.step(split="test", name=name, policy=policies[name], step=i,
                                            scenario=s, held_out=h, learn=False))
    records.extend(test_records)

    counterfactual: dict[str, dict[str, float]] = defaultdict(dict)
    for r in test_records:
        if r.policy in FIXED and r.applicable and r.feasible and r.reward is not None:
            counterfactual[r.mission_id][r.topology.value] = r.reward

    seed = cfg.bootstrap_seed
    test = {name: _policy_result(name, test_records, counterfactual, seed) for name in PERFORMANCE_POLICIES}

    def per_mission(name: str) -> dict[str, float]:
        return {r.mission_id: r.reward for r in test_records
                if r.policy == name and r.applicable and r.feasible and r.reward is not None}

    comparisons = [
        paired_comparison("P3", per_mission("P3"), "P1", per_mission("P1"), seed=seed),
        paired_comparison("P3", per_mission("P3"), "P2", per_mission("P2"), seed=seed),
        paired_comparison("P2", per_mission("P2"), "P1", per_mission("P1"), seed=seed),
    ]
    return ExperimentResult(
        config=cfg,
        config_hash=config_hash(cfg, costs, *extra_hash_configs),
        p1_topology=p1_topology,
        training_rewards=training_rewards,
        test=test,
        comparisons=comparisons,
        learner_updates=dict(runner.updates),
        blocked_updates=dict(runner.blocked),
        records=records,
    )
