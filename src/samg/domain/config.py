"""Typed, versioned configuration contracts (owner: Dev A for these three files).

YAML files under ``config/`` mirror these models. Defaults here equal the
committed YAML base values, so tests can run without touching the filesystem.
Every run persists ``model_dump()`` of the configs it used.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import Field, model_validator

from samg.domain.mission import SamgModel

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


class CostSetting(SamgModel):
    h0: float = Field(ge=0)
    h1: float = Field(ge=0)


class SimulationModelConfig(SamgModel):
    """Mission model v2 (D041): rules that let coordination change outcomes, not only cost.

    Absent (``TopologyCostConfig.simulation_model is None``) means model v1: every existing
    run, the CLI demo, the dashboard and the warehouse twin behave exactly as before.
    """

    version: str = "sim-v2"
    handoff_max_attempts: int = Field(
        default=2, ge=1, le=3,
        description="Attempts per handoff hop (v1 uses 3). With 2 = one retry; if every attempt is lost the "
        "dependent task is BLOCKED and later FAILED, and its dependents are blocked too.",
    )
    enforce_deadline: bool = Field(
        default=True, description="A task completing after mission.deadline_ms does not count in C.")
    relay_queue: bool = Field(
        default=True,
        description="Intermediate agents on a handoff path relay one message at a time (processed in plan order).",
    )
    keyed_randomness: bool = Field(
        default=True,
        description="Common random numbers: draws are keyed by (seed, task) and (seed, prerequisite, task, hop) "
        "instead of plan order, so two different plans for the same mission face the same luck.",
    )


V2_HOP_FAILURE_PROBABILITY = 0.05
"""Predeclared v2 per-hop loss probability (D041); fixed before any v2 result."""


class TopologyCostConfig(SamgModel):
    """Graph-derived coordination cost (brief §5.4), identical rule for every topology."""

    version: str = "topo-cost-v1"
    h0: float = Field(default=1.0, ge=0, description="Fixed cost of any cross-agent handoff.")
    h1: float = Field(default=0.5, ge=0, description="Cost per coordination hop.")
    link_cost: float = Field(
        default=0.25,
        ge=0,
        description="Per undirected coordination link maintained by the topology (D021).",
    )
    max_path_hops: int = Field(default=4, ge=1, description="Longer paths are treated as no permitted path.")
    handoff_delay_ms_per_hop: float = Field(default=120_000.0, ge=0, description="Simulated ms added per hop.")
    hop_failure_probability: float = Field(default=0.02, ge=0, lt=1, description="Per-hop message loss in the simulator.")
    distributed_max_degree: int = Field(default=3, ge=1)
    span_overhead: float = Field(
        default=0.10,
        ge=0,
        description="Span-of-control cost (D031): an agent's task durations grow by this fraction per "
        "coordination link beyond its first. 0 disables the rule.",
    )
    sensitivity: dict[str, CostSetting] = Field(
        default_factory=lambda: {
            "low": CostSetting(h0=0.5, h1=0.25),
            "base": CostSetting(h0=1.0, h1=0.5),
            "high": CostSetting(h0=2.0, h1=1.0),
        }
    )

    simulation_model: SimulationModelConfig | None = Field(
        default=None, description="None = mission model v1. Set via with_model_v2() (D041).")

    def with_model_v2(self, model: SimulationModelConfig | None = None,
                      hop_failure_probability: float = V2_HOP_FAILURE_PROBABILITY) -> TopologyCostConfig:
        """This config under mission model v2, with the predeclared v2 values unless overridden."""
        return self.model_copy(update={"simulation_model": model or SimulationModelConfig(),
                                       "hop_failure_probability": hop_failure_probability})

    def handoff_cost(self, hops: int) -> float:
        """Cost of handing work across ``hops`` coordination hops (0 hops = same agent)."""
        return 0.0 if hops == 0 else self.h0 + self.h1 * hops

    def with_setting(self, name: str) -> TopologyCostConfig:
        s = self.sensitivity[name]
        return self.model_copy(update={"h0": s.h0, "h1": s.h1})


class CpSatSettings(SamgModel):
    time_limit_s: float = Field(default=5.0, gt=0)
    num_workers: int = Field(default=1, ge=1, description="1 keeps CP-SAT deterministic.")
    random_seed: int = 0
    time_unit_ms: int = Field(default=1000, ge=1, description="Solver time unit; ms values are divided by this and rounded.")


class AllocationConfig(SamgModel):
    version: str = "alloc-v1"
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "makespan": 1.0,
            "handoff_cost": 10.0,
            "resource_use": 0.0,
            "max_agent_load": 0.25,
            "unserved_priority": 1000.0,
        }
    )
    cpsat: CpSatSettings = Field(default_factory=CpSatSettings)
    use_cpsat: bool = True

    @model_validator(mode="after")
    def _weights_known(self) -> AllocationConfig:
        expected = {"makespan", "handoff_cost", "resource_use", "max_agent_load", "unserved_priority"}
        if set(self.weights) != expected:
            raise ValueError(f"allocation weights must be exactly {sorted(expected)}")
        return self


class RewardConfig(SamgModel):
    """r = wC*C + wT*(1-T) + wR*(1-R) + wH*(1-H), clipped to [0, 1] (brief §7.2)."""

    version: str = "reward-v1"
    weights: dict[str, float] = Field(
        default_factory=lambda: {"completion": 0.65, "duration": 0.15, "resources": 0.10, "coordination": 0.10}
    )
    alternatives: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {
            "completion_heavy": {"completion": 0.75, "duration": 0.10, "resources": 0.075, "coordination": 0.075},
            "efficiency_heavy": {"completion": 0.55, "duration": 0.20, "resources": 0.10, "coordination": 0.15},
        }
    )
    failure_reward: float = Field(default=0.0, ge=0, le=1)
    failure_label: str = "INVALID_PLAN"

    @model_validator(mode="after")
    def _weights_valid(self) -> RewardConfig:
        for name, w in {"base": self.weights, **self.alternatives}.items():
            if set(w) != {"completion", "duration", "resources", "coordination"}:
                raise ValueError(f"reward weight set {name!r} has wrong keys")
            if abs(sum(w.values()) - 1.0) > 1e-9:
                raise ValueError(f"reward weight set {name!r} must sum to 1")
        return self


_C = TypeVar("_C", bound=SamgModel)


def load_config(model: type[_C], filename: str, config_dir: Path | None = None) -> _C:
    """Load ``config_dir/filename`` into ``model``; missing file -> model defaults."""
    path = (config_dir or CONFIG_DIR) / filename
    if not path.exists():
        return model()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return model.model_validate(data)


def config_hash(*configs: SamgModel) -> str:
    """Stable short hash of one or more configs, for run manifests and freezes."""
    # exclude_none: optional sections that are absent (e.g. simulation_model under model v1) do not
    # change the hash, so configs frozen before such sections existed keep their recorded hash.
    payload = json.dumps([c.model_dump(mode="json", exclude_none=True) for c in configs], sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_topology_costs(config_dir: Path | None = None) -> TopologyCostConfig:
    return load_config(TopologyCostConfig, "topology_costs.yaml", config_dir)


def load_allocation(config_dir: Path | None = None) -> AllocationConfig:
    return load_config(AllocationConfig, "allocation.yaml", config_dir)


def load_reward(config_dir: Path | None = None) -> RewardConfig:
    return load_config(RewardConfig, "reward.yaml", config_dir)
