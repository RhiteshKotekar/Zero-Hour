"""Export side-by-side replays: SAMG vs the conventional baseline on identical missions (D042).

For each twin preset, runs both modes with the same RunSpec (same seed, orders, robots, layout,
injections) and writes, under ``web/public/replays/compare/``:

* ``<preset>.samg.json`` / ``<preset>.baseline.json``: twin states (the ``twin-state`` contract the
  3D scene renders), one per mode;
* ``<preset>.metrics.json``: ``samg.baseline.run_metrics`` for both modes plus a manifest
  (seed, preset, injections, git commit, simulator model, environment);
* ``index.json``: the list of exported presets.

Usage: ``python scripts/export_compare_replays.py [--presets judge_demo clean rush] [--model v1|v2]``.
Numbers shown on the compare page come only from these files.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from samg.baseline import run_metrics, run_mode
from samg.domain.config import SimulationModelConfig
from samg.twin import preset
from samg.twin.adapter import build_state
from samg.twin.layout import load_config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "replays" / "compare"
CAPABILITIES = {
    "samg": {"coordination": "Secure adaptive mission graph", "topology_selection": "LinUCB (adaptive)",
             "allocator": "CP-SAT", "witness": True, "evidence_gate": True, "learning": True},
    "baseline": {"coordination": "Centralized greedy dispatcher", "topology_selection": "None (fixed controller star)",
                 "allocator": "Greedy (travel + queue + execution)", "witness": False, "evidence_gate": False,
                 "learning": False},
}


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--presets", nargs="+", default=None, help="twin presets (default: all in config/twin.yaml)")
    ap.add_argument("--model", choices=("v1", "v2"), default="v1", help="simulator model applied to both modes")
    args = ap.parse_args(argv)
    cfg = load_config()
    presets = args.presets or sorted(cfg["scenarios"])
    sim = SimulationModelConfig() if args.model == "v2" else None
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for name in presets:
        spec = preset(cfg, name)
        metrics = {}
        for mode in ("samg", "baseline"):
            run = run_mode(spec, mode, cfg, sim)
            state = build_state(run)
            (OUT / f"{name}.{mode}.json").write_text(json.dumps(state, separators=(",", ":"), default=str),
                                                     encoding="utf-8")
            metrics[mode] = run_metrics(run)
        manifest = {
            "preset": name, "label": cfg["scenarios"][name].get("label", name), "seed": spec.seed,
            "injections": [i.describe() for i in spec.injections], "model": args.model,
            "git_commit": _git_commit(), "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "python": sys.version.split()[0], "platform": platform.platform(),
        }
        (OUT / f"{name}.metrics.json").write_text(
            json.dumps({"manifest": manifest, "capabilities": CAPABILITIES, "metrics": metrics}, indent=1,
                       default=str), encoding="utf-8")
        index.append({"preset": name, "label": manifest["label"], "seed": spec.seed,
                      "injections": manifest["injections"]})
        print(f"{name}: samg vs baseline written")
    (OUT / "index.json").write_text(json.dumps({"model": args.model, "presets": index}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
