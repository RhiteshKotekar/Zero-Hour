"""Multi-seed SAMG-vs-baseline comparison over W1-W6 and the ladder B0 -> B1 -> B2 -> SAMG (D042).

    python -m samg.experiments.compare --scenarios W1 W5 --seeds 1001 1002 1003
    python -m samg.experiments.compare --all --n-seeds 30 --doc docs/RESULTS_BASELINE.md

Writes ``artifacts/experiments/baseline/<run-name>/results.json`` (manifest, every row, summary)
and ``rows.csv``; ``--doc`` also renders the measured tables to Markdown. Nothing is tuned here:
the dispatcher weights, model v2 values and seeds are fixed before running.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from samg.baseline import run_metrics
from samg.baseline.dispatcher import CONFIG_PATH as BASELINE_CONFIG
from samg.baseline.execution import run_warehouse_baseline, run_warehouse_samg
from samg.evaluation.metrics import paired_comparison, summarize
from samg.experiments.scenarios import DEFAULT_SEEDS, LADDER, MODEL_V2, RUNGS, SCENARIOS, Rung, with_rung
from samg.twin.layout import load_config

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "artifacts" / "experiments" / "baseline"

# metric -> better direction (None = context-dependent, reported without a direction)
METRICS: dict[str, str | None] = {
    "truly_fulfilled_rate": "max", "order_completion_rate": "max", "orders_shipped_incomplete": "min",
    "corrupted_tasks": "min", "false_claims_accepted": "min", "false_claims": None,
    "avg_fulfilment_s": "min", "avg_task_latency_s": "min", "makespan_s": "min", "robot_utilization": None,
    "travel_m": "min", "congestion_events": "min", "congestion_s": "min", "task_failures": "min",
    "retransmissions": "min", "handoff_hops": "min", "runtime_s": "min",
}
STEPS = (("B1", "B0", "optimiser"), ("B2", "B1", "witness & evidence gate"), ("SAMG", "B2", "adaptive topology"),
         ("SAMG", "B0", "SAMG overall"), ("SAMG-cold", "SAMG", "cold vs warm start"))


def run_one(scenario: str, rung: Rung, seed: int, cfg: dict[str, Any]) -> dict[str, Any]:
    spec = with_rung(SCENARIOS[scenario].spec(seed, cfg), rung)
    t0 = time.perf_counter()
    if rung.mode == "baseline":
        run = run_warehouse_baseline(spec, cfg, sim=MODEL_V2, planner=rung.planner)
    else:
        run = run_warehouse_samg(spec, cfg, MODEL_V2)
    runtime = time.perf_counter() - t0
    k = run_metrics(run)
    row = {"scenario": scenario, "rung": rung.name, "seed": seed, "runtime_s": runtime,
           "truly_fulfilled_rate": (k["orders_truly_fulfilled"] / k["orders_total"]) if k["orders_total"] else None}
    row.update({m: k.get(m) for m in METRICS if m not in row})
    row.update(orders_total=k["orders_total"], orders_truly_fulfilled=k["orders_truly_fulfilled"],
               topologies=k.get("topologies"))
    return row


def summarise(rows: list[dict[str, Any]], boot_seed: int = 7) -> dict[str, Any]:
    by: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[(r["scenario"], r["rung"])].append(r)
    out: dict[str, Any] = {}
    for (sc, rung), rs in sorted(by.items()):
        stats = {}
        for m in METRICS:
            vals = [float(r[m]) for r in rs if r[m] is not None]
            s = summarize(vals, seed=boot_seed).model_dump()
            s.update(min=min(vals) if vals else None, max=max(vals) if vals else None)
            stats[m] = s
        out.setdefault(sc, {"rungs": {}, "steps": {}})["rungs"][rung] = stats
    for sc in out:
        rows_sc = [r for r in rows if r["scenario"] == sc]
        for a, b, label in STEPS:
            per = {}
            for m in METRICS:
                va = {str(r["seed"]): float(r[m]) for r in rows_sc if r["rung"] == a and r[m] is not None}
                vb = {str(r["seed"]): float(r[m]) for r in rows_sc if r["rung"] == b and r[m] is not None}
                if va and vb:
                    per[m] = paired_comparison(a, va, b, vb, seed=boot_seed).model_dump()
            out[sc]["steps"][f"{a}-{b}"] = {"label": label, "metrics": per}
    return out


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def manifest(scenarios: list[str], rungs: list[str], seeds: list[int], cfg: dict[str, Any]) -> dict[str, Any]:
    import ortools
    twin_yaml = ROOT / "config" / "twin.yaml"
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git("rev-parse", "HEAD"), "git_dirty": bool(_git("status", "--porcelain")),
        "scenarios": {s: SCENARIOS[s].__dict__ | {"injections": [i.describe() for i in SCENARIOS[s].injections]}
                      for s in scenarios},
        "rungs": {r: RUNGS[r].__dict__ for r in rungs}, "seeds": seeds,
        "training_seed_base": cfg["learning"]["training_seed_base"], "experience": cfg["learning"]["experience"],
        "simulation_model": MODEL_V2.model_dump(),
        "baseline_config_sha256": hashlib.sha256(BASELINE_CONFIG.read_bytes()).hexdigest()[:16],
        "twin_config_sha256": hashlib.sha256(twin_yaml.read_bytes()).hexdigest()[:16] if twin_yaml.exists() else None,
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(),
                        "numpy": np.__version__, "ortools": ortools.__version__},
    }


def run(scenarios: list[str], seeds: list[int], rungs: list[str] | None = None,
        progress: bool = True) -> dict[str, Any]:
    cfg = load_config()
    base = int(cfg["learning"]["training_seed_base"])
    training = set(range(base, base + int(cfg["learning"]["experience"])))
    if training & set(seeds):
        raise ValueError(f"evaluation seeds overlap training seeds {sorted(training & set(seeds))}")
    rungs = rungs or [r.name for r in LADDER]
    man = manifest(scenarios, rungs, seeds, cfg)  # recorded before running: the code state that produced the rows
    rows = []
    for sc in scenarios:
        for seed in seeds:
            for name in rungs:
                rows.append(run_one(sc, RUNGS[name], seed, cfg))
            if progress:
                print(f"{sc} seed {seed}: done", flush=True)
    return {"manifest": man, "rows": rows, "summary": summarise(rows)}


def _fmt(s: dict[str, Any] | None, m: str) -> str:
    if not s or s.get("mean") is None:
        return "—"
    pct = m in ("truly_fulfilled_rate", "order_completion_rate", "robot_utilization")
    f = (lambda x: f"{100 * x:.1f}%") if pct else (lambda x: f"{x:.3f}" if abs(x) < 10 else f"{x:.1f}")
    ci = f" [{f(s['ci95_low'])}, {f(s['ci95_high'])}]" if s.get("ci95_low") is not None else ""
    return f"{f(s['mean'])}{ci}"


def render_markdown(result: dict[str, Any]) -> str:
    man, summ = result["manifest"], result["summary"]
    lines = ["# SAMG vs conventional baseline — measured results (W1–W6)", "",
             f"Generated {man['generated_at']} from commit `{(man['git_commit'] or '?')[:8]}`"
             f"{' (dirty tree)' if man['git_dirty'] else ''}; seeds {man['seeds'][0]}–{man['seeds'][-1]} "
             f"(n = {len(man['seeds'])}); mission model v2 with common random numbers for every rung (D041, D042). "
             "Values are means with 95% bootstrap intervals across seeds. Paired differences are per seed. "
             "Nothing was tuned on these seeds.", "",
             "Ladder: " + "; ".join(f"**{r}** = {RUNGS[r].title} ({RUNGS[r].what_it_adds})" for r in man["rungs"]),
             ""]
    key = ["truly_fulfilled_rate", "order_completion_rate", "orders_shipped_incomplete", "corrupted_tasks",
           "false_claims_accepted", "avg_fulfilment_s", "avg_task_latency_s", "makespan_s", "robot_utilization",
           "travel_m", "congestion_s", "task_failures", "retransmissions", "runtime_s"]
    for sc, data in summ.items():
        s = SCENARIOS[sc]
        lines += [f"## {sc} — {s.title}", "", s.description, "",
                  "| Metric | " + " | ".join(data["rungs"]) + " |", "|---|" + "---:|" * len(data["rungs"])]
        for m in key:
            lines.append(f"| {m} | " + " | ".join(_fmt(data["rungs"][r].get(m), m) for r in data["rungs"]) + " |")
        lines += ["", "| Paired step (per seed, first minus second) | Metric | Mean diff | 95% CI | Seeds higher/lower/tie |",
                  "|---|---|---:|---|---|"]
        for step, st in data["steps"].items():
            for m in ("truly_fulfilled_rate", "avg_fulfilment_s", "corrupted_tasks", "runtime_s"):
                c = st["metrics"].get(m)
                if c and c["mean_diff"] is not None:
                    ci = f"[{c['ci95_low']:+.4f}, {c['ci95_high']:+.4f}]" if c["ci95_low"] is not None else "—"
                    lines.append(f"| {step} ({st['label']}) | {m} | {c['mean_diff']:+.4f} | {ci} | "
                                 f"{c['wins']}/{c['losses']}/{c['ties']} |")
        lines.append("")
    lines += ["## Notes", "",
              "- `truly_fulfilled_rate` counts an order only if every one of its tasks really happened (ground truth). "
              "`order_completion_rate` is the twin's KPI and over-counts for rungs that trust claims (B0, B1).",
              "- Security rows (`false_claims_accepted`, `corrupted_tasks`) are 0 for B2/SAMG by construction of the "
              "evidence gate, and the baseline has no witness; read them as the measured consequence of that "
              "capability difference.",
              "- `runtime_s` is wall-clock per mission run on the recorded machine (see manifest), not a simulated time.",
              f"- Environment: Python {man['environment']['python']}, numpy {man['environment']['numpy']}, "
              f"OR-Tools {man['environment']['ortools']}, {man['environment']['platform']}.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SAMG vs conventional baseline, multi-seed")
    ap.add_argument("--scenarios", nargs="+", choices=sorted(SCENARIOS), default=None)
    ap.add_argument("--all", action="store_true", help="all scenarios W1-W6")
    ap.add_argument("--seeds", nargs="+", type=int, default=None)
    ap.add_argument("--n-seeds", type=int, default=None, help="use seeds 1001..1000+n")
    ap.add_argument("--rungs", nargs="+", choices=list(RUNGS), default=None)
    ap.add_argument("--name", default=None, help="output folder name (default: timestamp)")
    ap.add_argument("--doc", type=Path, default=None, help="also write the Markdown results here")
    args = ap.parse_args(argv)
    scenarios = sorted(SCENARIOS) if args.all or not args.scenarios else args.scenarios
    seeds = args.seeds or (list(range(1001, 1001 + args.n_seeds)) if args.n_seeds else list(DEFAULT_SEEDS))
    result = run(scenarios, seeds, args.rungs)
    out = OUT_DIR / (args.name or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    with (out / "rows.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(result["rows"][0]))
        w.writeheader()
        w.writerows(result["rows"])
    if args.doc:
        args.doc.write_text(render_markdown(result), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
