"""Benchmark headless topology-selection latency for trained P3 and P4 policies.

This intentionally excludes allocation, simulation, UI, and orchestration from
the timed region. Policies are first trained through the normal experiment
runner, then their real ``select`` methods are timed on held-out scenarios.

    python scripts/benchmark_policy_latency.py
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import random
import re
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from samg.context import extract_features
from samg.domain import config_hash
from samg.domain.config import CONFIG_DIR
from samg.evaluation.executor import OrchestrationExecutor
from samg.evaluation.runner import (
    EpsilonGreedyExperimentConfig,
    ExperimentConfig,
    _Runner,
    build_splits,
    load_experiment,
)
from samg.learning import make_policy
from samg.orchestration import RunSettings


def _percentile(values: list[int], percentile: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.int64), percentile))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("artifacts/experiments/epsilon_greedy"))
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR)
    parser.add_argument("--repeats", type=int, default=50,
                        help="measured decisions per held-out scenario and policy")
    parser.add_argument("--warmup", type=int, default=500,
                        help="untimed decisions per policy before collecting samples")
    args = parser.parse_args(argv)
    if args.repeats < 1 or args.warmup < 0:
        parser.error("--repeats must be positive and --warmup must be non-negative")

    args.out.mkdir(parents=True, exist_ok=True)
    base = load_experiment(args.config_dir)
    policy_cfg = EpsilonGreedyExperimentConfig.model_validate(
        yaml.safe_load((args.config_dir / "epsilon_greedy.yaml").read_text(encoding="utf-8")) or {}
    )
    policy_text = (args.config_dir / "epsilon_greedy.yaml").read_text(encoding="utf-8")
    settings = RunSettings.load(args.config_dir)
    frozen_hash = config_hash(base, settings.costs, settings.allocation, settings.reward, policy_cfg)
    recorded_hash = re.search(r"^# config_hash: (\w+)", policy_text, flags=re.M)
    if not policy_cfg.frozen or not recorded_hash or recorded_hash.group(1) != frozen_hash:
        raise SystemExit("frozen epsilon_greedy.yaml hash mismatch; refusing benchmark")
    scenarios = build_splits(base)
    executor = OrchestrationExecutor(settings)
    runner = _Runner(executor, settings.costs)
    policy_entries = []

    # Train every policy on the standard training stream, with the same real
    # allocator/simulator/ACP feedback path used by the evaluation experiment.
    train = scenarios["train"]
    print(f"Training P3 and P4 through the normal pipeline ({len(train)} training missions per seed)")
    for seed in policy_cfg.policy_seeds:
        linucb = make_policy(
            "P3", {"alpha": base.alpha, "lam": base.lam, "warmup_per_arm": base.warmup_per_arm},
            seed=seed,
        )
        for i, (scenario, held_out) in enumerate(train):
            runner.step(split="train", name=f"P3s{seed}", policy=linucb, step=i, scenario=scenario,
                        held_out=held_out, learn=True, policy_seed=seed)
        policy_entries.append(("P3-LinUCB", None, seed, linucb))
        print(f"  trained P3 seed={seed}")

    for epsilon in sorted(set(policy_cfg.epsilon_grid)):
        for seed in policy_cfg.policy_seeds:
            # Keep the runner-generated decision/event IDs below the domain's
            # 128-character limit for the longer generated scenario IDs.
            name = f"P4e{epsilon:g}s{seed}"
            policy = make_policy(
                "P4", {"epsilon": epsilon, "lam": policy_cfg.lam,
                       "warmup_per_arm": policy_cfg.warmup_per_arm}, seed=seed,
            )
            for i, (scenario, held_out) in enumerate(train):
                runner.step(split="train", name=name, policy=policy, step=i, scenario=scenario,
                            held_out=held_out, learn=True, policy_seed=seed)
            policy_entries.append(("P4-ContextualEpsilonGreedy", epsilon, seed, policy))
            print(f"  trained {name}")

    # Use actual held-out contexts and feasibility sets. Timing wraps only the
    # public policy decision call, not feature extraction or executor work.
    test_inputs = []
    for scenario, _held_out in scenarios["test"]:
        context = extract_features(scenario)
        eligible = runner.eligible(scenario)
        test_inputs.append((context.features, tuple(eligible), context.feature_schema_version))
    sample_rows: list[dict[str, object]] = []
    summaries = []
    order_rng = random.Random(base.master_seed + 9187)

    for label, epsilon, seed, policy in policy_entries:
        for i in range(args.warmup):
            context, eligible, schema = test_inputs[i % len(test_inputs)]
            policy.select(context, eligible, schema)

    # Interleave policies deterministically per input/repetition to reduce
    # systematic clock and thermal ordering bias. Each measured interval holds
    # exactly one select() call.
    values: dict[str, list[int]] = {f"{label}|{epsilon}|{seed}": []
                                    for label, epsilon, seed, _policy in policy_entries}
    index = {f"{label}|{epsilon}|{seed}": (label, epsilon, seed, policy)
             for label, epsilon, seed, policy in policy_entries}
    for repeat in range(args.repeats):
        for scenario_index, (context, eligible, schema) in enumerate(test_inputs):
            keys = list(index)
            order_rng.shuffle(keys)
            for key in keys:
                policy = index[key][3]
                started = time.perf_counter_ns()
                policy.select(context, eligible, schema)
                elapsed = time.perf_counter_ns() - started
                values[key].append(elapsed)

    for key, durations in values.items():
        label, epsilon, seed, _policy = index[key]
        row = {
            "policy": label,
            "epsilon": epsilon,
            "policy_seed": seed,
            "n_decisions": len(durations),
            "mean_ns": statistics.fmean(durations),
            "median_ns": _percentile(durations, 50),
            "p95_ns": _percentile(durations, 95),
            "p99_ns": _percentile(durations, 99),
            "std_ns": statistics.pstdev(durations),
        }
        summaries.append(row)
        sample_rows.extend({"policy": label, "epsilon": epsilon, "policy_seed": seed,
                            "sample_index": i, "latency_ns": elapsed}
                           for i, elapsed in enumerate(durations))

    aggregate_rows = []
    groups = [("P3-LinUCB", None)] + [("P4-ContextualEpsilonGreedy", epsilon)
                                     for epsilon in sorted(set(policy_cfg.epsilon_grid))]
    for label, epsilon in groups:
        pooled = [duration for key, durations in values.items()
                  if index[key][0] == label and index[key][1] == epsilon
                  for duration in durations]
        aggregate_rows.append({
            "policy": label,
            "epsilon": epsilon,
            "n_policy_seeds": len(policy_cfg.policy_seeds),
            "n_decisions": len(pooled),
            "median_ns": _percentile(pooled, 50),
            "p95_ns": _percentile(pooled, 95),
            "p99_ns": _percentile(pooled, 99),
            "mean_ns": statistics.fmean(pooled),
        })

    summary_path = args.out / "policy_latency_summary.json"
    sample_path = args.out / "policy_latency_samples.csv"
    summary_path.write_text(json.dumps({
        "config_hash": frozen_hash,
        "protocol": {
            "training_missions": len(train),
            "held_out_scenarios": len(test_inputs),
            "epsilon_grid": sorted(set(policy_cfg.epsilon_grid)),
            "policy_seeds": list(policy_cfg.policy_seeds),
            "repeats_per_scenario": args.repeats,
            "warmup_calls_per_policy": args.warmup,
            "timed_region": "one policy.select(context, eligible, schema) call",
            "excluded": ["feature extraction", "allocation", "simulation", "ACP", "frontend"],
            "clock": "time.perf_counter_ns",
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "summaries": summaries,
        "pooled_summaries": aggregate_rows,
    }, indent=2), encoding="utf-8")
    with sample_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["policy", "epsilon", "policy_seed", "sample_index", "latency_ns"])
        writer.writeheader()
        writer.writerows(sample_rows)

    print("\nSelection latency, pooled samples (nanoseconds per call; median / p95 / p99):")
    for row in aggregate_rows:
        print(f"  {row['policy']} epsilon={row['epsilon']}: "
              f"{row['median_ns']:.0f} / {row['p95_ns']:.0f} / {row['p99_ns']:.0f} ns "
              f"(n={row['n_decisions']})")
    print(f"Wrote {summary_path} and {sample_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
