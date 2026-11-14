"""Append-only repositories over the ``db-v1`` schema.

Payloads are stored as canonical JSON (``samg.domain.canonical``). Dev A's
mission/plan/outcome models are accepted as any Pydantic model or JSON-like
mapping, so this layer never imports Dev A's internals.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from samg.assurance.freshness import DedupeKey
from samg.domain.canonical import canonical_hash, canonical_json
from samg.domain.enums import EpisodeStatus, ReasonCode
from samg.domain.events import AgentEvent, EpisodeRecord, EventDecision, LearningEvent, WitnessEvent

JsonLike = Mapping[str, Any] | Any


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class DuplicateRecord(Exception):
    """An insert hit a UNIQUE / PRIMARY KEY constraint (e.g. a replayed event)."""


class Repository:
    """All SAMG writes and audit reads. One instance per connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.conn.execute("BEGIN")
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def _insert(self, table: str, row: Mapping[str, Any]) -> None:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        try:
            self.conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(row.values()))
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc) or "PRIMARY KEY" in str(exc):
                raise DuplicateRecord(f"{table}: {exc}") from exc
            raise

    # --- run inputs (payloads produced by Dev A) ---------------------------

    def add_experiment(self, experiment_id: str, config: JsonLike, created_at: str | None = None) -> str:
        config_hash = canonical_hash(config)
        self._insert("experiments", dict(
            experiment_id=experiment_id, config_hash=config_hash,
            config_json=canonical_json(config), created_at=created_at or _now(),
        ))
        return config_hash

    def add_mission(
        self, *, mission_id: str, epoch: int, seed: int, mission: JsonLike, agents: JsonLike,
        identities: JsonLike, experiment_id: str | None = None,
    ) -> None:
        """``identities`` must be public ``Identity`` records only (no private keys)."""
        self._insert("missions", dict(
            mission_id=mission_id, epoch=epoch, experiment_id=experiment_id, seed=seed,
            mission_json=canonical_json(mission), agents_json=canonical_json(agents),
            identities_json=canonical_json(identities),
        ))

    def add_graph_snapshot(self, *, graph_id: str, mission_id: str, epoch: int, topology: str, graph: JsonLike) -> None:
        self._insert("graph_snapshots", dict(
            graph_id=graph_id, mission_id=mission_id, epoch=epoch, topology=topology, graph_json=canonical_json(graph),
        ))

    def add_topology_decision(
        self, *, decision_id: str, mission_id: str, epoch: int, policy_instance: str, decision: Any,
    ) -> None:
        self._insert("topology_decisions", dict(
            decision_id=decision_id, mission_id=mission_id, epoch=epoch, policy_instance=policy_instance,
            policy_kind=decision.policy_kind, policy_version=decision.policy_version,
            topology=decision.topology.value if decision.topology else None,
            decision_json=canonical_json(decision),
        ))

    def add_allocation_plan(self, *, plan_id: str, decision_id: str, feasible: bool, solver: str, plan: JsonLike) -> None:
        self._insert("allocation_plans", dict(
            plan_id=plan_id, decision_id=decision_id, feasible=int(feasible), solver=solver,
            plan_json=canonical_json(plan),
        ))

    def add_outcome(self, *, outcome_id: str, plan_id: str, seed: int, outcome: JsonLike) -> None:
        self._insert("outcomes", dict(
            outcome_id=outcome_id, plan_id=plan_id, seed=seed, outcome_json=canonical_json(outcome),
        ))

    # --- events and ACP decisions -----------------------------------------

    def add_received_event(self, event: AgentEvent | WitnessEvent) -> None:
        """Store an authenticated, fresh event. Raises ``DuplicateRecord`` on replay."""
        if event.signature is None:
            raise ValueError("only signed events are stored in events_received")
        self._insert("events_received", dict(
            event_id=event.event_id, mission_id=event.mission_id, epoch=event.epoch,
            signer_id=event.signer_id, seq=event.seq, kind=event.kind,
            event_type=event.event_type.value, task_id=event.task_id, key_id=event.key_id,
            signature=event.signature, event_json=canonical_json(event),
        ))

    def add_event_decision(self, decision: EventDecision, raw_event: AgentEvent | WitnessEvent | JsonLike) -> None:
        self._insert("event_decisions", dict(
            decision_id=decision.decision_id, event_id=decision.event_id, mission_id=decision.mission_id,
            epoch=decision.epoch, signer_id=decision.signer_id, status=decision.status.value,
            reason_codes_json=canonical_json(list(decision.reason_codes)),
            decision_json=canonical_json(decision), raw_event_json=canonical_json(raw_event),
        ))

    def add_episode(self, episode: EpisodeRecord) -> None:
        """ADMITTED → ``episodes_trusted``; PROVISIONAL/REJECTED → ``episodes_quarantined``."""
        common = dict(
            episode_id=episode.episode_id, mission_id=episode.mission_id, epoch=episode.epoch,
            topology=episode.topology.value, status=episode.status.value, episode_json=canonical_json(episode),
        )
        if episode.status is EpisodeStatus.ADMITTED:
            self._insert("episodes_trusted", {**common, "reward": episode.reward})
        else:
            self._insert("episodes_quarantined", {
                **common, "reason_codes_json": canonical_json(list(episode.reason_codes)),
            })

    # --- learning ----------------------------------------------------------

    def add_learning_event(
        self, event: LearningEvent, *, policy_instance: str, policy_kind: str,
        applied: bool, rejection_reason: ReasonCode | None = None, applied_at: str | None = None,
    ) -> None:
        """Record an attempted observation. ``applied`` rows are unique per (instance, episode)."""
        if applied == (rejection_reason is not None):
            raise ValueError("exactly one of applied / rejection_reason must be given")
        self._insert("learning_events", dict(
            event_id=event.event_id, policy_instance=policy_instance, policy_kind=policy_kind,
            episode_id=event.episode_id, topology=event.topology.value, status=event.status.value,
            reward_source=event.reward_source.value, reward=event.reward,
            applied_at=(applied_at or _now()) if applied else None,
            rejection_reason=rejection_reason.value if rejection_reason else None,
            event_json=canonical_json(event),
        ))

    def add_policy_snapshot(
        self, *, snapshot_id: str, policy_instance: str, state: Mapping[str, Any], created_at: str | None = None,
    ) -> None:
        self._insert("policy_state", dict(
            snapshot_id=snapshot_id, policy_instance=policy_instance, policy_kind=state["kind"],
            policy_version=state["policy_version"], state_json=canonical_json(state),
            created_at=created_at or _now(),
        ))

    def add_evaluation_run(
        self, *, run_id: str, split: str, policy_kind: str, seed: int, metrics: JsonLike,
        experiment_id: str | None = None, created_at: str | None = None,
    ) -> None:
        self._insert("evaluation_runs", dict(
            run_id=run_id, experiment_id=experiment_id, split=split, policy_kind=policy_kind, seed=seed,
            metrics_json=canonical_json(metrics), created_at=created_at or _now(),
        ))

    # --- reads -------------------------------------------------------------

    def has_event_id(self, event_id: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM events_received WHERE event_id = ?", (event_id,)
        ).fetchone() is not None

    def has_dedupe_key(self, key: DedupeKey) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM events_received WHERE mission_id=? AND epoch=? AND signer_id=? AND seq=?", key
        ).fetchone() is not None

    def applied_episodes(self, policy_instance: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT episode_id FROM learning_events WHERE policy_instance=? AND applied_at IS NOT NULL",
            (policy_instance,),
        )
        return {r["episode_id"] for r in rows}

    def latest_policy_state(self, policy_instance: str) -> str | None:
        row = self.conn.execute(
            "SELECT state_json FROM policy_state WHERE policy_instance=? ORDER BY rowid DESC LIMIT 1",
            (policy_instance,),
        ).fetchone()
        return row["state_json"] if row else None

    def count(self, table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
        if not table.isidentifier():
            raise ValueError("bad table name")
        sql = f"SELECT COUNT(*) FROM {table}" + (f" WHERE {where}" if where else "")
        return int(self.conn.execute(sql, params).fetchone()[0])


class DbSeenStore:
    """``SeenStore`` backed by ``events_received`` — survives restarts."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def has_event_id(self, event_id: str) -> bool:
        return self.repo.has_event_id(event_id)

    def has_dedupe_key(self, key: DedupeKey) -> bool:
        return self.repo.has_dedupe_key(key)

    def add(self, event: AgentEvent | WitnessEvent) -> None:
        self.repo.add_received_event(event)
