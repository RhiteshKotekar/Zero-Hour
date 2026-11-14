"""SQLite schema: append-only, durable replay barrier, INV-08, no private keys."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from samg.assurance.freshness import FreshnessGuard
from samg.assurance.identity import build_identities
from samg.assurance.signatures import sign_with_ring
from samg.domain import (
    AgentEvent,
    EpisodeRecord,
    EpisodeStatus,
    EventDecision,
    EventStatus,
    EventType,
    IdentityRole,
    LearningEvent,
    ReasonCode,
    RewardSource,
    TopologyName,
)
from samg.persistence.db import TABLES, connect
from samg.persistence.repositories import DbSeenStore, DuplicateRecord, Repository

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _signed_claim(seq: int = 0, event_id: str = "e0") -> AgentEvent:
    registry, ring = build_identities(7, {"A1": IdentityRole.AGENT})
    identity = registry.by_identity_id("A1")
    assert identity
    return sign_with_ring(
        AgentEvent(event_id=event_id, mission_id="m", epoch=1, seq=seq, event_type=EventType.TASK_COMPLETE_CLAIM,
                   task_id="T1", issued_at=T0, key_id=identity.key_id, agent_id="A1"),
        ring,
    )


def _learning(status: EpisodeStatus = EpisodeStatus.ADMITTED, reward: float | None = 0.6) -> LearningEvent:
    return LearningEvent(event_id="le", episode_id="ep", decision_id="d", topology=TopologyName.DISTRIBUTED,
                         feature_schema_version="ctx-v1", context=(1.0, 0.1), reward=reward,
                         reward_source=RewardSource.ACP_RECOMPUTED, status=status)


def test_schema_has_no_private_key_columns() -> None:
    conn = connect()
    for table in TABLES:
        cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
        assert not [c for c in cols if "private" in c.lower() or c.lower() in {"secret", "seed_bytes"}]
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_append_only_blocks_update_and_delete() -> None:
    repo = Repository(connect())
    repo.add_received_event(_signed_claim())
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        repo.conn.execute("UPDATE events_received SET seq = 9")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        repo.conn.execute("DELETE FROM events_received")


def test_duplicate_dedupe_key_rejected_by_db() -> None:
    repo = Repository(connect())
    repo.add_received_event(_signed_claim(seq=0, event_id="e0"))
    with pytest.raises(DuplicateRecord):
        repo.add_received_event(_signed_claim(seq=0, event_id="e1"))  # same (m, 1, A1, 0)
    with pytest.raises(DuplicateRecord):
        repo.add_received_event(_signed_claim(seq=1, event_id="e0"))  # same event id


def test_restart_keeps_replay_protection(tmp_path: Path) -> None:
    path = tmp_path / "samg.db"
    claim = _signed_claim()

    def guard(repo: Repository) -> FreshnessGuard:
        return FreshnessGuard({"m": 1}, timedelta(seconds=5), timedelta(seconds=300), seen=DbSeenStore(repo))

    first = Repository(connect(path))
    g = guard(first)
    assert g.check(claim, T0) is None
    g.record(claim)
    first.conn.close()

    second = Repository(connect(path))
    verdict = guard(second).check(claim, T0)
    assert verdict is not None and verdict.reason is ReasonCode.DUPLICATE_EVENT_ID
    replay = _signed_claim(event_id="e-new")
    verdict = guard(second).check(replay, T0)
    assert verdict is not None and verdict.reason is ReasonCode.DUPLICATE_SEQUENCE


def test_learning_events_applied_once_per_instance() -> None:
    repo = Repository(connect())
    ev = _learning()
    repo.add_learning_event(ev, policy_instance="S2", policy_kind="P3", applied=True)
    with pytest.raises(DuplicateRecord):
        repo.add_learning_event(ev, policy_instance="S2", policy_kind="P3", applied=True)
    # attempts are always recordable, and other instances are independent
    repo.add_learning_event(ev, policy_instance="S2", policy_kind="P3", applied=False,
                            rejection_reason=ReasonCode.DUPLICATE_EPISODE)
    repo.add_learning_event(ev, policy_instance="S1", policy_kind="S1", applied=True)
    assert repo.applied_episodes("S2") == {"ep"}
    assert repo.count("learning_events", "applied_at IS NOT NULL") == 2
    with pytest.raises(ValueError):
        repo.add_learning_event(ev, policy_instance="X", policy_kind="P3", applied=True,
                                rejection_reason=ReasonCode.INELIGIBLE_STATUS)


def test_episodes_split_by_status() -> None:
    repo = Repository(connect())
    common = dict(mission_id="m", epoch=1, topology_decision_id="d", topology=TopologyName.HIERARCHICAL, plan_id="p")
    repo.add_episode(EpisodeRecord(episode_id="a", status=EpisodeStatus.ADMITTED, reward=0.4,
                                   reward_schema_version="rew-v1", **common))
    repo.add_episode(EpisodeRecord(episode_id="q", status=EpisodeStatus.PROVISIONAL,
                                   reason_codes=(ReasonCode.NO_WITNESS_EVIDENCE,), **common))
    assert repo.count("episodes_trusted") == 1 and repo.count("episodes_quarantined") == 1


def test_event_decision_keeps_raw_duplicate_for_audit() -> None:
    repo = Repository(connect())
    claim = _signed_claim()
    for i, status in enumerate([EventStatus.AUTHENTICATED, EventStatus.DUPLICATE]):
        repo.add_event_decision(
            EventDecision(decision_id=f"ed{i}", event_id=claim.event_id, mission_id="m", epoch=1,
                          signer_id="A1", event_type=claim.event_type, status=status,
                          reason_codes=() if i == 0 else (ReasonCode.DUPLICATE_EVENT_ID,)),
            claim,
        )
    rows = repo.conn.execute("SELECT status, raw_event_json FROM event_decisions ORDER BY rowid").fetchall()
    assert [r["status"] for r in rows] == ["AUTHENTICATED", "DUPLICATE"]
    assert json.loads(rows[1]["raw_event_json"])["signature"] == claim.signature


def test_policy_snapshot_roundtrip() -> None:
    from samg.learning import LinUCBPolicy

    repo = Repository(connect())
    p = LinUCBPolicy(seed=2)
    repo.add_policy_snapshot(snapshot_id="s0", policy_instance="S2", state=p.snapshot())
    raw = repo.latest_policy_state("S2")
    assert raw is not None
    restored = LinUCBPolicy.from_snapshot(json.loads(raw))
    assert restored.snapshot() == p.snapshot()
