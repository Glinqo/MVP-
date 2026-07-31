"""Student assessment reports for teacher view. Stage 4 (fixed).
Uses assessment_store for persistent data, never leaks sensitive fields."""
import json
import logging
from typing import Any, Dict, List

from app.services.assessment_store import list_sessions as _list_db_sessions, load_state

logger = logging.getLogger(__name__)


def generate_individual_report(session_id: str, job_role=None) -> Dict[str, Any]:
    """Generate a detailed individual report from persistent store.
    Never returns: correct_key, token, password, phone, or internal paths."""
    try:
        state = load_state(session_id, job_role)
    except Exception:
        return {"session_id": session_id, "error": "No assessment data found"}

    result = state.get("result") or {}
    return {
        "session_id": session_id,
        "job_role": state.get("job_role", ""),
        "state": state.get("state", "not_started"),
        "completed": state.get("completed", False),
        "overall_score": result.get("total_score", 0),
        "dimension_scores": result.get("dimension_scores", {}),
        "weak_areas": result.get("weak_abilities", []),
        "strong_areas": result.get("strong_abilities", []),
        "safety_gaps": result.get("safety_critical_gaps", []),
        "answered_count": state.get("answers", None) and len(state["answers"]) or 0,
        "updated_at": state.get("updated_at"),
        "completed_at": state.get("completed_at"),
    }


def generate_class_report(student_ids=None) -> Dict[str, Any]:
    """Generate a class-wide summary from persistent store."""
    sessions = _list_db_sessions()
    students = []
    for s in sessions:
        students.append({
            "session_id": s.get("session_id", ""),
            "job_role": s.get("job_role", ""),
            "state": s.get("state", ""),
            "completed_at": s.get("completed_at"),
        })
    return {
        "total_students": len(students),
        "students": students,
        "generated_at": "",
    }


def list_student_sessions() -> Dict[str, Any]:
    """List all student assessment sessions from persistent store."""
    try:
        sessions = _list_db_sessions()
        return {
            "students": sessions,
            "total": len(sessions),
        }
    except Exception as e:
        logger.warning("Failed to list sessions: %s", e)
        return {"students": [], "total": 0, "error": str(e)}
