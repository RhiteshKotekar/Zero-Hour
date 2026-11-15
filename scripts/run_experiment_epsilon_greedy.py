"""Tune P4 on dev data, freeze its config, and compare against the frozen A/B baselines.

Run from the repository root::

    python scripts/run_experiment_epsilon_greedy.py

P4 uses ``config/epsilon_greedy.yaml``. The existing frozen ``experiment.yaml``
and its measured P0-P3 results are never rewritten.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import yaml

from samg.domain import config_hash
from samg.domain.config import CONFIG_DIR, load_allocation, load_reward, load_topology_costs
from samg.evaluation.executor import OrchestrationExecutor
from samg.evaluation.runner import (
    EpsilonGreedyExperimentConfig,
    ExperimentConfig,
    load_experiment,
    run_experiment_a,
    tune_epsilon_on_dev,
)
from samg.orchestration import RunSettings


def _digest(base: ExperimentConfig, policy: EpsilonGreedyExperimentConfig,
            settings: RunSettings) -> str:
    return config_hash(base, settings.costs, settings.allocation, settings.reward, policy)


def _write_frozen(path: Path, policy: EpsilonGreedyExperimentConfig, digest: str) -> None:
    data = policy.model_copy(update={"frozen": True}).model_dump(mode="json")
    path.write_text(yaml.safe_dump(data, sort_keys=False) + f"# config_hash: {digest}\n", encoding="utf-8")


def _write_records(records, path: Path) -> None:
    metric_keys = sorted({key for row in records for key in row.metrics})
    columns = ["split", "policy", "policy_seed", "step", "scenario_id", "mission_id", "eligible", "topology",
               "applicable", "feasible", "reward", "admitted_reward", "episode_status", "learned", "warmup",
               "explored", "exploration_probability", *metric_keys]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in records:
            writer.writerow({
                "split": row.split,
                "policy": row.policy,
                "policy_seed": row.policy_seed,
                "step": row.step,
                "scenario_id": row.scenario_id,
                "mission_id": row.mission_id,
                "eligible": "|".join(arm.value for arm in row.eligible),
                "topology": row.topology.value if row.topology else "",
                "applicable": row.applicable,
                "feasible": row.feasible,
                "reward": row.reward,
                "admitted_reward": row.admitted_reward,
                "episode_status": row.episode_status.value if row.episode_status else "",
                "learned": row.learned,
                "warmup": row.warmup,
                "explored": row.explored,
                "exploration_probability": row.exploration_probability,
                **{key: row.metrics.get(key, "") for key in metric_keys},
            })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("artifacts/experiments/epsilon_greedy"))
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR)
    parser.add_argument("--all-epsilons", action="store_true",
                        help="evaluate every frozen epsilon-grid value on the same held-out missions")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    base = load_experiment(args.config_dir)
    policy_path = args.config_dir / "epsilon_greedy.yaml"
    policy_cfg = EpsilonGreedyExperimentConfig.model_validate(
        yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    )
    settings = RunSettings.load(args.config_dir)
    executor = OrchestrationExecutor(settings)

    def digest(current: EpsilonGreedyExperimentConfig) -> str:
        return _digest(base, current, settings)

    if not policy_cfg.frozen:
        print(f"Dev tuning: epsilon grid {policy_cfg.epsilon_grid}; policy seeds {policy_cfg.policy_seeds}")
        tuning = tune_epsilon_on_dev(base, executor, policy_cfg, costs=settings.costs, progress=print)
        (args.out / "epsilon_dev_tuning.json").write_text(tuning.model_dump_json(indent=2), encoding="utf-8")
        for row in tuning.results:
            print(f"  epsilon={row.epsilon:g}: dev-eval mean={row.eval_reward.mean} "
                  f"CI=[{row.eval_reward.ci95_low}, {row.eval_reward.ci95_high}] "
                  f"per-seed={row.replicate_means}")
        policy_cfg = policy_cfg.model_copy(update={"epsilon": tuning.chosen_epsilon, "frozen": True})
        frozen_hash = digest(policy_cfg)
        _write_frozen(policy_path, policy_cfg, frozen_hash)
        print(f"Frozen epsilon={policy_cfg.epsilon:g}; config_hash={frozen_hash}")
    else:
        frozen_hash = digest(policy_cfg)
        text = policy_path.read_text(encoding="utf-8")
        match = re.search(r"^# config_hash: (\w+)", text, flags=re.M)
        if not match or match.group(1) != frozen_hash:
            raise SystemExit("frozen epsilon_greedy.yaml hash mismatch; refusing held-out evaluation")
        print(f"Using frozen epsilon={policy_cfg.epsilon:g}; config_hash={frozen_hash}")

    started = time.perf_counter()
    result = run_experiment_a(
        base,
        executor,
        costs=settings.costs,
        extra_hash_configs=(settings.allocation, settings.reward),
        epsilon_greedy=policy_cfg,
        epsilon_sweep=args.all_epsilons,
        progress=print,
    )
    if result.config_hash != frozen_hash:
        raise SystemExit(f"run hash drift: {result.config_hash} != {frozen_hash}")
    suffix = "epsilon_sweep" if args.all_epsilons else "epsilon_greedy"
    (args.out / f"{suffix}_result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    _write_records(result.records, args.out / f"{suffix}_records.csv")
    print("\nHeld-out comparison (same paired scenarios; P4 averaged over policy seeds):")
    for row in result.table():
        print(f"  {row['policy']}: n={row['n']} mean={row['mean_reward']} CI={row['ci95']} "
              f"regret={row['mean_regret']} N/A={row['not_applicable']} infeasible={row['infeasible']}")
    for comparison in result.comparisons:
        print(f"  {comparison.a} - {comparison.b}: {comparison.mean_diff} "
              f"CI=[{comparison.ci95_low}, {comparison.ci95_high}] "
              f"W/L/T={comparison.wins}/{comparison.losses}/{comparison.ties} n={comparison.n_pairs}")
    for name, policy_result in result.test.items():
        if name == "P4" or name.startswith("P4@"):
            print(f"{name} exploration choices={policy_result.exploration_count}; "
                  f"exploration rate={policy_result.exploration_rate}; "
                  f"policy seeds={policy_result.policy_seed_count}")
    print(f"Wrote results to {args.out}; elapsed={time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
