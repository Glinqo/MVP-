"""V2 Workflow Store - Persistent Intervention Workflow"""
import sqlite3, json, time, os
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "v2_workflow.db"

VALID_TRANSITIONS = {
    "draft":       ["reviewed", "cancelled"],
    "reviewed":    ["assigned", "cancelled"],
    "assigned":    ["in_progress", "cancelled"],
    "in_progress": ["completed"],
    "completed":   ["evaluated"],
    "evaluated":   ["closed"],
    "closed":      [],
    "cancelled":   [],
}

def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute("PRAGMA journal_mode=WAL")
    c.row_factory = sqlite3.Row
    return c

def _ensure_tables():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                intervention_id TEXT NOT NULL UNIQUE,
                issue_id TEXT NOT NULL DEFAULT '',
                teacher_id TEXT NOT NULL DEFAULT '',
                candidate_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                scope_class TEXT NOT NULL DEFAULT '',
                job_role TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                reviewed_at REAL,
                assigned_at REAL,
                completed_at REAL,
                evaluated_at REAL,
                closed_at REAL,
                version INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS intervention_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                intervention_id TEXT NOT NULL,
                student_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'assigned',
                created_at REAL NOT NULL,
                UNIQUE(intervention_id, student_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS intervention_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                intervention_id TEXT NOT NULL,
                student_id TEXT NOT NULL,
                resource_type TEXT NOT NULL DEFAULT 'scenario',
                resource_id TEXT NOT NULL DEFAULT '',
                target_ability_ids TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'assigned',
                assigned_at REAL NOT NULL,
                started_at REAL,
                completed_at REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                intervention_id TEXT NOT NULL,
                student_id TEXT NOT NULL,
                pre_mastery REAL,
                post_mastery REAL,
                delta REAL,
                pre_patterns TEXT DEFAULT '[]',
                post_patterns TEXT DEFAULT '[]',
                completion INTEGER DEFAULT 0,
                evidence_count INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'insufficient_evidence',
                evaluated_at REAL,
                engine_version TEXT DEFAULT ''
            )
        """)
        conn.commit()
_ensure_tables()

# --- Intervention CRUD ---

def create_intervention(issue_id: str, candidate_id: str, student_ids: List[str],
                        teacher_id: str, scope_class: str = "", job_role: str = "") -> Dict[str, Any]:
    iid = f"INT_{issue_id}_{int(time.time())}"
    now = time.time()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO interventions (intervention_id, issue_id, teacher_id, candidate_id,
               status, scope_class, job_role, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?)""",
            (iid, issue_id, teacher_id, candidate_id, scope_class, job_role, now, now)
        )
        for sid in student_ids:
            conn.execute(
                "INSERT OR IGNORE INTO intervention_targets (intervention_id, student_id, status, created_at) VALUES (?, ?, 'assigned', ?)",
                (iid, sid, now)
            )
        conn.commit()
    return {"intervention_id": iid, "status": "draft"}

def get_intervention(intervention_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM interventions WHERE intervention_id = ?", (intervention_id,)).fetchone()
        if not row:
            return None
        targets = [dict(r) for r in conn.execute(
            "SELECT * FROM intervention_targets WHERE intervention_id = ?", (intervention_id,)).fetchall()]
        tasks = [dict(r) for r in conn.execute(
            "SELECT * FROM intervention_tasks WHERE intervention_id = ?", (intervention_id,)).fetchall()]
        result = dict(row)
        result["targets"] = targets
        result["tasks"] = tasks
        return result

def transition_intervention(intervention_id: str, new_status: str, actor: str = "system") -> Dict[str, Any]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM interventions WHERE intervention_id = ?", (intervention_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "not found", "code": "NOT_FOUND"}
        cur = dict(row)["status"]
        valid = VALID_TRANSITIONS.get(cur, [])
        if new_status not in valid:
            return {"ok": False, "error": f"invalid transition {cur}->{new_status}", "code": "ILLEGAL_STATE"}
        now = time.time()
        timestamp_col = {
            "reviewed": "reviewed_at", "assigned": "assigned_at", "completed": "completed_at",
            "evaluated": "evaluated_at", "closed": "closed_at"
        }
        updates = {"status = ?": new_status, "updated_at = ?": now}
        if new_status in timestamp_col:
            updates[f"{timestamp_col[new_status]} = ?"] = now
        set_clause = ", ".join(f"{k} {v}" for k, v in zip(updates.keys(), ["= ?"] * len(updates)) if not isinstance(k, str))
        cols = [("status", new_status), ("updated_at", now)]
        if new_status in timestamp_col:
            cols.append((timestamp_col[new_status], now))
        params = [v for _, v in cols]
        params.append(intervention_id)
        set_parts = ", ".join(f"{c} = ?" for c, _ in cols)
        conn.execute(
            f"UPDATE interventions SET {set_parts}, version = version + 1 WHERE intervention_id = ?",
            params
        )
        conn.commit()
    return {"ok": True, "intervention_id": intervention_id, "status": new_status}

def list_interventions(teacher_id: str = "", scope_class: str = "") -> List[Dict[str, Any]]:
    with _conn() as conn:
        if scope_class:
            rows = conn.execute("SELECT * FROM interventions WHERE scope_class = ? ORDER BY updated_at DESC", (scope_class,)).fetchall()
        elif teacher_id:
            rows = conn.execute("SELECT * FROM interventions WHERE teacher_id = ? ORDER BY updated_at DESC", (teacher_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM interventions ORDER BY updated_at DESC LIMIT 100").fetchall()
        return [dict(r) for r in rows]

def get_student_interventions(student_id: str) -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT i.* FROM interventions i
            INNER JOIN intervention_targets t ON i.intervention_id = t.intervention_id
            WHERE t.student_id = ? ORDER BY i.updated_at DESC
        """, (student_id,)).fetchall()
        return [dict(r) for r in rows]

# --- Outcome ---

def save_outcome(intervention_id: str, student_id: str, pre_mastery: float = 0.0,
                 post_mastery: float = 0.0, delta: float = 0.0,
                 pre_patterns: str = "[]", post_patterns: str = "[]",
                 evidence_count: int = 0, status: str = "insufficient_evidence") -> Dict[str, Any]:
    with _conn() as conn:
        conn.execute("""INSERT OR REPLACE INTO outcomes
            (intervention_id, student_id, pre_mastery, post_mastery, delta,
             pre_patterns, post_patterns, evidence_count, status, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (intervention_id, student_id, pre_mastery, post_mastery, delta,
             pre_patterns, post_patterns, evidence_count, status, time.time()))
        conn.commit()
    return {"ok": True, "intervention_id": intervention_id, "student_id": student_id}

def get_outcome(intervention_id: str) -> Dict[str, Any]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM outcomes WHERE intervention_id = ?", (intervention_id,)).fetchall()
        return {"intervention_id": intervention_id, "outcomes": [dict(r) for r in rows],
                "total": len(rows)}

print("WorkflowStore initialized:", DB_PATH)