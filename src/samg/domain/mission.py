"""Mission, task, agent and scenario contracts (owner: Dev A).

All models are immutable Pydantic v2 models with ``extra="forbid"``. Set-like
fields are stored as sorted, de-duplicated tuples so that serialisation and
hashing are deterministic.
"""

from __future__ import annotations

import heapq
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from samg.domain.enums import CapabilityMatch

MISSION_SCHEMA_VERSION = "mission-v1"


class SamgModel(BaseModel):
    """Base class: strict, immutable, JSON-safe."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _sorted_unique(values: Any) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


class AgentProfile(SamgModel):
    """A simulated agent. Never contains private key material."""

    agent_id: str = Field(min_length=1)
    role: str = Field(min_length=1, description="Primary role / capability family; drives functional cells.")
    capabilities: tuple[str, ...]
    capacity: int = Field(ge=0, description="Maximum number of tasks this agent may take in one mission.")
    resource_budget: float = Field(ge=0, description="Resource units available for the mission.")
    can_coordinate: bool = False
    is_mission_lead: bool = False
    available: bool = True
    public_key_id: str = Field(min_length=1)

    _sort_caps = field_validator("capabilities", mode="before")(_sorted_unique)


class TaskSpec(SamgModel):
    """A mission task."""

    task_id: str = Field(min_length=1)
    name: str = ""
    required_capabilities: tuple[str, ...] = Field(min_length=1)
    capability_match: CapabilityMatch = CapabilityMatch.ALL
    duration_ms: float = Field(gt=0, description="Nominal execution time in simulated milliseconds.")
    resource_demand: float = Field(ge=0)
    priority_weight: float = Field(default=1.0, gt=0, description="Weight in the weighted completion fraction C.")
    mandatory: bool = True
    reward_critical: bool = True
    dependencies: tuple[str, ...] = ()

    _sort_caps = field_validator("required_capabilities", mode="before")(_sorted_unique)
    _sort_deps = field_validator("dependencies", mode="before")(_sorted_unique)

    @model_validator(mode="after")
    def _no_self_dependency(self) -> TaskSpec:
        if self.task_id in self.dependencies:
            raise ValueError(f"task {self.task_id} depends on itself")
        return self

    def is_capable(self, agent: AgentProfile) -> bool:
        """Whether ``agent`` has the capabilities this task requires."""
        caps = set(agent.capabilities)
        if self.capability_match is CapabilityMatch.ANY:
            return bool(caps.intersection(self.required_capabilities))
        return caps.issuperset(self.required_capabilities)


class MissionSpec(SamgModel):
    """A mission: a DAG of tasks with a deadline."""

    schema_version: str = MISSION_SCHEMA_VERSION
    mission_id: str = Field(min_length=1)
    epoch: int = Field(default=0, ge=0)
    scenario_id: str = ""
    tasks: tuple[TaskSpec, ...] = Field(min_length=1)
    deadline_ms: float = Field(gt=0, description="Simulated milliseconds; T is normalised against it.")
    generator_version: str = "manual"
    generator_params: dict[str, Any] = Field(default_factory=dict)
    family: str | None = Field(default=None, description="Reporting label only; never a policy feature.")

    @model_validator(mode="after")
    def _validate_dag(self) -> MissionSpec:
        ids = [t.task_id for t in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task IDs must be unique")
        known = set(ids)
        for task in self.tasks:
            missing = set(task.dependencies) - known
            if missing:
                raise ValueError(f"task {task.task_id} depends on unknown tasks {sorted(missing)}")
        if len(self.topological_order()) != len(ids):
            raise ValueError("task dependencies contain a cycle")
        return self

    def task(self, task_id: str) -> TaskSpec:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        raise KeyError(task_id)

    def dependency_edges(self) -> list[tuple[str, str]]:
        """``(prerequisite, dependent)`` pairs, sorted."""
        return sorted((dep, t.task_id) for t in self.tasks for dep in t.dependencies)

    def topological_order(self) -> list[str]:
        """Kahn's algorithm with task-ID tie-breaking (deterministic)."""
        indegree = {t.task_id: len(t.dependencies) for t in self.tasks}
        children: dict[str, list[str]] = {t.task_id: [] for t in self.tasks}
        for t in self.tasks:
            for dep in t.dependencies:
                if dep in children:
                    children[dep].append(t.task_id)
        ready = [k for k, v in indegree.items() if v == 0]
        heapq.heapify(ready)
        order: list[str] = []
        while ready:
            current = heapq.heappop(ready)
            order.append(current)
            for child in children[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    heapq.heappush(ready, child)
        return order

    def depth(self) -> dict[str, int]:
        """Longest dependency chain length ending at each task (roots have depth 0)."""
        result: dict[str, int] = {}
        for task_id in self.topological_order():
            deps = self.task(task_id).dependencies
            result[task_id] = 1 + max(result[d] for d in deps) if deps else 0
        return result


class Scenario(SamgModel):
    """Reproducible mission inputs: one mission plus its agent roster."""

    scenario_id: str = Field(min_length=1)
    seed: int
    mission: MissionSpec
    agents: tuple[AgentProfile, ...] = Field(min_length=1)
    permitted_links: tuple[tuple[str, str], ...] | None = Field(
        default=None,
        description="Directed physical/policy links (NetworkState). None = every pair may link. "
        "A topology may only use links permitted in both directions.",
    )

    @model_validator(mode="after")
    def _validate_agents(self) -> Scenario:
        ids = [a.agent_id for a in self.agents]
        if len(ids) != len(set(ids)):
            raise ValueError("agent IDs must be unique")
        if self.mission.scenario_id and self.mission.scenario_id != self.scenario_id:
            raise ValueError("mission.scenario_id must match scenario_id")
        known = set(ids)
        for a, b in self.permitted_links or ():
            if a not in known or b not in known or a == b:
                raise ValueError(f"permitted link {a}->{b} must join two different known agents")
        return self

    def link_permitted(self, a: str, b: str) -> bool:
        """Whether an undirected coordination link a<->b is physically/policy permitted."""
        if self.permitted_links is None:
            return True
        links = set(self.permitted_links)
        return (a, b) in links and (b, a) in links

    def agent(self, agent_id: str) -> AgentProfile:
        for a in self.agents:
            if a.agent_id == agent_id:
                return a
        raise KeyError(agent_id)

    def available_agents(self) -> tuple[AgentProfile, ...]:
        return tuple(a for a in self.agents if a.available)
