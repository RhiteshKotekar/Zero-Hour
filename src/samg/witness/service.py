"""Independent witness: signs simulator task transitions (owner: Dev B, brief §8.5).

Minimal integration version, written by the integrator for the Phase 2
vertical slice.

The witness has its own registered identity (``IdentityRole.WITNESS``) and key.
It turns each ``TaskTransition`` of the ground-truth ``ExecutionTrace`` into a
signed ``WitnessEvent``. The simulator records a finished task as
``EXECUTING -> REPORTED_COMPLETE`` (the work is done); the witness, which is the
only actor allowed to verify, signs that observation as
``EXECUTING -> VERIFIED_COMPLETE``. Every other transition is signed as-is.

Event times: ``issued_at = base_time + sim_time_ms`` so freshness checks run in
simulated time (D016), independent of wall clock.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from samg.assurance.identity import IdentityRegistry, KeyRing
from samg.assurance.signatures import sign_with_ring
from samg.domain import ExecutionTrace, TaskState, WitnessEvent

WITNESS_SERVICE_VERSION = "witness-v0-integration"


def sim_datetime(base_time: datetime, sim_time_ms: float) -> datetime:
    """Simulated wall-clock instant for a simulated millisecond offset."""
    return base_time + timedelta(milliseconds=int(round(sim_time_ms)))


def event_id(mission_id: str, epoch: int, signer_id: str, seq: int) -> str:
    """Deterministic event id shared by witness and agent events."""
    return f"{mission_id}/e{epoch}/{signer_id}/{seq}"


class WitnessService:
    """Signs observed task transitions with the witness identity's key."""

    def __init__(self, witness_id: str, registry: IdentityRegistry, ring: KeyRing) -> None:
        identity = registry.by_identity_id(witness_id)
        if identity is None:
            raise ValueError(f"witness identity {witness_id} is not registered")
        self.witness_id = witness_id
        self.key_id = identity.key_id
        self._ring = ring

    def observe(self, trace: ExecutionTrace, base_time: datetime) -> list[WitnessEvent]:
        """Signed witness events for every transition in ``trace``, in trace order, seq from 0."""
        events: list[WitnessEvent] = []
        for seq, tr in enumerate(trace.transitions):
            to_state = TaskState.VERIFIED_COMPLETE if tr.to_state is TaskState.REPORTED_COMPLETE else tr.to_state
            ms = int(round(tr.sim_time))
            unsigned = WitnessEvent(
                event_id=event_id(trace.mission_id, trace.epoch, self.witness_id, seq),
                mission_id=trace.mission_id, epoch=trace.epoch, seq=seq, task_id=tr.task_id,
                issued_at=sim_datetime(base_time, ms), key_id=self.key_id, witness_id=self.witness_id,
                from_state=tr.from_state, to_state=to_state, sim_time_ms=ms,
                payload={"agent_id": tr.agent_id, "plan_id": trace.plan_id},
            )
            events.append(sign_with_ring(unsigned, self._ring))
        return events


__all__ = ["WITNESS_SERVICE_VERSION", "WitnessService", "event_id", "sim_datetime"]
