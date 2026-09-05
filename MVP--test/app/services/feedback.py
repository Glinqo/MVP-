import json
import re
import threading
from collections import Counter, OrderedDict
from datetime import datetime, timezone

from .data_loader import ROOT


SESSIONS_DIR = ROOT / "data" / "sessions"
ALLOWED_FEEDBACK = {"已掌握", "仍不会", "需要更基础讲解"}

# ── per-session file locks (read-modify-write protection) ──────────
_session_locks: dict[str, threading.Lock] = {}
_locks_dict_lock = threading.Lock()
_MAX_LOCKS = 100


def _get_session_lock(session_id: str) -> threading.Lock:
    safe_id = safe_session_id(session_id)
    with _locks_dict_lock:
        if safe_id not in _session_locks:
            _prune_locks_locked()
            _session_locks[safe_id] = threading.Lock()
        return _session_locks[safe_id]


def _prune_locks_locked():
    """Remove oldest locks when the dictionary grows too large.
    Must be called while holding _locks_dict_lock."""
    while len(_session_locks) > _MAX_LOCKS:
        oldest = next(iter(_session_locks))
        del _session_locks[oldest]


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
    lock = _get_session_lock(session_id)
    with lock:
        record = load_session_record(session_id)
        event = dict(event or {})
        event.setdefault("event_type", "unknown")
        event["event_id"] = now_id()
        event["created_at"] = datetime.now(timezone.utc).isoformat()
        record.setdefault("events", []).append(event)
        write_session_record(record)

        # Best-effort SQLite dual-write
        try:
            from .session_store import insert_event, increment_ability_counters
            sid = safe_session_id(session_id)
            insert_event(sid, event)
            _increment_ability_state_for_event(sid, event)
        except Exception:
            pass  # SQLite write is non-critical for JSON-led flow

    return {"saved": True, "session_id": record["session_id"], "event_type": event["event_type"]}


def _increment_ability_state_for_event(session_id: str, event: dict):
    """Increment ability-state cache counters for a single event.

    Only handles simple event types; complex types (feedback, score with
    cross-ability side-effects) are handled by cache invalidation in
    graph_update_engine.
    """
    from .graph_update_engine import (
        IMPROVING_EVENTS,
        MASTERED_EVENTS,
        WEAK_EVENTS,
        event_ability_ids,
    )
    from .session_store import batch_increment_ability_counters

    event_type = event.get("event_type", "")
    ability_ids = event_ability_ids(event)

    if not ability_ids:
        return

    if event_type == "chat_message":
        increments = [(aid, "chat_count") for aid in ability_ids]
    elif event_type in IMPROVING_EVENTS:
        increments = [(aid, "improving_count") for aid in ability_ids]
    elif event_type in WEAK_EVENTS:
        increments = [(aid, "weak_count") for aid in ability_ids]
    elif event_type in MASTERED_EVENTS:
        outcome = event.get("outcome")
        if outcome in {None, "", "passed", "completed"}:
            increments = [(aid, "mastered_count") for aid in ability_ids]
        else:
            increments = [(aid, "improving_count") for aid in ability_ids]
    else:
        # Complex event types (feedback, score, diagnosis) — skip increment,
        # rely on full recompute path in graph_update_engine.
        return

    batch_increment_ability_counters(session_id, increments, event_id=event.get("event_id", ""))


def save_feedback(payload):
    payload = payload or {}
    feedback = payload.get("feedback")
    if feedback not in ALLOWED_FEEDBACK:
        raise ValueError("feedback must be one of: 已掌握, 仍不会, 需要更基础讲解")

    session_id = safe_session_id(payload.get("session_id"))
    lock = _get_session_lock(session_id)
    with lock:
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
