"""
Persistent assessment state store (SQLite).
Replaces in-memory _sessions dict with durable storage.
Keyed by: session_id + job_role + assessment_version
"""
import json
import sqlite3
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "assessments.db"


def _conn():
    """Get a database connection with WAL mode."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c


def _ensure_table():
    """Create the assessments table if it does not exist."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assessments (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                job_role TEXT NOT NULL DEFAULT 'default',
                assessment_id TEXT NOT NULL DEFAULT '',
                assessment_version TEXT NOT NULL DEFAULT '1.0.0',
                state TEXT NOT NULL DEFAULT 'not_started',
                answers_json TEXT NOT NULL DEFAULT '[]',
                result_json TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                completed_at REAL,
                UNIQUE(session_id, job_role, assessment_version)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assess_session ON assessments(session_id, job_role)")
        # Migration: add assessment_id column if missing
        try:
            conn.execute("ALTER TABLE assessments ADD COLUMN assessment_id TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.commit()


def _make_key(session_id, job_role=None, assessment_version="1.0.0"):
    """Generate a unique storage key.
    Keyed by session_id + job_role + assessment_version to allow
    multiple assessment versions per session."""
    role = job_role or "default"
    return f"{session_id}_{role}_{assessment_version}"


def load_state(session_id, job_role=None, assessment_version="1.0.0"):
    """Load assessment state from persistent storage."""
    _ensure_table()
    key = _make_key(session_id, job_role, assessment_version)
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, state, assessment_id, answers_json, result_json, created_at, updated_at, completed_at FROM assessments WHERE id = ?",
            (key,)
        ).fetchone()
    if row is None:
        return {
            "id": key,
            "session_id": session_id,
            "job_role": job_role or "default",
            "state": "not_started",
            "answers": [],
            "result": None,
            "created_at": time.time(),
            "updated_at": time.time(),
            "completed_at": None,
        }
    completed = row[1] == "completed"
    return {
        "id": row[0],
        "session_id": session_id,
        "job_role": job_role or "default",
        "assessment_id": row[2] or "",
        "assessment_version": assessment_version,
        "state": row[1],
        "completed": completed,
        "answers": json.loads(row[3] or "[]"),
        "result": json.loads(row[4]) if row[4] else None,
        "created_at": row[5],
        "updated_at": row[6],
        "completed_at": row[7],
    }

def save_state(state):
    """Persist assessment state. Creates or updates."""
    _ensure_table()
    # Normalize key from state fields, do not trust state["id"]
    session_id = state.get("session_id", "")
    job_role = state.get("job_role") or "default"
    assessment_version = state.get("assessment_version") or "1.0.0"
    key = _make_key(session_id, job_role, assessment_version)
    now = time.time()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO assessments (
                id, session_id, job_role, assessment_id,
                assessment_version, state, answers_json,
                result_json, created_at, updated_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, job_role, assessment_version)
            DO UPDATE SET
                id = excluded.id,
                assessment_id = excluded.assessment_id,
                state = excluded.state,
                answers_json = excluded.answers_json,
                result_json = excluded.result_json,
                updated_at = excluded.updated_at,
                completed_at = excluded.completed_at""",
            (
                key,
                session_id,
                job_role,
                state.get("assessment_id", ""),
                assessment_version,
                state.get("state", "not_started"),
                json.dumps(state.get("answers", []), ensure_ascii=False),
                json.dumps(state.get("result"), ensure_ascii=False) if state.get("result") else None,
                state.get("created_at", now),
                now,
                state.get("completed_at"),
            )
        )
        conn.commit()
    state["id"] = key
    state["updated_at"] = now
    return state


def list_sessions(job_role=None):
    """List all assessment sessions, optionally filtered by job_role."""
    _ensure_table()
    with _conn() as conn:
        if job_role:
            rows = conn.execute(
                "SELECT session_id, job_role, state, created_at, updated_at, completed_at FROM assessments WHERE job_role = ? ORDER BY updated_at DESC LIMIT 100",
                (job_role,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT session_id, job_role, state, created_at, updated_at, completed_at FROM assessments ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
    return [
        {
            "session_id": r[0],
            "job_role": r[1],
            "state": r[2],
            "created_at": r[3],
            "updated_at": r[4],
            "completed_at": r[5],
        }
        for r in rows
    ]
