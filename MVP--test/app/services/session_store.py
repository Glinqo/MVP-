# -*- coding: utf-8 -*-
"""SQLite storage layer for session events, conversation memory, and ability-state cache.

Replaces (augments) the JSON-file session store with structured SQLite tables,
providing:
  - session_events: event log with indexed session_id + created_at
  - session_memory: per-session conversation summary / key_facts cache
  - ability_state_cache: incremental ability-node counters (avoids full
    event-scan on every personal_graph_state() call)
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone

from .data_loader import ROOT

DB_DIR = ROOT / "data"
DB_PATH = DB_DIR / "sessions.db"

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

_SCHEMA = [
    # ── Event log ──────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS session_events (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT    NOT NULL,
        event_id   TEXT    NOT NULL UNIQUE,
        event_type TEXT    NOT NULL DEFAULT 'unknown',
        event_data TEXT    NOT NULL DEFAULT '{}',
        created_at TEXT    NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_se_session   ON session_events(session_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_se_event_type ON session_events(event_type)",

    # ── Conversation memory per session ────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS session_memory (
        session_id       TEXT PRIMARY KEY,
        summary          TEXT    DEFAULT '',
        key_facts        TEXT    DEFAULT '[]',
        summary_span_start INTEGER DEFAULT 0,
        summary_span_end   INTEGER DEFAULT 0,
        updated_at       TEXT    DEFAULT ''
    )
    """,

    # ── Incremental ability-state counters ─────────────────────────
    """
    CREATE TABLE IF NOT EXISTS ability_state_cache (
        session_id        TEXT NOT NULL,
        ability_id        TEXT NOT NULL,
        chat_count        INTEGER DEFAULT 0,
        weak_count        INTEGER DEFAULT 0,
        improving_count   INTEGER DEFAULT 0,
        mastered_count    INTEGER DEFAULT 0,
        recommended_count INTEGER DEFAULT 0,
        last_event_id     TEXT    DEFAULT '',
        last_updated_at   TEXT    DEFAULT '',
        PRIMARY KEY (session_id, ability_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_asc_session ON ability_state_cache(session_id)",
]


def _get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _init_tables()
    return _conn


def _init_tables():
    db = _conn
    for stmt in _SCHEMA:
        db.execute(stmt)
    db.commit()


def close():
    global _conn
    if _conn:
        _conn.close()
        _conn = None


# ── Session events ─────────────────────────────────────────────────

def insert_event(session_id: str, event: dict) -> dict:
    """Write a single event into the SQLite event log."""
    db = _get_db()
    event_id = event.get("event_id", "")
    event_type = event.get("event_type", "unknown")
    event_data = json.dumps(event, ensure_ascii=False)
    created_at = event.get("created_at") or datetime.now(timezone.utc).isoformat()

    with _lock:
        db.execute(
            "INSERT OR IGNORE INTO session_events (session_id, event_id, event_type, event_data, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, event_id, event_type, event_data, created_at),
        )
        db.commit()
    return {"saved": True, "session_id": session_id, "event_id": event_id}


def query_events(session_id: str, event_type: str | None = None, limit: int = 100):
    """Read events for a session, optionally filtered by type."""
    db = _get_db()
    if event_type:
        rows = db.execute(
            "SELECT event_data FROM session_events "
            "WHERE session_id = ? AND event_type = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (session_id, event_type, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT event_data FROM session_events "
            "WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    # Return oldest-first for chronological consumption
    results = [json.loads(r[0]) for r in reversed(rows)]
    return results


# ── Conversation memory ────────────────────────────────────────────

def load_memory(session_id: str) -> dict:
    db = _get_db()
    row = db.execute(
        "SELECT summary, key_facts, summary_span_start, summary_span_end, updated_at "
        "FROM session_memory WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return {
            "summary": "",
            "key_facts": [],
            "summary_span_start": 0,
            "summary_span_end": 0,
            "updated_at": "",
        }
    return {
        "summary": row[0] or "",
        "key_facts": json.loads(row[1]) if row[1] else [],
        "summary_span_start": row[2] or 0,
        "summary_span_end": row[3] or 0,
        "updated_at": row[4] or "",
    }


def save_memory(session_id: str, summary: str = "", key_facts: list | None = None,
                span_start: int = 0, span_end: int = 0):
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    facts_json = json.dumps(key_facts or [], ensure_ascii=False)
    with _lock:
        db.execute(
            "INSERT OR REPLACE INTO session_memory "
            "(session_id, summary, key_facts, summary_span_start, summary_span_end, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, summary, facts_json, span_start, span_end, now),
        )
        db.commit()


# ── Ability state cache (incremental) ──────────────────────────────

_COUNTER_FIELDS = ["chat_count", "weak_count", "improving_count", "mastered_count", "recommended_count"]


def load_ability_cache(session_id: str) -> dict[str, dict]:
    """Return {ability_id: {chat_count, weak_count, ...}} for a session."""
    db = _get_db()
    rows = db.execute(
        "SELECT ability_id, chat_count, weak_count, improving_count, "
        "mastered_count, recommended_count, last_event_id, last_updated_at "
        "FROM ability_state_cache WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    result = {}
    for r in rows:
        result[r[0]] = {
            "chat_count": r[1] or 0,
            "weak_count": r[2] or 0,
            "improving_count": r[3] or 0,
            "mastered_count": r[4] or 0,
            "recommended_count": r[5] or 0,
            "last_event_id": r[6] or "",
            "last_updated_at": r[7] or "",
        }
    return result


def increment_ability_counter(session_id: str, ability_id: str, field: str,
                               event_id: str = ""):
    """Atomically increment one counter field for an ability node.

    Uses INSERT … ON CONFLICT DO UPDATE so no read-modify-write race is possible.
    """
    if field not in _COUNTER_FIELDS:
        raise ValueError(f"Unknown counter field: {field}")
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        db.execute(
            f"INSERT INTO ability_state_cache "
            f"(session_id, ability_id, {field}, last_event_id, last_updated_at) "
            f"VALUES (?, ?, 1, ?, ?) "
            f"ON CONFLICT(session_id, ability_id) DO UPDATE SET "
            f"{field} = {field} + 1, "
            f"last_event_id = excluded.last_event_id, "
            f"last_updated_at = excluded.last_updated_at",
            (session_id, ability_id, event_id, now),
        )
        db.commit()


def batch_increment_ability_counters(session_id: str, increments: list[tuple[str, str]],
                                      event_id: str = ""):
    """Apply multiple (ability_id, field) increments in a single transaction."""
    if not increments:
        return
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        for ability_id, field in increments:
            if field not in _COUNTER_FIELDS:
                continue
            db.execute(
                f"INSERT INTO ability_state_cache "
                f"(session_id, ability_id, {field}, last_event_id, last_updated_at) "
                f"VALUES (?, ?, 1, ?, ?) "
                f"ON CONFLICT(session_id, ability_id) DO UPDATE SET "
                f"{field} = {field} + 1, "
                f"last_event_id = excluded.last_event_id, "
                f"last_updated_at = excluded.last_updated_at",
                (session_id, ability_id, event_id, now),
            )
        db.commit()


def invalidate_ability_cache(session_id: str, ability_ids: list[str]):
    """Delete cache rows for specific abilities — next read will fall back to full recompute."""
    if not ability_ids:
        return
    db = _get_db()
    with _lock:
        placeholders = ",".join("?" for _ in ability_ids)
        db.execute(
            f"DELETE FROM ability_state_cache WHERE session_id = ? AND ability_id IN ({placeholders})",
            [session_id] + list(ability_ids),
        )
        db.commit()


def rebuild_ability_cache(session_id: str, ability_buckets: dict):
    """Overwrite the entire ability cache for one session from full-recompute data.

    ability_buckets: {ability_id: {chat_count, weak_count, improving_count, ...}}
    """
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        db.execute("DELETE FROM ability_state_cache WHERE session_id = ?", (session_id,))
        for ability_id, bucket in ability_buckets.items():
            db.execute(
                "INSERT INTO ability_state_cache "
                "(session_id, ability_id, chat_count, weak_count, improving_count, "
                "mastered_count, recommended_count, last_event_id, last_updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    ability_id,
                    bucket.get("chat", 0),
                    bucket.get("weak", 0),
                    bucket.get("improving", 0),
                    bucket.get("mastered", 0),
                    bucket.get("recommended", 0),
                    bucket.get("last_event_id", ""),
                    bucket.get("last_updated_at", now),
                ),
            )
        db.commit()
