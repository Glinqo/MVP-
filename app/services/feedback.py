"""Feedback and session management (delegates to data_store)."""

from collections import Counter
from datetime import datetime, timezone
from .data_store import load_session, save_session, append_event as _append_event, list_all_sessions, _safe_id, _now_id

ALLOWED_FEEDBACK = {"已掌握", "仍不会", "需要更基础讲解"}


def safe_session_id(value):
    return _safe_id(value)


def now_id():
    return _now_id()


def session_path(session_id):
    from pathlib import Path
    from .data_store import SESSIONS_DIR
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = _safe_id(session_id)
    return cleaned, SESSIONS_DIR / f"{cleaned}.json"


def load_session_record(session_id):
    return load_session(session_id)


def write_session_record(record):
    return save_session(record)


def append_session_event(session_id, event):
    record = _append_event(session_id, event)
    return {"saved": True, "session_id": record["session_id"], "event_type": event.get("event_type", "unknown")}


def save_feedback(payload):
    payload = payload or {}
    feedback = payload.get("feedback")
    if feedback not in ALLOWED_FEEDBACK:
        raise ValueError("feedback must be one of: 已掌握, 仍不会, 需要更基础讲解")
    session_id = _safe_id(payload.get("session_id"))
    record = load_session(session_id)
    record.update({
        "feedback": feedback,
        "user_input": payload.get("user_input", ""),
        "score_result": payload.get("score_result", {}),
        "weak_abilities": payload.get("weak_abilities", []),
        "recommended_path": payload.get("recommended_path", []),
    })
    event = {
        "event_id": _now_id(),
        "event_type": "feedback",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "feedback": feedback,
        "user_input": payload.get("user_input", ""),
        "score_result": payload.get("score_result", {}),
        "weak_abilities": payload.get("weak_abilities", []),
        "highlighted_abilities": payload.get("highlighted_abilities", []),
        "recommended_path": payload.get("recommended_path", []),
    }
    record.setdefault("events", []).append(event)
    save_session(record)
    return {"saved": True, "session_id": session_id, "feedback": feedback}


def teacher_summary():
    sessions = list_all_sessions()
    records = []
    from .data_store import SESSIONS_DIR
    for p in SESSIONS_DIR.glob("*.json"):
        try:
            import json
            records.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    feedback_counts = Counter(r.get("feedback", "未填写") for r in records)
    weak_counts = Counter()
    for r in records:
        for ability in r.get("weak_abilities", []):
            key = ability.get("ability_name") or ability.get("name") or ability.get("ability_id") or ability.get("id")
            if key:
                weak_counts[key] += 1
    return {
        "session_count": len(sessions),
        "feedback_counts": dict(feedback_counts),
        "top_weak_abilities": [{"ability_name": k, "count": v} for k, v in weak_counts.most_common(3)],
        "teaching_suggestion": (
            "暂无反馈记录" if not sessions
            else "优先围绕班级高频薄弱能力安排下一节课补救训练"
        ),
    }
