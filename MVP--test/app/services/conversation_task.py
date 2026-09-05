"""
ActiveTask lifecycle management — Phase 2.

Manages a single active task per conversation session.
The active task tracks what problem is being solved and what slots
have been collected.
"""

import uuid
from datetime import datetime, timezone
from .conversation_state import load_conversation_state, save_conversation_state
from .diagnosis_policy import init_diagnosis_progress, update_diagnosis_progress, diagnosis_progress_summary


TASK_STATUSES = ["collecting_info", "diagnosing", "resolved", "abandoned"]
MAX_CLARIFY_TURNS = 3


def start_task(session_id, task_type="diagnosis", topic="", matched_pattern_id=None):
    """Create a new active task for the session.

    Overwrites any existing active task (single-task model for Phase 2).
    """
    state = load_conversation_state(session_id)
    task = {
        "task_id": f"task_{uuid.uuid4().hex[:8]}",
        "type": task_type,
        "topic": topic or "未知故障",
        "status": "collecting_info",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "clarify_turns": 0,
        "pending_slot": None,
        "matched_pattern_id": matched_pattern_id,
        "slots": {},
        "diagnosis_progress": init_diagnosis_progress(),
    }
    state["active_task"] = task
    save_conversation_state(state)
    return task


def get_active_task(session_id):
    """Get the current active task, or None."""
    state = load_conversation_state(session_id)
    task = state.get("active_task")
    if task and isinstance(task, dict) and task.get("task_id"):
        return task
    return None


def update_task(session_id, updates):
    """Apply partial updates to the active task.

    updates is a dict of fields to update. Updates updated_at automatically.
    """
    state = load_conversation_state(session_id)
    task = state.get("active_task")
    if not task or not isinstance(task, dict):
        return None

    for key, value in updates.items():
        if key in ("slots",):
            # merging handled at higher level
            task[key] = value
        elif key != "task_id":
            task[key] = value

    task["updated_at"] = datetime.now(timezone.utc).isoformat()
    state["active_task"] = task
    save_conversation_state(state)
    return task


def finish_task(session_id, resolution=""):
    """Mark the active task as resolved."""
    state = load_conversation_state(session_id)
    task = state.get("active_task")
    if task and isinstance(task, dict):
        task["status"] = "resolved"
        task["resolution"] = resolution
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        state["active_task"] = task
        save_conversation_state(state)
    return task


def cancel_task(session_id, reason=""):
    """Abandon the current active task."""
    state = load_conversation_state(session_id)
    task = state.get("active_task")
    if task and isinstance(task, dict):
        task["status"] = "abandoned"
        task["abandon_reason"] = reason
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        state["active_task"] = task
        save_conversation_state(state)
    return task


def clear_active_task(session_id):
    """Remove the active task entirely (e.g., after resolution)."""
    state = load_conversation_state(session_id)
    state["active_task"] = None
    save_conversation_state(state)


# ---------------------------------------------------------------------------
# Task-level slot helpers
# ---------------------------------------------------------------------------

def get_task_slots(session_id):
    """Get slots from the active task."""
    task = get_active_task(session_id)
    if task:
        return task.get("slots", {})
    return {}


def set_task_slots(session_id, slots):
    """Set slots on the active task."""
    return update_task(session_id, {"slots": slots})


def increment_clarify_turn(session_id):
    """Increment clarify_turns on the active task. Returns the new count."""
    task = get_active_task(session_id)
    if task:
        new_count = task.get("clarify_turns", 0) + 1
        update_task(session_id, {"clarify_turns": new_count})
        return new_count
    return 0


def get_clarify_turns(session_id):
    """Get clarify_turns from the active task."""
    task = get_active_task(session_id)
    if task:
        return task.get("clarify_turns", 0)
    return 0


def set_pending_slot(session_id, slot_name):
    """Set which slot the next user message should answer."""
    return update_task(session_id, {"pending_slot": slot_name})


def clear_pending_slot(session_id):
    """Clear the pending slot after resolution."""
    return update_task(session_id, {"pending_slot": None})


def get_pending_slot(session_id):
    """Get the currently pending slot, or None."""
    task = get_active_task(session_id)
    if task:
        return task.get("pending_slot")
    return None


# ---------------------------------------------------------------------------
# Task state summary for API response
# ---------------------------------------------------------------------------

def task_summary(session_id):
    """Return a compact summary of the active task for API responses."""
    task = get_active_task(session_id)
    if not task:
        return None
    return {
        "task_id": task.get("task_id"),
        "type": task.get("type"),
        "topic": task.get("topic"),
        "status": task.get("status"),
        "clarify_turns": task.get("clarify_turns", 0),
        "pending_slot": task.get("pending_slot"),
        "slots_summary": _summarize_slots(task.get("slots", {})),
    }


def get_diagnosis_progress(session_id):
    task = get_active_task(session_id)
    if task:
        return task.get("diagnosis_progress")
    return None

def set_diagnosis_progress(session_id, progress):
    return update_task(session_id, {"diagnosis_progress": progress})

def update_diagnosis_from_context(session_id, pattern_id, context):
    progress = get_diagnosis_progress(session_id)
    progress = update_diagnosis_progress(progress, pattern_id, context)
    set_diagnosis_progress(session_id, progress)
    return progress

def get_diagnosis_summary(session_id):
    progress = get_diagnosis_progress(session_id)
    return diagnosis_progress_summary(progress)

def _summarize_slots(slots):
    """Convert slot dict to flat {key: value} for display."""
    flat = {}
    for key, val in slots.items():
        if isinstance(val, dict):
            flat[key] = val.get("value", "unknown")
        else:
            flat[key] = str(val) if val else "unknown"
    return flat


# ---------------------------------------------------------------------------
# Short answer detection (for task continuation)
# ---------------------------------------------------------------------------

SHORT_ANSWER_PATTERNS = [
    "不亮", "没亮", "亮", "没有", "有", "是", "不是",
    "会亮", "不会", "没变化", "没变", "变化", "变了",
    "NPN", "PNP", "npn", "pnp", "24V", "0V",
    "接了", "没接", "接好了", "断开",
    "对", "不对", "是的", "没错",
]


def looks_like_task_continuation(message, has_active_task):
    """Check if a user message looks like it continues the current task.

    Returns True if the message should be treated as a task continuation
    rather than a brand-new intent.
    """
    if not has_active_task:
        return False

    text = str(message).strip() if message else ""
    if not text:
        return False

    # Very short messages are almost always task continuations
    if len(text) <= 10:
        return True

    # Known short answer patterns
    if text in SHORT_ANSWER_PATTERNS or text.lower() in [p.lower() for p in SHORT_ANSWER_PATTERNS]:
        return True

    return False
