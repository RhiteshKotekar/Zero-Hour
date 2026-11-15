"""Warehouse comparison scenarios W1-W6 and the comparison ladder (D042, BASELINE_PLAN.md).

Every scenario is a ``RunSpec`` factory of the evaluation seed: each seed gets its own seeded order
book (``twin.orders.generate_orders``, the twin's evaluation-stream generator, never the demo book),
the same faults, and mission model v2 with common random numbers applied identically to every rung.
Evaluation seeds must not overlap the twin's training seeds (``learning.training_seed_base``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from samg.domain.config import SimulationModelConfig
from samg.twin import Injection, RunSpec
from samg.twin.adapter import WarehouseEnv
from samg.twin.orders import generate_orders

DEFAULT_SEEDS = tuple(range(1001, 1011))
MODEL_V2 = SimulationModelConfig()  # predeclared v2 rules + common random numbers (D041/D042)


@dataclass(frozen=True)
class Scenario:
    name: str
    title: str
    description: str
    injections: tuple[Injection, ...] = ()
    n_min: int = 2
    n_max: int = 5

    def spec(self, seed: int, cfg: dict[str, Any], policy: str = "adaptive", experience: int | None = None) -> RunSpec:
        env = WarehouseEnv(cfg, ())
        skus = [s.sku for s in env.inventory.all() if s.stock > 0]
        orders = generate_orders(seed, skus, n_min=self.n_min, n_max=self.n_max, prefix=f"{self.name}-")
        return RunSpec(seed=seed, policy=policy, injections=self.injections, orders=tuple(orders),
                       experience=experience, scenario=self.name, label=self.title)


SCENARIOS: dict[str, Scenario] = {s.name: s for s in (
    Scenario("W1", "Normal warehouse", "Seeded order book, no faults."),
    Scenario("W2", "High congestion", "Larger order book (6-9 orders) for more concurrent tasks and aisle conflicts.",
             n_min=6, n_max=9),
    Scenario("W3", "Robot failure", "A transport robot breaks down during its first transport task.",
             (Injection("robot_failure", robot="auto:TRANSPORT"),)),
    Scenario("W4", "Communication failure", "Per-hop message loss raised to the twin's comm-failure level.",
             (Injection("comm_failure"),)),
    Scenario("W5", "Malicious agent", "A picking robot abandons a task and signs false completion and reward claims.",
             (Injection("malicious_report", robot="auto:PICK"),)),
    Scenario("W6", "Mixed stress", "High workload plus robot failure, communication failure and a malicious report.",
             (Injection("robot_failure", robot="auto:TRANSPORT"), Injection("comm_failure"),
              Injection("malicious_report", robot="auto:PICK")), n_min=6, n_max=9),
)}


@dataclass(frozen=True)
class Rung:
    name: str
    title: str
    mode: str                    # run_mode mode
    planner: str = "greedy"      # baseline planner
    policy: str = "adaptive"     # SAMG twin policy
    experience: int | None = None  # None = twin config (warm start); 0 = cold start
    what_it_adds: str = ""


LADDER: tuple[Rung, ...] = (
    Rung("B0", "Conventional baseline", "baseline", what_it_adds="greedy central dispatch, claims trusted"),
    Rung("B1", "+ CP-SAT optimiser", "baseline", planner="cpsat", what_it_adds="SAMG's optimiser, claims still trusted"),
    Rung("B2", "+ witness & evidence gate", "samg", policy="P0-H",
         what_it_adds="SAMG pipeline with a fixed controller star (no adaptation)"),
    Rung("SAMG", "SAMG (adaptive)", "samg", what_it_adds="+ LinUCB topology selection (warm start)"),
    Rung("SAMG-cold", "SAMG (adaptive, cold start)", "samg", experience=0,
         what_it_adds="LinUCB with no pre-training"),
)
RUNGS = {r.name: r for r in LADDER}


def with_rung(spec: RunSpec, rung: Rung) -> RunSpec:
    return replace(spec, policy=rung.policy, experience=rung.experience) if rung.mode == "samg" else spec


SpecFactory = Callable[[int], RunSpec]
