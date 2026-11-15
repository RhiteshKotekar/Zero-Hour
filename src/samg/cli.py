"""Command-line entry point (owner: Dev B). Minimal integration version.

    python -m samg demo
    python -m samg run --seed 7 --policy linucb --mode protected
    python -m samg run --seed 7 --policy linucb --mode vulnerable --attack

Output is deterministic for a given seed; wall-clock runtimes are never printed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from samg.demo import DemoConfig, run_demo, run_one
from samg.domain import PolicyMode, TopologyName

POLICIES = ("linucb", "ucb1", "fixed-h", "fixed-f", "fixed-d")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="samg", description="SAMG controlled-simulation vertical slice")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="clean run, learning stream and signed false-report attack")
    demo.add_argument("--judge-seed", type=int, default=DemoConfig.judge_seed)
    demo.add_argument("--alpha", type=float, default=DemoConfig.alpha)
    demo.add_argument("--n-learn", type=int, default=DemoConfig.n_learn)
    demo.add_argument("--n-attack", type=int, default=DemoConfig.n_attack)
    demo.add_argument("--greedy", action="store_true", help="use the greedy allocator instead of CP-SAT")

    run = sub.add_parser("run", help="one mission in full detail")
    run.add_argument("--seed", type=int, default=7)
    run.add_argument("--policy", choices=POLICIES, default="linucb")
    run.add_argument("--mode", choices=("protected", "vulnerable"), default="protected")
    run.add_argument("--scenario", choices=("judge", "generated"), default="judge")
    run.add_argument("--alpha", type=float, default=DemoConfig.alpha)
    run.add_argument("--attack", action="store_true", help="the compromised agent signs a false reward claim")
    run.add_argument("--compromised", default="A4")
    run.add_argument("--prefer", choices=[t.value for t in TopologyName], default=TopologyName.FUNCTIONAL_CELL.value)
    run.add_argument("--greedy", action="store_true", help="use the greedy allocator instead of CP-SAT")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "demo":
        if args.n_learn < 4 or args.n_attack < 1:
            parser.error("--n-learn must be >= 4 and --n-attack >= 1")
        run_demo(print, DemoConfig(judge_seed=args.judge_seed, alpha=args.alpha, n_learn=args.n_learn,
                                   n_attack=args.n_attack, use_cpsat=not args.greedy))
        return 0
    mode = PolicyMode.VULNERABLE if args.mode == "vulnerable" else PolicyMode.PROTECTED
    if mode is PolicyMode.VULNERABLE and args.policy != "linucb":
        parser.error("--mode vulnerable is only defined for --policy linucb (VulnerableLinUCB, Experiment C)")
    run_one(print, seed=args.seed, policy_kind=args.policy, mode=mode, scenario_kind=args.scenario,
            alpha=args.alpha, attack=args.attack, compromised=args.compromised,
            preferred=TopologyName(args.prefer), use_cpsat=not args.greedy)
    return 0


if __name__ == "__main__":
    sys.exit(main())
