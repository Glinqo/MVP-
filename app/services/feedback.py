import json
import re
from collections import Counter
from datetime import datetime, timezone

from .data_loader import ROOT


SESSIONS_DIR = ROOT / "data" / "sessions"
ALLOWED_FEEDBACK = {"已掌握", "仍不会", "需要更基础讲解"}


def now_id():
    return datetime.now(timezone.utc).strftime("S%Y%m%d%H%M%S%f")


def safe_session_id(value):
    raw = str(value or now_id())
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", raw)[:80]
    return cleaned or now_id()


def session_path(session_id):
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = safe_session_id(session_id)
    return cleaned, SESSIONS_DIR / f"{cleaned}.json"


def load_session_record(session_id):
    cleaned, target = session_path(session_id)
    record = {}
    if target.exists():
        try:
            record = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            record = {}

    record.setdefault("session_id", cleaned)
    record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    record.setdefault("events", [])
    if not isinstance(record["events"], list):
        record["events"] = []
    return record


def write_session_record(record):
    session_id = safe_session_id(record.get("session_id"))
    record["session_id"] = session_id
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    _, target = session_path(session_id)
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def append_session_event(session_id, event):
    record = load_session_record(session_id)
    event = dict(event or {})
    event.setdefault("event_type", "unknown")
    event["event_id"] = now_id()
    event["created_at"] = datetime.now(timezone.utc).isoformat()
    record.setdefault("events", []).append(event)
    write_session_record(record)
    return {"saved": True, "session_id": record["session_id"], "event_type": event["event_type"]}


def save_feedback(payload):
    payload = payload or {}
    feedback = payload.get("feedback")
    if feedback not in ALLOWED_FEEDBACK:
        raise ValueError("feedback must be one of: 已掌握, 仍不会, 需要更基础讲解")

    session_id = safe_session_id(payload.get("session_id"))
    record = load_session_record(session_id)
    record = {
        **record,
        "session_id": session_id,
        "feedback": feedback,
        "user_input": payload.get("user_input", ""),
        "score_result": payload.get("score_result", {}),
        "weak_abilities": payload.get("weak_abilities", []),
        "recommended_path": payload.get("recommended_path", []),
    }
    record.setdefault("events", []).append(
        {
            "event_id": now_id(),
            "event_type": "feedback",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "feedback": feedback,
            "user_input": payload.get("user_input", ""),
            "score_result": payload.get("score_result", {}),
            "weak_abilities": payload.get("weak_abilities", []),
            "highlighted_abilities": payload.get("highlighted_abilities", []),
            "recommended_path": payload.get("recommended_path", []),
        }
    )
    write_session_record(record)
    return {"saved": True, "session_id": session_id, "feedback": feedback}


def teacher_summary():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for path in SESSIONS_DIR.glob("*.json"):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue

    feedback_counts = Counter(record.get("feedback", "未填写") for record in records)
    weak_counts = Counter()
    for record in records:
        for ability in record.get("weak_abilities", []):
            key = ability.get("ability_name") or ability.get("name") or ability.get("ability_id") or ability.get("id")
            if key:
                weak_counts[key] += 1

    return {
        "session_count": len(records),
        "feedback_counts": dict(feedback_counts),
        "top_weak_abilities": [
            {"ability_name": ability_name, "count": count}
            for ability_name, count in weak_counts.most_common(3)
        ],
        "teaching_suggestion": (
            "暂无反馈记录，建议先完成一次学生诊断。"
            if not records
            else "优先围绕班级高频薄弱能力安排下一节课补救训练，并保留安全检查口令。"
        ),
    }
