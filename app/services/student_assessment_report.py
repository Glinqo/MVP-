"""Student assessment reports for teacher view. Stage 4."""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"


def generate_individual_report(session_id: str) -> Dict[str, Any]:
    """Generate a detailed individual assessment report for a student session."""
    return {
        "session_id": session_id,
        "student_name": "",
        "job_role": "",
        "overall_score": 0.0,
        "dimension_scores": {},
        "weak_areas": [],
        "strong_areas": [],
        "recommendations": [],
        "learning_path": [],
    }


def generate_class_report(student_ids: List[str] = None) -> Dict[str, Any]:
    """Generate a class-wide summary of all student assessments."""
    students = []
    return {
        "total_students": len(students),
        "average_score": 0.0,
        "dimension_averages": {},
        "common_weak_areas": [],
        "students": students,
        "generated_at": "",
    }


def list_student_sessions() -> List[Dict[str, Any]]:
    """List all student assessment sessions."""
    sessions = []
    if not (DATA_DIR / "sessions.db").exists():
        return sessions
    try:
        import sqlite3
        conn = sqlite3.connect(str(DATA_DIR / "sessions.db"))
        cur = conn.cursor()
        cur.execute("SELECT session_id, metadata FROM sessions ORDER BY created_at DESC LIMIT 100")
        for row in cur.fetchall():
            try:
                meta = json.loads(row[1] or "{}")
                sessions.append({"session_id": row[0], "job_role": meta.get("job_role", ""), "created_at": meta.get("created_at", "")})
            except Exception:
                sessions.append({"session_id": row[0], "job_role": "", "created_at": ""})
        conn.close()
    except Exception as e:
        logger.warning("Failed to list sessions: %s", e)
    return sessions