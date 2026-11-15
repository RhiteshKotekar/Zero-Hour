"""Real ``MissionExecutor`` for Experiments A/B over ``samg.orchestration.execute_mission`` (owner: Dev A).

Per scenario, ``feasible_topologies`` is solved once and cached: the runner's
eligibility (D030) and every later execution of that scenario reuse the same
``(graph, plan)``, so CP-SAT never solves the same (scenario, topology) twice.
Simulation, witness evidence and ACP admission run on every call, so each
decision gets its own episode ID and the protected learning gate sees a fresh
event.

Nothing is persisted (no repository): the ACP uses an in-memory seen-store per
mission. Ground truth goes to ``MissionResult.ground_truth_reward`` (evaluation
only); the ACP ``EpisodeRecord`` goes to ``MissionResult.episode`` (learning only).
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

from samg.allocation import feasible_topologies
from samg.domain import AllocationPlan, CoordinationGraph, Scenario, TopologyName
from samg.evaluation.runner import MissionResult
from samg.orchestration import RunSettings, execute_mission

FeasibleEntry = tuple[list[TopologyName], dict[TopologyName, tuple[CoordinationGraph, AllocationPlan]]]


class OrchestrationExecutor:
    """``MissionExecutor`` backed by the integration pipeline (allocate -> simulate -> witness -> ACP)."""

    def __init__(self, settings: RunSettings | None = None, *, config_dir: Path | None = None,
                 use_cpsat: bool | None = None) -> None:
        self.settings = settings or RunSettings.load(config_dir, use_cpsat=use_cpsat)
        self._feasible: dict[str, FeasibleEntry] = {}
        self.timing_s: Counter[str] = Counter()
        self.calls: Counter[str] = Counter()

    def feasible(self, scenario: Scenario) -> FeasibleEntry:
        key = scenario.scenario_id
        if key not in self._feasible:
            start = time.perf_counter()
            eligible, _verdicts, plans = feasible_topologies(scenario, self.settings.costs, self.settings.allocation)
            self.timing_s["allocation"] += time.perf_counter() - start
            self.calls["allocation"] += 1
            self._feasible[key] = (list(eligible), plans)
        return self._feasible[key]

    def eligible(self, scenario: Scenario) -> list[TopologyName]:
        """D030 eligibility under this executor's own cost/allocation settings (used by the runner)."""
        return list(self.feasible(scenario)[0])

    def execute(self, scenario: Scenario, topology: TopologyName, *, seed: int, decision_id: str) -> MissionResult:
        _eligible, plans = self.feasible(scenario)
        if topology not in plans:
            return MissionResult(feasible=False, ground_truth_reward=None, detail=f"{topology.value} not eligible")
        graph, plan = plans[topology]
        start = time.perf_counter()
        ex = execute_mission(scenario, topology, self.settings, seed=seed, decision_id=decision_id,
                             graph=graph, plan=plan)
        self.timing_s["execution"] += time.perf_counter() - start
        self.calls["execution"] += 1
        metrics = ex.metrics_dict()
        if ex.feasible:
            metrics["planned_handoff_cost"] = float(plan.objective.handoff_cost)
            metrics["coordination_links"] = float(len(graph.coordination_links()))
        return MissionResult(
            feasible=ex.feasible,
            ground_truth_reward=ex.ground_truth_reward.reward,
            episode=ex.episode,
            metrics=metrics,
            detail=ex.episode.status.value,
        )

