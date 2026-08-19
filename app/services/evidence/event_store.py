"""V2 Learning Event Store - SQLite append-only store.

Event immutability: events are INSERT-only.
Correction model: void/supersede via void_event_id reference.
"""

import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Generator
from contextlib import contextmanager

from .event_schema import LearningEvent, validate_event, SCHEMA_VERSION

DEFAULT_DB_PATH = "data/v2_events.db"

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS learning_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    actor_id TEXT NOT NULL,
    verb TEXT NOT NULL,
    object_id TEXT NOT NULL,
    result_json TEXT,
    context_json TEXT,
    evidence_json TEXT,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    source TEXT NOT NULL DEFAULT 'direct',
    schema_version TEXT NOT NULL,
    processor_version TEXT NOT NULL DEFAULT '1.0',
    void_event_id TEXT,
    idempotency_key TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_events_actor ON learning_events(actor_id);
CREATE INDEX IF NOT EXISTS idx_events_ability ON learning_events(verb);
CREATE INDEX IF NOT EXISTS idx_events_occurred ON learning_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_source ON learning_events(source);
"""


class EventStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA_DDL)

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def insert_event(self, event: LearningEvent, idempotency_key: str = "") -> bool:
        """Insert an event. Returns True if inserted, False if already exists (idempotent)."""
        errors = validate_event(event)
        if errors:
            raise ValueError(f"Event validation failed: {errors}")

        with self._conn() as conn:
            if idempotency_key:
                existing = conn.execute(
                    "SELECT id FROM learning_events WHERE idempotency_key = ?",
                    (idempotency_key,)
                ).fetchone()
                if existing:
                    return False
            try:
                conn.execute("""
                    INSERT INTO learning_events
                    (event_id, actor_id, verb, object_id, result_json, context_json,
                     evidence_json, occurred_at, source, schema_version, processor_version, idempotency_key)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id, event.actor_id, event.verb, event.object_id,
                    json.dumps(event.result, ensure_ascii=False) if event.result else None,
                    json.dumps(event.context.to_dict() if hasattr(event.context, 'to_dict') else event.context, ensure_ascii=False, default=str) if event.context else None,
                    json.dumps(event.evidence.to_dict() if hasattr(event.evidence, 'to_dict') else event.evidence, ensure_ascii=False, default=str) if event.evidence else None,
                    event.occurred_at, event.source, event.schema_version,
                    event.processor_version, idempotency_key or None,
                ))
                return True
            except sqlite3.IntegrityError:
                return False

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM learning_events WHERE event_id = ? AND void_event_id IS NULL",
                (event_id,)
            ).fetchone()
            return dict(row) if row else None

    def query_events(self, actor_id: str = None, verb: str = None,
                     from_time: str = None, to_time: str = None,
                     limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        conditions = ["void_event_id IS NULL"]
        params = []
        if actor_id:
            conditions.append("actor_id = ?")
            params.append(actor_id)
        if verb:
            conditions.append("verb = ?")
            params.append(verb)
        if from_time:
            conditions.append("occurred_at >= ?")
            params.append(from_time)
        if to_time:
            conditions.append("occurred_at <= ?")
            params.append(to_time)
        where = " AND ".join(conditions)
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM learning_events WHERE {where} ORDER BY occurred_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset]
            ).fetchall()
            return [dict(r) for r in rows]

    def count_events(self, actor_id: str = None) -> int:
        with self._conn() as conn:
            if actor_id:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM learning_events WHERE actor_id = ? AND void_event_id IS NULL",
                    (actor_id,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM learning_events WHERE void_event_id IS NULL"
                ).fetchone()
            return row["cnt"] if row else 0


# Singleton
_event_store: Optional[EventStore] = None

def get_event_store(db_path: str = DEFAULT_DB_PATH) -> EventStore:
    global _event_store
    if _event_store is None:
        _event_store = EventStore(db_path)
    return _event_store
