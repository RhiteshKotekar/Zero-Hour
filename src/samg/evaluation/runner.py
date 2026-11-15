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
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
from samg.evaluation.metrics import PairedComparison, Summary, paired_comparison, summarize
from samg.allocation import feasible_topologies
from samg.learning import best_fixed_from_training, make_policy
from samg.learning.base import PolicyDecision, TopologyPolicy
from samg.simulation.scenarios import generate_scenario, seed_splits, split_factor_combos

PERFORMANCE_POLICIES = ("P0-H", "P0-F", "P0-D", "P1", "P2", "P3")
FIXED = {"P0-H": TopologyName.HIERARCHICAL, "P0-F": TopologyName.FUNCTIONAL_CELL,
         "P0-D": TopologyName.DISTRIBUTED}


class ExperimentConfig(SamgModel):
    """``config/experiment.yaml``. Hash it and freeze it before the held-out run (brief §12.2)."""

    version: str = "exp-v1"
    master_seed: int = 2026
    n_dev: int = Field(default=40, ge=0)
    n_train: int = Field(default=120, ge=1)
    n_test: int = Field(default=60, ge=1)
    holdout_fraction: float = Field(default=0.2, gt=0, lt=1)
    alpha: float = Field(default=0.5, ge=0)
    lam: float = Field(default=1.0, gt=0)
    warmup_per_arm: int = Field(default=2, ge=0)
    ucb_c: float = Field(default=1.0, ge=0)
    bootstrap_seed: int = 7
    frozen: bool = False


class EpsilonGreedyExperimentConfig(SamgModel):
    """Versioned P4 settings, kept separate from the frozen P0-P3 experiment."""

    version: str = "epsilon-greedy-exp-v1"
    epsilon: float = Field(default=0.2, ge=0, le=1)
    epsilon_grid: tuple[float, ...] = (0.05, 0.1, 0.2, 0.3, 0.5)
    lam: float = Field(default=1.0, gt=0)
    warmup_per_arm: int = Field(default=2, ge=0)
    policy_seeds: tuple[int, ...] = (101, 211, 307, 401, 503)
    frozen: bool = False

    @model_validator(mode="after")
    def _epsilon_config_valid(self) -> EpsilonGreedyExperimentConfig:
        if not self.epsilon_grid or any(not 0 <= e <= 1 for e in self.epsilon_grid):
            raise ValueError("epsilon_grid must contain values in [0, 1]")
        if not self.policy_seeds or len(set(self.policy_seeds)) != len(self.policy_seeds):
            raise ValueError("policy_seeds must be non-empty and unique")
        return self


def load_experiment(config_dir: Path | None = None) -> ExperimentConfig:
    return load_config(ExperimentConfig, "experiment.yaml", config_dir)


def load_epsilon_greedy_experiment(config_dir: Path | None = None) -> EpsilonGreedyExperimentConfig:
    return load_config(EpsilonGreedyExperimentConfig, "epsilon_greedy.yaml", config_dir)


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
    policy_seed: int | None = None
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
    explored: bool = False
    exploration_probability: float | None = None
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
    metric_means: dict[str, float] = Field(default_factory=dict,
                                           description="Mean of each executor metric over feasible runs.")
    exploration_count: int = 0
    exploration_rate: float | None = None
    policy_seed_count: int = 1


class ExperimentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    config: ExperimentConfig
    epsilon_greedy: EpsilonGreedyExperimentConfig | None = None
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
        for policy in self.test:
            r = self.test[policy]
            label = policy
            if policy == "P1":
                label = f"P1 (best fixed = {self.p1_topology.value})"
            elif policy == "P4" and self.epsilon_greedy is not None:
                label = f"P4 Contextual epsilon-greedy (epsilon={self.epsilon_greedy.epsilon:g})"
            elif policy.startswith("P4@"):
                label = f"P4 Contextual epsilon-greedy (epsilon={policy.removeprefix('P4@')})"
            rows.append({
                "policy": label,
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
            # D030: an arm is offered only if a feasible plan exists for it. An executor that
            # owns its own cost/allocation settings (and plan cache) answers this itself.
            own = getattr(self.executor, "eligible", None)
            self._eligible_cache[scenario.scenario_id] = (
                list(own(scenario)) if callable(own) else feasible_topologies(scenario, self.costs)[0])
        return self._eligible_cache[scenario.scenario_id]

    def step(self, *, split: str, name: str, policy: TopologyPolicy, step: int, scenario: Scenario,
             held_out: bool, learn: bool, policy_seed: int | None = None) -> RunRecord:
        context = extract_features(scenario)
        eligible = self.eligible(scenario)
        decision = policy.select(context.features, eligible, context.feature_schema_version)
        seed_tag = f"-ps{policy_seed}" if policy_seed is not None else ""
        decision_id = f"dec-{split}-{name}{seed_tag}-{step}-{scenario.scenario_id}"
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
            split=split, policy=name, policy_seed=policy_seed, step=step, scenario_id=scenario.scenario_id,
            mission_id=scenario.mission.mission_id, family=scenario.mission.family, held_out_combo=held_out,
            eligible=tuple(eligible), topology=decision.topology, applicable=decision.topology is not None,
            feasible=bool(result and result.feasible),
            reward=result.ground_truth_reward if result else None,
            admitted_reward=episode.reward if episode else None,
            episode_status=episode.status if episode else None,
            learned=learned, warmup=decision.warmup, explored=decision.explored,
            exploration_probability=decision.exploration_probability, scores=dict(decision.scores),
            metrics=dict(result.metrics) if result else {},
        )


def _policy_result(name: str, records: list[RunRecord], counterfactual: dict[str, dict[str, float]],
                   seed: int) -> PolicyResult:
    mine = [r for r in records if r.policy == name]
    by_mission: dict[str, list[float]] = defaultdict(list)
    by_mission_regret: dict[str, list[float]] = defaultdict(list)
    family_by_mission: dict[str, str] = {}
    for r in mine:
        if r.applicable and r.feasible and r.reward is not None:
            by_mission[r.mission_id].append(r.reward)
            family_by_mission[r.mission_id] = r.family or "unknown"
            best = max(counterfactual.get(r.mission_id, {}).values(), default=r.reward)
            by_mission_regret[r.mission_id].append(max(best - r.reward, 0.0))
    rewards = [float(np.mean(vals)) for vals in by_mission.values()]
    selected = {mission: float(np.mean(vals)) for mission, vals in by_mission.items()}
    by_family: dict[str, list[float]] = defaultdict(list)
    for mission, vals in by_mission.items():
        by_family[family_by_mission[mission]].append(float(np.mean(vals)))
    sel_family: dict[str, Counter] = defaultdict(Counter)
    for r in mine:
        fam = r.family or "unknown"
        if r.topology is not None:
            sel_family[fam][r.topology.value] += 1
    regret = {mission: float(np.mean(vals)) for mission, vals in by_mission_regret.items()}
    metric_values: dict[str, list[float]] = defaultdict(list)
    for r in mine:
        if r.applicable and r.feasible:
            for k, v in r.metrics.items():
                metric_values[k].append(float(v))
    return PolicyResult(
        policy=name,
        reward=summarize(rewards, seed=seed),
        not_applicable=sum(not r.applicable for r in mine),
        infeasible=sum(r.applicable and not r.feasible for r in mine),
        selection_counts=dict(Counter(r.topology.value for r in mine if r.topology is not None)),
        selection_by_family={f: dict(c) for f, c in sorted(sel_family.items())},
        regret=summarize(list(regret.values()), seed=seed),
        reward_by_family={f: summarize(v, seed=seed) for f, v in sorted(by_family.items())},
        metric_means={k: float(np.mean(v)) for k, v in sorted(metric_values.items())},
        exploration_count=sum(r.explored for r in mine),
        exploration_rate=(
            sum(r.explored for r in mine) / sum(r.exploration_probability is not None and not r.warmup for r in mine)
            if any(r.exploration_probability is not None and not r.warmup for r in mine) else None
        ),
        policy_seed_count=len({r.policy_seed for r in mine if r.policy_seed is not None}) or 1,
    )


def run_experiment_a(
    cfg: ExperimentConfig,
    executor: MissionExecutor,
    *,
    costs: TopologyCostConfig | None = None,
    extra_hash_configs: Sequence[SamgModel] = (),
    progress: Callable[[str], None] | None = None,
    splits: dict[str, list[tuple[Scenario, bool]]] | None = None,
    epsilon_greedy: EpsilonGreedyExperimentConfig | None = None,
    epsilon_sweep: bool = False,
) -> ExperimentResult:
    """Run Experiment A (P3 vs P1) and B (P3 vs P2) on one shared protocol.

    ``splits`` overrides ``build_splits(cfg)`` (needs ``train`` and ``test``); used only for
    ablations on design-seed missions, never for the reported held-out run.
    """
    costs = costs or TopologyCostConfig()
    splits = splits if splits is not None else build_splits(cfg)
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

    # Optional P4 training: independent seeded runs on the same scenario stream.
    p4_policies: dict[str, dict[int, TopologyPolicy]] = {}
    p4_names: list[str] = []
    if epsilon_greedy is not None:
        epsilon_values = sorted(set(epsilon_greedy.epsilon_grid if epsilon_sweep else (epsilon_greedy.epsilon,)))
        for epsilon in epsilon_values:
            name = f"P4@{epsilon:g}" if epsilon_sweep else "P4"
            p4_names.append(name)
            p4_policies[name] = {}
            p4_rewards: list[float | None] = []
            for policy_seed in epsilon_greedy.policy_seeds:
                policy = make_policy(
                    "P4",
                    {"epsilon": epsilon, "lam": epsilon_greedy.lam,
                     "warmup_per_arm": epsilon_greedy.warmup_per_arm},
                    seed=policy_seed,
                )
                p4_policies[name][policy_seed] = policy
                say(f"train {name} seed={policy_seed}")
                recs = [runner.step(split="train", name=name, policy=policy, step=i, scenario=s, held_out=h,
                                    learn=True, policy_seed=policy_seed)
                        for i, (s, h) in enumerate(train)]
                records.extend(recs)
                p4_rewards.extend(r.reward for r in recs)
            training_rewards[name] = p4_rewards

    policy_names = PERFORMANCE_POLICIES + tuple(p4_names)

    # Held-out test: all policies, paired seeds, learner estimates frozen.
    policies: dict[str, TopologyPolicy] = {name: make_policy(name) for name in FIXED}
    policies["P1"] = make_policy("P1", {"topology": p1_topology.value})
    policies.update(learners)
    test_records: list[RunRecord] = []
    for name in PERFORMANCE_POLICIES:
        say(f"test {name}")
        for i, (s, h) in enumerate(splits["test"]):
            test_records.append(runner.step(split="test", name=name, policy=policies[name], step=i,
                                            scenario=s, held_out=h, learn=False))
    if epsilon_greedy is not None:
        for name in p4_names:
            for policy_seed, policy in p4_policies[name].items():
                say(f"test {name} seed={policy_seed}")
                for i, (s, h) in enumerate(splits["test"]):
                    test_records.append(runner.step(split="test", name=name, policy=policy, step=i, scenario=s,
                                                    held_out=h, learn=False, policy_seed=policy_seed))
    records.extend(test_records)

    counterfactual: dict[str, dict[str, float]] = defaultdict(dict)
    for r in test_records:
        if r.policy in FIXED and r.applicable and r.feasible and r.reward is not None:
            counterfactual[r.mission_id][r.topology.value] = r.reward

    seed = cfg.bootstrap_seed
    test = {name: _policy_result(name, test_records, counterfactual, seed) for name in policy_names}

    def per_mission(name: str) -> dict[str, float]:
        grouped: dict[str, list[float]] = defaultdict(list)
        for r in test_records:
            if r.policy == name and r.applicable and r.feasible and r.reward is not None:
                grouped[r.mission_id].append(r.reward)
        return {mission: float(np.mean(values)) for mission, values in grouped.items()}

    comparisons = [
        paired_comparison("P3", per_mission("P3"), "P1", per_mission("P1"), seed=seed),
        paired_comparison("P3", per_mission("P3"), "P2", per_mission("P2"), seed=seed),
        paired_comparison("P2", per_mission("P2"), "P1", per_mission("P1"), seed=seed),
    ]
    if epsilon_greedy is not None:
        for name in p4_names:
            comparisons.extend([
                paired_comparison(name, per_mission(name), "P3", per_mission("P3"), seed=seed),
                paired_comparison(name, per_mission(name), "P2", per_mission("P2"), seed=seed),
                paired_comparison(name, per_mission(name), "P1", per_mission("P1"), seed=seed),
            ])
    return ExperimentResult(
        config=cfg,
        epsilon_greedy=epsilon_greedy,
        config_hash=config_hash(cfg, costs, *extra_hash_configs,
                                *([epsilon_greedy] if epsilon_greedy is not None else [])),
        p1_topology=p1_topology,
        training_rewards=training_rewards,
        test=test,
        comparisons=comparisons,
        learner_updates=dict(runner.updates),
        blocked_updates=dict(runner.blocked),
        records=records,
    )


# --- dev tuning (brief §12.2 step 3) -----------------------------------------


class DevAlphaResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alpha: float
    eval_reward: Summary
    selection_counts: dict[str, int]
    updates: int


class DevTuningResult(BaseModel):
    """LinUCB ``alpha`` chosen on the DEV split only; train and test missions are never touched."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    grid: tuple[float, ...]
    n_dev_stream: int
    n_dev_eval: int
    results: list[DevAlphaResult]
    chosen_alpha: float
    rule: str


class DevEpsilonResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    epsilon: float
    eval_reward: Summary
    selection_counts: dict[str, int]
    updates: int
    replicate_means: dict[int, float]


class EpsilonTuningResult(BaseModel):
    """P4 epsilon selection using only the dev stream and dev evaluation block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    grid: tuple[float, ...]
    policy_seeds: tuple[int, ...]
    n_dev_stream: int
    n_dev_eval: int
    results: list[DevEpsilonResult]
    chosen_epsilon: float
    rule: str


def tune_alpha_on_dev(
    cfg: ExperimentConfig,
    executor: MissionExecutor,
    grid: Sequence[float],
    *,
    costs: TopologyCostConfig | None = None,
    stream_fraction: float = 0.5,
    progress: Callable[[str], None] | None = None,
) -> DevTuningResult:
    """Split the dev missions into a learning stream and a frozen evaluation block.

    For each ``alpha`` a fresh LinUCB (same ``lam``/warm-up/seed as the main run) learns
    online on the stream from ADMITTED episodes only, then is evaluated frozen on the
    evaluation block. Rule (predeclared): highest mean ground-truth reward on the
    evaluation block; ties (within 1e-9) go to the smaller ``alpha``.
    """
    if not grid:
        raise ValueError("alpha grid must not be empty")
    dev = build_splits(cfg)["dev"]
    cut = int(round(len(dev) * stream_fraction))
    stream, held = dev[:cut], dev[cut:]
    if not stream or not held:
        raise ValueError("dev split too small to tune: need missions in both stream and evaluation block")
    runner = _Runner(executor, costs or TopologyCostConfig())
    say = progress or (lambda _msg: None)
    results: list[DevAlphaResult] = []
    for alpha in sorted(float(a) for a in grid):
        say(f"dev alpha={alpha}")
        name = f"P3@{alpha}"
        policy = make_policy("P3", {"alpha": alpha, "lam": cfg.lam, "warmup_per_arm": cfg.warmup_per_arm},
                             seed=cfg.master_seed)
        for i, (s, h) in enumerate(stream):
            runner.step(split="dev", name=name, policy=policy, step=i, scenario=s, held_out=h, learn=True)
        recs = [runner.step(split="dev-eval", name=name, policy=policy, step=i, scenario=s, held_out=h,
                            learn=False) for i, (s, h) in enumerate(held)]
        rewards = [r.reward for r in recs if r.applicable and r.feasible and r.reward is not None]
        results.append(DevAlphaResult(
            alpha=alpha, eval_reward=summarize(rewards, seed=cfg.bootstrap_seed),
            selection_counts=dict(Counter(r.topology.value for r in recs if r.topology is not None)),
            updates=runner.updates[name]))
    best = results[0]
    for r in results[1:]:
        if (r.eval_reward.mean or float("-inf")) > (best.eval_reward.mean or float("-inf")) + 1e-9:
            best = r
    return DevTuningResult(grid=tuple(r.alpha for r in results), n_dev_stream=len(stream), n_dev_eval=len(held),
                           results=results, chosen_alpha=best.alpha,
                           rule="max dev-eval mean reward; ties -> smaller alpha")


def tune_epsilon_on_dev(
    cfg: ExperimentConfig,
    executor: MissionExecutor,
    policy_cfg: EpsilonGreedyExperimentConfig,
    *,
    costs: TopologyCostConfig | None = None,
    stream_fraction: float = 0.5,
    progress: Callable[[str], None] | None = None,
) -> EpsilonTuningResult:
    """Tune epsilon on dev data, averaging frozen dev-eval reward across policy seeds."""
    dev = build_splits(cfg)["dev"]
    cut = int(round(len(dev) * stream_fraction))
    stream, held = dev[:cut], dev[cut:]
    if not stream or not held:
        raise ValueError("dev split too small to tune: need missions in both stream and evaluation block")
    if not policy_cfg.epsilon_grid:
        raise ValueError("epsilon grid must not be empty")
    runner = _Runner(executor, costs or TopologyCostConfig())
    say = progress or (lambda _msg: None)
    results: list[DevEpsilonResult] = []
    for epsilon in sorted(set(float(e) for e in policy_cfg.epsilon_grid)):
        if not 0 <= epsilon <= 1:
            raise ValueError("epsilon values must be in [0, 1]")
        say(f"dev epsilon={epsilon}")
        eval_records: list[RunRecord] = []
        per_seed: dict[int, float] = {}
        selection_counts: Counter[str] = Counter()
        updates = 0
        for policy_seed in policy_cfg.policy_seeds:
            name = f"P4@{epsilon:g}:seed{policy_seed}"
            policy = make_policy(
                "P4",
                {"epsilon": epsilon, "lam": policy_cfg.lam,
                 "warmup_per_arm": policy_cfg.warmup_per_arm},
                seed=policy_seed,
            )
            for i, (scenario, held_out) in enumerate(stream):
                runner.step(split="dev", name=name, policy=policy, step=i, scenario=scenario,
                            held_out=held_out, learn=True, policy_seed=policy_seed)
            recs = [runner.step(split="dev-eval", name=name, policy=policy, step=i, scenario=scenario,
                                held_out=held_out, learn=False, policy_seed=policy_seed)
                    for i, (scenario, held_out) in enumerate(held)]
            eval_records.extend(recs)
            per_seed[policy_seed] = float(np.mean([r.reward for r in recs
                                                   if r.applicable and r.feasible and r.reward is not None]))
            selection_counts.update(r.topology.value for r in recs if r.topology is not None)
            updates += runner.updates[name]
        by_mission: dict[str, list[float]] = defaultdict(list)
        for record in eval_records:
            if record.applicable and record.feasible and record.reward is not None:
                by_mission[record.mission_id].append(record.reward)
        mission_means = [float(np.mean(values)) for values in by_mission.values()]
        results.append(DevEpsilonResult(
            epsilon=epsilon,
            eval_reward=summarize(mission_means, seed=cfg.bootstrap_seed),
            selection_counts=dict(selection_counts),
            updates=updates,
            replicate_means=per_seed,
        ))
    best = results[0]
    for candidate in results[1:]:
        if (candidate.eval_reward.mean or float("-inf")) > (best.eval_reward.mean or float("-inf")) + 1e-9:
            best = candidate
    return EpsilonTuningResult(
        grid=tuple(result.epsilon for result in results),
        policy_seeds=policy_cfg.policy_seeds,
        n_dev_stream=len(stream),
        n_dev_eval=len(held),
        results=results,
        chosen_epsilon=best.epsilon,
        rule="max dev-eval mean across policy seeds; ties -> smaller epsilon",
    )
