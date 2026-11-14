"""Scenario construction (owner: Dev A).

``judge_scenario()`` is the hand-written inspect-diagnose-repair-recover mission
from brief §3.2-3.3, used for demos and as a test oracle. The seeded generator
for evaluation (brief §3.4) is added in Phase 1.
"""

from __future__ import annotations

from samg.domain import AgentProfile, CapabilityMatch, MissionSpec, Scenario, TaskSpec

JUDGE_SCENARIO_ID = "judge-inspect-repair-v1"


def _agent(agent_id: str, role: str, caps: list[str], max_tasks: int, budget: float, *,
           coord: bool = False, lead: bool = False) -> AgentProfile:
    return AgentProfile(
        agent_id=agent_id,
        role=role,
        capabilities=caps,
        max_tasks=max_tasks,
        resource_budget=budget,
        can_coordinate=coord,
        is_mission_lead=lead,
        public_key_id=f"key-{agent_id}",
    )


def judge_agents() -> tuple[AgentProfile, ...]:
    """Agents A0-A5 (brief §3.2). Budgets/limits are illustrative scenario inputs."""
    return (
        _agent("A0", "lead", ["approval", "prioritisation", "supervision"], 0, 0.0, coord=True, lead=True),
        _agent("A1", "inspection", ["inspection", "survey"], 3, 6.0),
        _agent("A2", "transport", ["recovery", "transport"], 3, 12.0),
        _agent("A3", "transport", ["inspection", "transport"], 3, 10.0),
        _agent("A4", "maintenance", ["diagnostics", "repair", "verification"], 4, 12.0, coord=True),
        _agent("A5", "logistics", ["inventory", "resource_coordination"], 2, 8.0, coord=True),
    )


def judge_tasks() -> tuple[TaskSpec, ...]:
    """Tasks T1-T8 (brief §3.3). "a / b" capabilities are any-of."""
    any_ = CapabilityMatch.ANY
    rows = [
        # id, name, caps, match, duration, demand, priority, deps
        ("T1", "Survey the area", ["inspection", "survey"], any_, 20, 2, 1.0, []),
        ("T2", "Inspect the asset", ["inspection"], CapabilityMatch.ALL, 30, 3, 1.0, ["T1"]),
        ("T3", "Diagnose the fault", ["diagnostics"], CapabilityMatch.ALL, 25, 2, 1.5, ["T2"]),
        ("T4", "Identify the replacement component", ["diagnostics", "inventory"], any_, 15, 1, 1.0, ["T3"]),
        ("T5", "Transport the component", ["transport"], CapabilityMatch.ALL, 40, 5, 1.0, ["T4"]),
        ("T6", "Repair the asset", ["repair"], CapabilityMatch.ALL, 45, 6, 2.0, ["T5"]),
        ("T7", "Verify the repair", ["verification"], CapabilityMatch.ALL, 20, 2, 2.0, ["T6"]),
        ("T8", "Recover equipment and close the mission", ["recovery", "transport"], any_, 30, 4, 1.0, ["T7"]),
    ]
    return tuple(
        TaskSpec(task_id=tid, name=name, required_capabilities=caps, capability_match=match,
                 duration=dur, resource_demand=demand, priority=prio, dependencies=deps)
        for tid, name, caps, match, dur, demand, prio, deps in rows
    )


def judge_scenario(seed: int = 0) -> Scenario:
    tasks = judge_tasks()
    serial = sum(t.duration for t in tasks)
    mission = MissionSpec(
        mission_id="M-judge-001",
        scenario_id=JUDGE_SCENARIO_ID,
        tasks=tasks,
        deadline=round(serial * 1.5, 1),
        generator_version="manual-judge-v1",
        family="judge_demo",
    )
    return Scenario(scenario_id=JUDGE_SCENARIO_ID, seed=seed, mission=mission, agents=judge_agents())
