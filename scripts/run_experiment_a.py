"""Experiments A/B end to end: dev tuning -> freeze -> one held-out test run (brief §12.2).

Usage (from the repo root)::

    python scripts/run_experiment_a.py                 # tune on dev, freeze, run test once
    python scripts/run_experiment_a.py --ablations     # also run the §12.9 ablations (design seeds)

Phases
1. Dev: LinUCB ``alpha`` is chosen from a predeclared grid on the DEV split only
   (``runner.tune_alpha_on_dev``). Train and test missions are not touched.
2. Freeze: the chosen ``alpha`` and ``frozen: true`` are written into
   ``config/experiment.yaml`` together with the config hash (experiment + topology
   costs + allocation + reward configs). A frozen config is never retuned: if the
   file is already frozen, phase 1 is skipped and the frozen values are used.
3. Test: ``run_experiment_a`` runs once on the held-out split.

Outputs (gitignored) go to ``artifacts/experiments/``: ``dev_tuning.json``,
``experiment_a.json`` (summaries), ``experiment_a_records.csv`` (every run) and
``ablations.json``. ``docs/RESULTS.md`` is written by hand from these files.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

from samg.domain import Scenario, TopologyCostConfig, config_hash
from samg.domain.config import CONFIG_DIR
from samg.evaluation.executor import OrchestrationExecutor
from samg.evaluation.landscape import DESIGN_SEED_OFFSET, default_settings, grid_scenarios, landscape, summarize_landscape
from samg.evaluation.runner import (
    ExperimentConfig,
    ExperimentResult,
    load_experiment,
    run_experiment_a,
    tune_alpha_on_dev,
)
from samg.orchestration import RunSettings
from samg.simulation.scenarios import factor_grid, generate_scenario

ALPHA_GRID = (0.1, 0.3, 0.5, 1.0)  # predeclared before any dev result
ABLATION_SEED_OFFSET = DESIGN_SEED_OFFSET + 10_000  # design seeds, disjoint from every experiment split


def _say(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def freeze_config(path: Path, alpha: float, digest_fn) -> str:
    """Write ``alpha`` and ``frozen: true`` into the YAML (comments kept), then record the hash."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^alpha:\s*[^\s#]+", f"alpha: {alpha}", text, count=1, flags=re.M)
    text = re.sub(r"^frozen:\s*\w+", "frozen: true", text, count=1, flags=re.M)
    text = re.sub(r"^# config_hash:.*\n", "", text, flags=re.M)
    path.write_text(text, encoding="utf-8")
    digest = digest_fn()
    path.write_text(text.rstrip("\n") + f"\n# config_hash: {digest}  (experiment + topology_costs + allocation"
                    f" + reward; written at freeze)\n", encoding="utf-8")
    return digest


def write_records_csv(result: ExperimentResult, path: Path) -> None:
    metric_keys = sorted({k for r in result.records for k in r.metrics})
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["split", "policy", "step", "scenario_id", "mission_id", "family", "held_out_combo", "eligible",
                    "topology", "applicable", "feasible", "reward", "admitted_reward", "episode_status", "learned",
                    "warmup", *metric_keys])
        for r in result.records:
            w.writerow([r.split, r.policy, r.step, r.scenario_id, r.mission_id, r.family, r.held_out_combo,
                        "|".join(t.value for t in r.eligible), r.topology.value if r.topology else "",
                        r.applicable, r.feasible, r.reward, r.admitted_reward,
                        r.episode_status.value if r.episode_status else "", r.learned, r.warmup,
                        *[r.metrics.get(k, "") for k in metric_keys]])


def summary_json(result: ExperimentResult) -> dict:
    return {
        "config": result.config.model_dump(mode="json"),
        "config_hash": result.config_hash,
        "p1_topology": result.p1_topology.value,
        "table": result.table(),
        "test": {k: v.model_dump(mode="json") for k, v in result.test.items()},
        "comparisons": [c.model_dump(mode="json") for c in result.comparisons],
        "learner_updates": result.learner_updates,
        "blocked_updates": result.blocked_updates,
        "held_out_combo_test_missions": sum(1 for r in result.records if r.split == "test" and r.policy == "P0-H"
                                            and r.held_out_combo),
    }


# --- ablations (design seeds only) -------------------------------------------


def ablation_splits(n_train: int, n_test: int, seed: int) -> dict[str, list[tuple[Scenario, bool]]]:
    """Train/test missions from design seeds (>= 60 000), cycling the full factor grid."""
    grid = factor_grid()
    out: dict[str, list[tuple[Scenario, bool]]] = {}
    start = ABLATION_SEED_OFFSET + seed * 1_000
    for split, n, off in (("train", n_train, 0), ("test", n_test, 500)):
        out[split] = [(generate_scenario(start + off + i, grid[(start + off + i * 7) % len(grid)]), False)
                      for i in range(n)]
    return out


def ablation_settings(base: RunSettings) -> dict[str, RunSettings]:
    costs = base.costs
    reward = base.reward
    out: dict[str, RunSettings] = {"base": base}

    def with_costs(c: TopologyCostConfig) -> RunSettings:
        return RunSettings(costs=c, allocation=base.allocation, reward=reward, security=base.security)

    out["topology_cost_zero"] = with_costs(costs.model_copy(update={"h0": 0.0, "h1": 0.0,
                                                                    "handoff_delay_ms_per_hop": 0.0}))
    out["h_low"] = with_costs(costs.with_setting("low"))
    out["h_high"] = with_costs(costs.with_setting("high"))
    out["link_cost_0"] = with_costs(costs.model_copy(update={"link_cost": 0.0}))
    for span in (0.0, 0.05, 0.20):
        out[f"span_{span:.2f}"] = with_costs(costs.model_copy(update={"span_overhead": span}))
    for name, weights in (reward.alternatives or {}).items():
        out[f"reward_{name}"] = RunSettings(costs=costs, allocation=base.allocation,
                                            reward=reward.model_copy(update={"weights": dict(weights)}),
                                            security=base.security)
    return out


def run_ablations(cfg: ExperimentConfig, base: RunSettings, n_train: int, n_test: int) -> dict:
    splits = ablation_splits(n_train, n_test, seed=0)
    out: dict[str, dict] = {}
    for name, settings in ablation_settings(base).items():
        _say(f"ablation {name}")
        t0 = time.perf_counter()
        ex = OrchestrationExecutor(settings)
        res = run_experiment_a(cfg, ex, costs=settings.costs, splits=splits)
        cmp = {f"{c.a}-{c.b}": c.model_dump(mode="json") for c in res.comparisons}
        out[name] = {
            "p1": res.p1_topology.value,
            "mean_reward": {k: v.reward.mean for k, v in res.test.items()},
            "selection_counts": {k: v.selection_counts for k, v in res.test.items()},
            "mean_regret": {k: v.regret.mean for k, v in res.test.items()},
            "comparisons": cmp,
            "n_train": n_train, "n_test": n_test,
            "runtime_s": round(time.perf_counter() - t0, 1),
        }
    # Planned-reward landscape on the design grid (no learning), for best-topology shares.
    land = landscape(grid_scenarios(stride=2), default_settings(base.costs), allocation=base.allocation,
                     reward=base.reward)
    out["_landscape_design_grid_stride2"] = summarize_landscape(land)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config-dir", type=Path, default=CONFIG_DIR)
    ap.add_argument("--out", type=Path, default=Path("artifacts/experiments"))
    ap.add_argument("--ablations", action="store_true")
    ap.add_argument("--ablation-train", type=int, default=30)
    ap.add_argument("--ablation-test", type=int, default=20)
    ap.add_argument("--skip-main", action="store_true", help="only ablations (config must already be frozen)")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    exp_path = args.config_dir / "experiment.yaml"
    t_start = time.perf_counter()

    settings = RunSettings.load(args.config_dir)

    def digest() -> str:
        cfg = load_experiment(args.config_dir)
        return config_hash(cfg, settings.costs, settings.allocation, settings.reward)

    cfg = load_experiment(args.config_dir)
    executor = OrchestrationExecutor(settings)
    if not cfg.frozen:
        _say(f"dev tuning: alpha grid {ALPHA_GRID} on {cfg.n_dev} dev missions")
        tuning = tune_alpha_on_dev(cfg, executor, ALPHA_GRID, costs=settings.costs, progress=_say)
        (args.out / "dev_tuning.json").write_text(tuning.model_dump_json(indent=2), encoding="utf-8")
        for r in tuning.results:
            _say(f"  alpha={r.alpha}: dev-eval mean={r.eval_reward.mean} n={r.eval_reward.n} sel={r.selection_counts}")
        digest_value = freeze_config(exp_path, tuning.chosen_alpha, digest)
        _say(f"frozen alpha={tuning.chosen_alpha}, config_hash={digest_value}")
    else:
        _say("config already frozen: no retuning")
    cfg = load_experiment(args.config_dir)
    if not cfg.frozen:
        raise SystemExit("refusing to run the held-out test on an unfrozen config")
    frozen_hash = digest()

    if not args.skip_main:
        _say("held-out test run (single)")
        t0 = time.perf_counter()
        result = run_experiment_a(cfg, executor, costs=settings.costs,
                                  extra_hash_configs=(settings.allocation, settings.reward), progress=_say)
        if result.config_hash != frozen_hash:
            raise SystemExit(f"config hash drift: {result.config_hash} != {frozen_hash}")
        data = summary_json(result)
        data["runtime_s"] = {"experiment": round(time.perf_counter() - t0, 1),
                             "allocation_s": round(executor.timing_s["allocation"], 1),
                             "execution_s": round(executor.timing_s["execution"], 1),
                             "allocation_calls": executor.calls["allocation"],
                             "execution_calls": executor.calls["execution"]}
        (args.out / "experiment_a.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        (args.out / "summary_experiment_a.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        write_records_csv(result, args.out / "experiment_a_records.csv")
        for row in result.table():
            _say(f"  {row}")
        for c in result.comparisons:
            _say(f"  {c.a} - {c.b}: {c.mean_diff} CI[{c.ci95_low}, {c.ci95_high}] W/L/T {c.wins}/{c.losses}/{c.ties}")

    if args.ablations:
        abl = run_ablations(cfg, settings, args.ablation_train, args.ablation_test)
        (args.out / "ablations.json").write_text(json.dumps(abl, indent=2, default=str), encoding="utf-8")
    _say(f"done in {time.perf_counter() - t_start:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
