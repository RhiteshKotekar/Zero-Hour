"""Warehouse run specifications, failure injections and named presets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from samg.warehouse.orders import Order

INJECTION_KINDS: dict[str, str] = {
    "robot_failure": "Robot failure",
    "comm_failure": "Communication failure",
    "aisle_blockage": "Aisle blockage",
    "delayed_task": "Delayed task",
    "inventory_unavailable": "Inventory unavailable",
    "malicious_report": "Malicious report",
}
POLICY_KINDS: dict[str, str] = {
    "adaptive": "Adaptive · LinUCB (P3)",
    "ucb1": "Adaptive · UCB1, context-free (P2)",
    "P0-H": "Fixed · Hierarchical (P0-H)",
    "P0-F": "Fixed · Functional-cell (P0-F)",
    "P0-D": "Fixed · Distributed (P0-D)",
}


@dataclass(frozen=True)
class Injection:
    """A controlled fault. Each one is executed by an existing SAMG or warehouse mechanism:

    * ``robot_failure``: the robot's first task in the plan (a TRANSPORT if it has one) is a
      forced failure in SAMG execution; the robot is unavailable to later waves.
    * ``comm_failure``: SAMG's per-hop message failure probability is raised.
    * ``aisle_blockage``: the aisle is removed from the walkable grid; routes and estimates change.
    * ``delayed_task``: extra seconds on one task's SAMG execution.
    * ``inventory_unavailable``: the SKU's stock is 0; orders needing it are put on hold.
    * ``malicious_report``: ``evaluation.attacks.AttackConfig`` on the robot: it abandons its last
      task and signs false completion and reward claims with its real key.
    """

    kind: str
    robot: str | None = None
    aisle: str | None = None
    task: str | None = None
    sku: str | None = None
    delay_s: float = 60.0

    def __post_init__(self) -> None:
        if self.kind not in INJECTION_KINDS:
            raise ValueError(f"unknown injection {self.kind}")
        need = {"robot_failure": "robot", "malicious_report": "robot", "aisle_blockage": "aisle",
                "inventory_unavailable": "sku"}.get(self.kind)
        if need and getattr(self, need) is None:
            raise ValueError(f"{self.kind} needs {need}")

    def describe(self) -> str:
        detail = {"robot_failure": self.robot, "malicious_report": self.robot, "aisle_blockage": self.aisle,
                  "inventory_unavailable": self.sku, "delayed_task": f"{self.task or 'first PACK'} +{self.delay_s:.0f}s",
                  "comm_failure": "hop failure probability raised"}[self.kind]
        return f"{INJECTION_KINDS[self.kind]}: {detail}"


@dataclass(frozen=True)
class RunSpec:
    seed: int = 11
    policy: str = "adaptive"
    injections: tuple[Injection, ...] = ()
    orders: tuple[Order, ...] | None = None       # None = config order book
    experience: int | None = None                  # None = config learning.experience
    use_cpsat: bool = True
    replan: bool = True
    max_waves: int = 3
    scenario: str = "custom"
    label: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.policy not in POLICY_KINDS:
            raise ValueError(f"unknown policy {self.policy}")


def preset(cfg: dict[str, Any], name: str, **overrides: Any) -> RunSpec:
    """A named scenario from ``config/warehouse.yaml`` (``judge_demo``, ``clean``)."""
    sc = cfg["scenarios"][name]
    injections = tuple(Injection(**inj) for inj in sc.get("injections", []))
    base = dict(seed=int(sc["seed"]), policy=sc.get("policy", "adaptive"), injections=injections,
                scenario=name, label=sc.get("label", name))
    base.update(overrides)
    return RunSpec(**base)
