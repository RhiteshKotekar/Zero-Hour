"""Scenario construction (owner: Dev A).

- ``judge_scenario()``: the hand-written inspect-diagnose-repair-recover mission
  from brief §3.2-3.3, used for demos and as a test oracle.
- ``generate_scenario(seed, factors)``: the seeded evaluation generator (brief §3.4).
  It generates mission inputs only; it never encodes a preferred topology.
"""

from __future__ import annotations

import itertools
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from samg.domain import AgentProfile, CapabilityMatch, MissionSpec, Scenario, TaskSpec

JUDGE_SCENARIO_ID = "judge-inspect-repair-v1"
MINUTE_MS = 60_000.0
GENERATOR_VERSION = "gen-v1"
DEFAULT_DEADLINE_FACTOR = 1.6
V2_DEADLINE_FACTOR = 1.25  # predeclared for model v2 (D041)


def _agent(agent_id: str, role: str, caps: list[str], capacity: int, budget: float, *,
           coord: bool = False, lead: bool = False, available: bool = True) -> AgentProfile:
    return AgentProfile(
        agent_id=agent_id,
        role=role,
        capabilities=caps,
        capacity=capacity,
        resource_budget=budget,
        can_coordinate=coord,
        is_mission_lead=lead,
        available=available,
        public_key_id=f"key-{agent_id}",
    )


def _lead() -> AgentProfile:
    return _agent("A0", "lead", ["approval", "prioritisation", "supervision"], 0, 0.0, coord=True, lead=True)


# --- Judge scenario (brief §3.2-3.3) ----------------------------------------

def judge_agents() -> tuple[AgentProfile, ...]:
    """Agents A0-A5 (brief §3.2). Budgets/limits are illustrative scenario inputs."""
    return (
        _lead(),
        _agent("A1", "inspection", ["inspection", "survey"], 3, 6.0),
        _agent("A2", "transport", ["recovery", "transport"], 3, 12.0),
        _agent("A3", "transport", ["inspection", "transport"], 3, 10.0),
        _agent("A4", "maintenance", ["diagnostics", "repair", "verification"], 4, 12.0, coord=True),
        _agent("A5", "logistics", ["inventory", "resource_coordination"], 2, 8.0, coord=True),
    )


def judge_tasks() -> tuple[TaskSpec, ...]:
    """Tasks T1-T8 (brief §3.3). "a / b" capabilities are any-of. Durations below are minutes."""
    any_, all_ = CapabilityMatch.ANY, CapabilityMatch.ALL
    rows = [
        # id, name, caps, match, duration, demand, priority, deps
        ("T1", "Survey the area", ["inspection", "survey"], any_, 20, 2, 1.0, []),
        ("T2", "Inspect the asset", ["inspection"], all_, 30, 3, 1.0, ["T1"]),
        ("T3", "Diagnose the fault", ["diagnostics"], all_, 25, 2, 1.5, ["T2"]),
        ("T4", "Identify the replacement component", ["diagnostics", "inventory"], any_, 15, 1, 1.0, ["T3"]),
        ("T5", "Transport the component", ["transport"], all_, 40, 5, 1.0, ["T4"]),
        ("T6", "Repair the asset", ["repair"], all_, 45, 6, 2.0, ["T5"]),
        ("T7", "Verify the repair", ["verification"], all_, 20, 2, 2.0, ["T6"]),
        ("T8", "Recover equipment and close the mission", ["recovery", "transport"], any_, 30, 4, 1.0, ["T7"]),
    ]
    return tuple(
        TaskSpec(task_id=tid, name=name, required_capabilities=caps, capability_match=match,
                 duration_ms=dur * MINUTE_MS, resource_demand=demand, priority_weight=prio, dependencies=deps)
        for tid, name, caps, match, dur, demand, prio, deps in rows
    )


def judge_scenario(seed: int = 0) -> Scenario:
    tasks = judge_tasks()
    serial = sum(t.duration_ms for t in tasks)
    mission = MissionSpec(
        mission_id="M-judge-001",
        scenario_id=JUDGE_SCENARIO_ID,
        tasks=tasks,
        deadline_ms=round(serial * 1.5, 1),
        generator_version="manual-judge-v1",
        family="judge_demo",
    )
    return Scenario(scenario_id=JUDGE_SCENARIO_ID, seed=seed, mission=mission, agents=judge_agents())


# --- Seeded evaluation generator (brief §3.4) -------------------------------

Dependency = Literal["sparse", "branching", "parallel", "deep_chain"]
CapabilityDist = Literal["homogeneous", "specialist", "clustered"]
ResourcePressure = Literal["abundant", "moderate", "constrained"]
Availability = Literal["all", "one_unavailable", "uneven"]
TaskProfile = Literal["short_balanced", "long_skewed"]

CAPABILITY_FAMILIES: dict[str, tuple[str, ...]] = {
    "inspection": ("inspection", "survey"),
    "logistics": ("inventory",),
    "maintenance": ("diagnostics", "repair", "verification"),
    "transport": ("recovery", "transport"),
}
_FAMILY_OF = {cap: fam for fam, caps in CAPABILITY_FAMILIES.items() for cap in caps}
_PRESSURE = {"abundant": 2.0, "moderate": 1.3, "constrained": 1.05}
_FACTOR_VALUES: dict[str, tuple[str, ...]] = {
    "dependency": ("sparse", "branching", "parallel", "deep_chain"),
    "capability": ("homogeneous", "specialist", "clustered"),
    "resources": ("abundant", "moderate", "constrained"),
    "availability": ("all", "one_unavailable", "uneven"),
    "task_profile": ("short_balanced", "long_skewed"),
}


class ScenarioFactors(BaseModel):
    """Independently controlled generation factors. Never passed to the policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dependency: Dependency = "branching"
    capability: CapabilityDist = "specialist"
    resources: ResourcePressure = "moderate"
    availability: Availability = "all"
    task_profile: TaskProfile = "short_balanced"

    def family(self) -> str:
        """Reporting label (brief §3.4). Derived from factors; never a policy feature."""
        if self.dependency in ("branching", "deep_chain") and self.capability == "specialist":
            return "dependency_heavy"
        if self.dependency in ("sparse", "parallel") and self.resources == "constrained":
            return "loosely_coupled"
        return "mixed"

    def key(self) -> str:
        return "/".join((self.dependency, self.capability, self.resources, self.availability, self.task_profile))


def factor_grid() -> list[ScenarioFactors]:
    """Every factor combination (216), in a fixed order."""
    names = list(_FACTOR_VALUES)
    return [ScenarioFactors(**dict(zip(names, combo, strict=True)))
            for combo in itertools.product(*(_FACTOR_VALUES[n] for n in names))]


def _dependencies(rng: np.random.Generator, n: int, kind: str) -> list[list[int]]:
    deps: list[list[int]] = [[] for _ in range(n)]
    if kind == "deep_chain":
        for i in range(1, n):
            deps[i] = [i - 1]
    elif kind == "branching":
        for i in range(1, n):
            window = list(range(max(0, i - 3), i))
            k = int(min(len(window), rng.integers(1, 3)))
            deps[i] = sorted(int(x) for x in rng.choice(window, size=k, replace=False))
    elif kind == "sparse":
        for i in range(1, n):
            if rng.random() < 0.3:
                deps[i] = [int(rng.integers(0, i))]
    else:  # parallel chains that join at the final task
        groups = int(rng.integers(2, 4))
        body = list(range(n - 1))
        chains = [body[g::groups] for g in range(groups)]
        for chain in chains:
            for prev, cur in zip(chain, chain[1:]):
                deps[cur] = [prev]
        deps[n - 1] = sorted(chain[-1] for chain in chains if chain)
    return deps


def _critical_path(durations: list[float], deps: list[list[int]]) -> float:
    finish: list[float] = []
    for i, d in enumerate(durations):
        finish.append(d + max((finish[j] for j in deps[i]), default=0.0))
    return max(finish)


def generate_scenario(seed: int, factors: ScenarioFactors | None = None, *,
                      deadline_factor: float = DEFAULT_DEADLINE_FACTOR) -> Scenario:
    """Deterministic scenario for ``(seed, factors)``.

    Guarantees: every task has a capable, available agent; capacities and budgets are
    sized from a seeded reference assignment, so the mission is feasible under
    hierarchical coordination. Resource pressure scales the budget headroom above
    that reference (abundant 2.0x, moderate 1.3x, constrained 1.05x). Other
    topologies may still be infeasible (e.g. distributed degree caps) - that is a
    measured outcome, reported as infeasibility rate.
    """
    factors = factors or ScenarioFactors()
    rng = np.random.default_rng(seed)
    n_tasks = int(rng.integers(6, 11))
    n_workers = int(rng.integers(4, 7))  # plus the mission lead A0

    # tasks
    all_caps = sorted(_FAMILY_OF)
    caps = [str(rng.choice(all_caps)) for _ in range(n_tasks)]
    deps = _dependencies(rng, n_tasks, factors.dependency)
    if factors.task_profile == "short_balanced":
        durations = [float(rng.integers(10, 26)) * MINUTE_MS for _ in range(n_tasks)]
        priorities = [1.0] * n_tasks
    else:
        durations = [float(rng.integers(25, 61)) * MINUTE_MS for _ in range(n_tasks)]
        priorities = [float(rng.choice([1.0, 1.0, 2.0, 3.0])) for _ in range(n_tasks)]
    demands = [float(rng.integers(1, 7)) for _ in range(n_tasks)]

    # agents: roles round-robin over shuffled families
    families = list(CAPABILITY_FAMILIES)
    rng.shuffle(families)
    roles = [families[i % len(families)] for i in range(n_workers)]
    agent_caps: list[set[str]] = []
    for role in roles:
        own = CAPABILITY_FAMILIES[role]
        if factors.capability == "clustered":
            chosen = set(own)
        elif factors.capability == "specialist":
            size = min(len(own), int(rng.integers(1, 3)))
            chosen = {str(c) for c in rng.choice(own, size=size, replace=False)}
        else:  # homogeneous: own family plus one or two others
            others = [f for f in CAPABILITY_FAMILIES if f != role]
            picks = rng.choice(others, size=int(rng.integers(1, 3)), replace=False)
            chosen = set(own).union(*(CAPABILITY_FAMILIES[str(p)] for p in picks))
        agent_caps.append(chosen)
    coordinate = [role == "logistics" or bool(rng.random() < 0.3) for role in roles]

    available = [True] * n_workers
    if factors.availability == "one_unavailable":
        available[int(rng.integers(0, n_workers))] = False

    # coverage repair: each required capability is held by an available worker (same family preferred)
    live = [i for i in range(n_workers) if available[i]]
    for cap in sorted(set(caps)):
        if not any(cap in agent_caps[i] for i in live):
            same_family = [i for i in live if roles[i] == _FAMILY_OF[cap]]
            agent_caps[(same_family or live)[0]].add(cap)

    # Reference assignment (feasible by construction): each task, in a seeded order, goes to the
    # capable live worker with the least reference load (ties by a seeded rank). Capacity and
    # budget are then sized from it, so the mission is solvable under hierarchical coordination
    # (every pair is <= 2 hops via the lead) for every factor setting (brief §3.4).
    rank = {i: int(r) for i, r in zip(live, rng.permutation(len(live)))}
    ref_tasks = [0] * n_workers
    ref_demand = [0.0] * n_workers
    for t in (int(x) for x in rng.permutation(n_tasks)):
        capable = [i for i in live if caps[t] in agent_caps[i]]
        chosen = min(capable, key=lambda i: (ref_demand[i], ref_tasks[i], rank[i]))
        ref_tasks[chosen] += 1
        ref_demand[chosen] += demands[t]

    # Capacity slack: uneven availability -> 0-2 spare task slots per agent, otherwise 1.
    if factors.availability == "uneven":
        slack = [int(rng.integers(0, 3)) for _ in range(n_workers)]
    else:
        slack = [1] * n_workers
    capacity = [max(ref_tasks[i] + slack[i], 1) for i in range(n_workers)]

    # Budget = reference demand x pressure; workers with no reference task get a small reserve.
    pressure = _PRESSURE[factors.resources]
    mean_demand = sum(demands) / n_tasks
    budgets = [round(ref_demand[i] * pressure if ref_demand[i] else mean_demand * (pressure - 1.0) * 2, 1)
               for i in range(n_workers)]
    for i in range(n_workers):
        budgets[i] = max(budgets[i], ref_demand[i])  # rounding never undercuts the reference plan

    agents = [_lead()]
    for i in range(n_workers):
        agents.append(_agent(f"A{i + 1}", roles[i], sorted(agent_caps[i]), capacity[i], budgets[i],
                             coord=coordinate[i], available=available[i]))

    tid = [f"T{i + 1:02d}" for i in range(n_tasks)]
    tasks = tuple(
        TaskSpec(task_id=tid[i], name=f"{caps[i]} task", required_capabilities=[caps[i]],
                 duration_ms=durations[i], resource_demand=demands[i], priority_weight=priorities[i],
                 dependencies=[tid[j] for j in deps[i]])
        for i in range(n_tasks)
    )
    # Model v2 (D041) tightens the deadline to 1.25x the critical path. The default keeps gen-v1
    # scenarios byte-identical; any other factor is a distinct generator version and scenario ID.
    version = (GENERATOR_VERSION if deadline_factor == DEFAULT_DEADLINE_FACTOR
               else f"{GENERATOR_VERSION}-deadline{deadline_factor:g}")
    scenario_id = f"{version}-{seed}-{factors.key()}"
    mission = MissionSpec(
        mission_id=f"M-{seed}-{factors.key()}" + ("" if version == GENERATOR_VERSION else "-v2dl"),
        scenario_id=scenario_id,
        tasks=tasks,
        deadline_ms=round(_critical_path(durations, deps) * deadline_factor, 1),
        generator_version=version,
        generator_params={"seed": seed, **factors.model_dump(), "n_tasks": n_tasks, "n_workers": n_workers,
                          **({} if deadline_factor == DEFAULT_DEADLINE_FACTOR else {"deadline_factor": deadline_factor})},
        family=factors.family(),
    )
    return Scenario(scenario_id=scenario_id, seed=seed, mission=mission, agents=tuple(agents))


def seed_splits(master_seed: int, n_dev: int, n_train: int, n_test: int) -> dict[str, list[int]]:
    """Disjoint dev/train/test seed lists drawn from one master seed."""
    total = n_dev + n_train + n_test
    rng = np.random.default_rng(master_seed)
    seeds = [int(s) for s in rng.permutation(10_000 + total)[:total]]
    return {"dev": seeds[:n_dev], "train": seeds[n_dev:n_dev + n_train], "test": seeds[n_dev + n_train:]}


def split_factor_combos(master_seed: int, holdout_fraction: float = 0.2) -> dict[str, list[ScenarioFactors]]:
    """Hold out a fraction of factor combinations for the test split (within the declared ranges)."""
    grid = factor_grid()
    rng = np.random.default_rng(master_seed)
    order = [int(i) for i in rng.permutation(len(grid))]
    n_hold = max(1, round(len(grid) * holdout_fraction))
    return {"seen": [grid[i] for i in sorted(order[n_hold:])],
            "held_out": [grid[i] for i in sorted(order[:n_hold])]}
