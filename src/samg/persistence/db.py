"""SQLite connection and append-only schema (``db-v1``).

* ``PRAGMA foreign_keys=ON`` on every connection.
* Every table is append-only: UPDATE and DELETE are blocked by triggers.
* ``events_received`` has UNIQUE ``(mission_id, epoch, signer_id, seq)`` — the
  durable replay barrier — plus a primary key on ``event_id``.
* ``learning_events`` has a partial UNIQUE index so a policy instance can
  apply at most one update per episode (INV-08), even across restarts.
* No table stores private key material.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "db-v1"

TABLES: dict[str, str] = {
    "experiments": """
        experiment_id TEXT PRIMARY KEY,
        config_hash   TEXT NOT NULL,
        config_json   TEXT NOT NULL,
        created_at    TEXT NOT NULL""",
    "missions": """
        mission_id    TEXT NOT NULL,
        epoch         INTEGER NOT NULL,
        experiment_id TEXT REFERENCES experiments(experiment_id),
        seed          INTEGER NOT NULL,
        mission_json  TEXT NOT NULL,
        agents_json   TEXT NOT NULL,
        identities_json TEXT NOT NULL,
        PRIMARY KEY (mission_id, epoch)""",
    "graph_snapshots": """
        graph_id      TEXT PRIMARY KEY,
        mission_id    TEXT NOT NULL,
        epoch         INTEGER NOT NULL,
        topology      TEXT NOT NULL,
        graph_json    TEXT NOT NULL,
        FOREIGN KEY (mission_id, epoch) REFERENCES missions(mission_id, epoch)""",
    "topology_decisions": """
        decision_id    TEXT PRIMARY KEY,
        mission_id     TEXT NOT NULL,
        epoch          INTEGER NOT NULL,
        policy_instance TEXT NOT NULL,
        policy_kind    TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        topology       TEXT,
        decision_json  TEXT NOT NULL,
        FOREIGN KEY (mission_id, epoch) REFERENCES missions(mission_id, epoch)""",
    "allocation_plans": """
        plan_id      TEXT PRIMARY KEY,
        decision_id  TEXT NOT NULL REFERENCES topology_decisions(decision_id),
        feasible     INTEGER NOT NULL CHECK (feasible IN (0, 1)),
        solver       TEXT NOT NULL,
        plan_json    TEXT NOT NULL""",
    "outcomes": """
        outcome_id   TEXT PRIMARY KEY,
        plan_id      TEXT NOT NULL REFERENCES allocation_plans(plan_id),
        seed         INTEGER NOT NULL,
        outcome_json TEXT NOT NULL""",
    "events_received": """
        event_id     TEXT PRIMARY KEY,
        mission_id   TEXT NOT NULL,
        epoch        INTEGER NOT NULL,
        signer_id    TEXT NOT NULL,
        seq          INTEGER NOT NULL,
        kind         TEXT NOT NULL,
        event_type   TEXT NOT NULL,
        task_id      TEXT,
        key_id       TEXT NOT NULL,
        signature    TEXT NOT NULL,
        event_json   TEXT NOT NULL,
        UNIQUE (mission_id, epoch, signer_id, seq)""",
    "event_decisions": """
        decision_id  TEXT PRIMARY KEY,
        event_id     TEXT NOT NULL,
        mission_id   TEXT NOT NULL,
        epoch        INTEGER NOT NULL,
        signer_id    TEXT NOT NULL,
        status       TEXT NOT NULL,
        reason_codes_json TEXT NOT NULL,
        decision_json TEXT NOT NULL,
        raw_event_json TEXT NOT NULL""",
    "episodes_trusted": """
        episode_id   TEXT PRIMARY KEY,
        mission_id   TEXT NOT NULL,
        epoch        INTEGER NOT NULL,
        topology     TEXT NOT NULL,
        status       TEXT NOT NULL CHECK (status = 'ADMITTED'),
        reward       REAL NOT NULL CHECK (reward >= 0 AND reward <= 1),
        episode_json TEXT NOT NULL""",
    "episodes_quarantined": """
        episode_id   TEXT PRIMARY KEY,
        mission_id   TEXT NOT NULL,
        epoch        INTEGER NOT NULL,
        topology     TEXT NOT NULL,
        status       TEXT NOT NULL CHECK (status IN ('PROVISIONAL', 'REJECTED')),
        reason_codes_json TEXT NOT NULL,
        episode_json TEXT NOT NULL""",
    "learning_events": """
        row_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id        TEXT NOT NULL,
        policy_instance TEXT NOT NULL,
        policy_kind     TEXT NOT NULL,
        episode_id      TEXT NOT NULL,
        topology        TEXT NOT NULL,
        status          TEXT NOT NULL,
        reward_source   TEXT NOT NULL,
        reward          REAL,
        applied_at      TEXT,
        rejection_reason TEXT,
        event_json      TEXT NOT NULL,
        CHECK ((applied_at IS NULL) <> (rejection_reason IS NULL))""",
    "policy_state": """
        snapshot_id     TEXT PRIMARY KEY,
        policy_instance TEXT NOT NULL,
        policy_kind     TEXT NOT NULL,
        policy_version  TEXT NOT NULL,
        state_json      TEXT NOT NULL,
        created_at      TEXT NOT NULL""",
    "evaluation_runs": """
        run_id        TEXT PRIMARY KEY,
        experiment_id TEXT REFERENCES experiments(experiment_id),
        split         TEXT NOT NULL,
        policy_kind   TEXT NOT NULL,
        seed          INTEGER NOT NULL,
        metrics_json  TEXT NOT NULL,
        created_at    TEXT NOT NULL""",
}

INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_learning_applied_once "
    "ON learning_events(policy_instance, episode_id) WHERE applied_at IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_event_decisions_event ON event_decisions(event_id)",
    "CREATE INDEX IF NOT EXISTS ix_learning_events_episode ON learning_events(episode_id)",
)


def _append_only_triggers(table: str) -> list[str]:
    return [
        f"CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE ON {table} "
        f"BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END",
        f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} "
        f"BEGIN SELECT RAISE(ABORT, 'append-only: {table}'); END",
    ]


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a connection with foreign keys on and the schema applied (idempotent)."""
    conn = sqlite3.connect(str(path), isolation_level=None)  # explicit transactions only
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    apply_schema(conn)
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN")
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_meta (version TEXT PRIMARY KEY)")
        conn.execute("INSERT OR IGNORE INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
        for name, body in TABLES.items():
            conn.execute(f"CREATE TABLE IF NOT EXISTS {name} ({body})")
            for stmt in _append_only_triggers(name):
                conn.execute(stmt)
        for stmt in INDEXES:
            conn.execute(stmt)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
