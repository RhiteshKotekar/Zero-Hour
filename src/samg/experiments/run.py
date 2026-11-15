"""Single run: one scenario, one mode (ladder rung), one seed.

    python -m samg.experiments.run --mode baseline --scenario W5 --seed 1001
    python -m samg.experiments.run --mode samg --scenario W5 --seed 1001
    python -m samg.experiments.run --rung B1 --scenario W3 --seed 1004

``--mode samg`` = rung SAMG, ``--mode baseline`` = rung B0. Prints one standardized JSON result.
"""

from __future__ import annotations

import argparse
import json

from samg.experiments.compare import run_one
from samg.experiments.scenarios import RUNGS, SCENARIOS
from samg.twin.layout import load_config


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", choices=sorted(SCENARIOS), default="W1")
    ap.add_argument("--seed", type=int, default=1001)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--mode", choices=("samg", "baseline"), default=None)
    group.add_argument("--rung", choices=list(RUNGS), default=None)
    args = ap.parse_args(argv)
    rung = args.rung or {"samg": "SAMG", "baseline": "B0"}.get(args.mode or "samg")
    row = run_one(args.scenario, RUNGS[rung], args.seed, load_config())
    print(json.dumps(row, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
