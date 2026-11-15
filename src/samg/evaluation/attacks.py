"""Signed false-report attack (Experiment C, brief §9.2) (owner: Dev B).

Minimal integration version, written by the integrator for the Phase 2
vertical slice. Dev B owns the full Experiment C harness (S1/S2 metrics, FRR,
dev-seed tuning); this module only defines the deterministic attack schedule and
rewrites report drafts before they are signed.

One compromised but *authorised* agent signs, with its real registered key and
fresh sequence numbers:

* a false ``TASK_COMPLETE_CLAIM`` for each of its own tasks that did not
  complete in ground truth (if any), and
* a false after-action ``REWARD_CLAIM``: inflated when the mission ran under the
  attacker's preferred topology, deflated otherwise, so a learner that trusts
  the claim is pushed toward the preferred topology.

The claimed value is derived from the actual reward of the run and the attack
config; both are shown side by side, never a hard-coded "measured" number.
"""

from __future__ import annotations

from collections.abc import Collection

from pydantic import BaseModel, ConfigDict, Field

from samg.domain import AllocationPlan, EventType, ExecutionTrace, RewardBreakdown, TopologyName
from samg.witness.reports import ReportDraft, reward_claim_payload

ATTACK_VERSION = "attack-v0-integration"


class AttackConfig(BaseModel):
    """Frozen attack parameters. ``schedule`` holds stream indices of attacked missions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    compromised_agent: str = Field(min_length=1)
    preferred_topology: TopologyName
    inflation: float = Field(default=0.20, ge=0, le=1, description="Added to the true reward on preferred topology.")
    deflation: float = Field(default=0.30, ge=0, le=1, description="Subtracted on any other topology.")
    schedule: frozenset[int] = frozenset()
    sabotage_schedule: frozenset[int] = Field(
        default=frozenset(),
        description="Stream indices where the compromised agent also abandons its last assigned task "
        "(simulator fault injection), so its completion claim for that task is false.",
    )

    def active(self, mission_index: int) -> bool:
        return mission_index in self.schedule

    def sabotaged_task(self, mission_index: int, plan: AllocationPlan) -> str | None:
        """Task the compromised agent abandons on this mission, if any (last by planned start)."""
        if mission_index not in self.sabotage_schedule:
            return None
        own = sorted((a.start, a.task_id) for a in plan.assignments if a.agent_id == self.compromised_agent)
        return own[-1][1] if own else None

    def claimed_reward(self, topology: TopologyName, true_reward: float) -> float:
        if topology is self.preferred_topology:
            return min(1.0, true_reward + self.inflation)
        return max(0.0, true_reward - self.deflation)


def apply_attack(
    drafts: list[ReportDraft], trace: ExecutionTrace, plan: AllocationPlan, true_reward: RewardBreakdown,
    attack: AttackConfig, *, agents: Collection[str],
) -> list[ReportDraft]:
    """Return drafts with the compromised agent's false claims added (oracle-labelled ``false_claim``)."""
    agent = attack.compromised_agent
    if agent not in agents:
        raise ValueError(f"compromised agent {agent} is not part of the mission")
    end = int(round(max((t.sim_time for t in trace.transitions), default=0.0)))
    # The compromised agent's own honest after-action report is replaced, not duplicated.
    out = [d for d in drafts if not (d.agent_id == agent and d.event_type is EventType.REWARD_CLAIM)]
    for outcome in trace.outcomes:
        if outcome.agent_id == agent and not outcome.completed:
            out.append(ReportDraft(agent, EventType.TASK_COMPLETE_CLAIM, end, outcome.task_id,
                                   {"sim_time_ms": end}, false_claim=True))
    claimed = attack.claimed_reward(plan.topology, true_reward.reward)
    false_reward = true_reward.model_copy(update={"reward": claimed})
    payload = reward_claim_payload(false_reward, {})
    out.append(ReportDraft(agent, EventType.REWARD_CLAIM, end, None, payload, false_claim=True))
    return out


__all__ = ["ATTACK_VERSION", "AttackConfig", "apply_attack"]
