"""Unified server-side conversation state.

The server is the single source of truth for conversation history.
Frontend sends only session_id + message; backend manages all history.

State is stored inside the session JSON file under the "conversation" key.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from .data_store import load_session, save_session, _safe_id


def load_conversation_state(session_id):
    """Load conversation state for a session, or create a new empty one."""
    record = load_session(session_id)
    conv = record.get("conversation")
    if not conv or not isinstance(conv, dict):
        conv = _empty_conversation(session_id)
        record["conversation"] = conv
        save_session(record)
    # Ensure all expected keys exist
    conv.setdefault("session_id", _safe_id(session_id))
    conv.setdefault("messages", [])
    conv.setdefault("summary", "")
    conv.setdefault("active_task", None)
    conv.setdefault("slots", {})
    conv.setdefault("global_slots", {})
    conv.setdefault("metadata", {
        "created_at": record.get("created_at", datetime.now(timezone.utc).isoformat()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return conv


def save_conversation_state(state):
    """Persist conversation state into the session record."""
    sid = state.get("session_id", "default")
    record = load_session(sid)
    state["metadata"] = state.get("metadata", {})
    state["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
    record["conversation"] = state
    save_session(record)
    return state


def get_or_create_conversation_state(session_id):
    """Get existing state or create new one (same as load, explicit name)."""
    return load_conversation_state(session_id)


def append_user_message(session_id, content):
    """Append a user message to the conversation. Always appends exactly once."""
    state = load_conversation_state(session_id)
    msg = {
        "role": "user",
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    state["messages"].append(msg)
    save_conversation_state(state)
    return msg


def append_assistant_message(session_id, content):
    """Append an assistant message to the conversation. Always appends exactly once."""
    state = load_conversation_state(session_id)
    msg = {
        "role": "assistant",
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    state["messages"].append(msg)
    save_conversation_state(state)
    return msg


def get_recent_messages(session_id, limit=8):
    """Get recent messages for LLM context. Returns list of {role, content}."""
    state = load_conversation_state(session_id)
    messages = state.get("messages", [])
    if limit <= 0 or not messages:
        return []
    return [
        {"role": m["role"], "content": m["content"]}
        for m in messages[-limit:]
    ]


def get_all_messages(session_id):
    """Get all messages (for frontend restore on refresh)."""
    state = load_conversation_state(session_id)
    return state.get("messages", [])


def clear_conversation_state(session_id):
    """Reset conversation state for a session."""
    record = load_session(session_id)
    record["conversation"] = _empty_conversation(session_id)
    save_session(record)
    return record["conversation"]


def get_conversation_context(session_id, limit=8):
    """Get messages formatted for LLM context (role+content only)."""
    return get_recent_messages(session_id, limit)


def _empty_conversation(session_id):
    return {
        "session_id": _safe_id(session_id),
        "messages": [],
        "summary": "",
        "active_task": None,
        "slots": {},
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


# ---- Slot and task helpers (placeholder for Phase 2) ----

def update_slots(session_id, slots_update):
    """Merge slots_update into existing slots."""
    state = load_conversation_state(session_id)
    state["slots"].update(slots_update or {})
    save_conversation_state(state)
    return state["slots"]


def set_active_task(session_id, task):
    """Set the active task for this conversation."""
    state = load_conversation_state(session_id)
    state["active_task"] = task
    save_conversation_state(state)
    return state["active_task"]


def clear_active_task(session_id):
    """Clear the active task."""
    state = load_conversation_state(session_id)
    state["active_task"] = None
    save_conversation_state(state)
    return state["active_task"]

# ---- Conversation management ---

def list_conversation_sessions(limit=20):
    """List all sessions sorted by updated_at desc."""
    from .data_store import SESSIONS_DIR
    results = []
    if not SESSIONS_DIR.exists():
        return results
    for fpath in sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            record = json.loads(fpath.read_text(encoding="utf-8"))
            conv = record.get("conversation", {})
            if not isinstance(conv, dict):
                continue
            sid = conv.get("session_id", fpath.stem)
            msgs = conv.get("messages", [])
            if not msgs or len(msgs) == 0:
                continue  # skip empty sessions
            title = conv.get("metadata", {}).get("title", "")
            if not title:
                for m in msgs:
                    if m.get("role") == "user":
                        title = str(m.get("content", ""))[:40]
                        break
            if not title:
                title = sid[:20]
            results.append({
                "session_id": sid,
                "title": title,
                "message_count": len(msgs),
                "updated_at": conv.get("metadata", {}).get("updated_at", ""),
            })
            if len(results) >= limit:
                break
        except Exception:
            continue
    return results


def rename_conversation(session_id, title):
    """Rename a conversation session."""
    state = load_conversation_state(session_id)
    state.setdefault("metadata", {})
    state["metadata"]["title"] = title
    state["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_conversation_state(state)
    return {"session_id": session_id, "title": title}


def delete_conversation(session_id):
    """Delete a conversation session file."""
    from .data_store import SESSIONS_DIR
    path = SESSIONS_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()
        return {"deleted": True}
    return {"deleted": False, "error": "Not found"}


def update_activity(session_id):
    """Touch the updated_at timestamp."""
    state = load_conversation_state(session_id)
    state.setdefault("metadata", {})
    state["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_conversation_state(state)


def generate_session_title(session_id):
    """Auto-generate title from first user message if not already set."""
    state = load_conversation_state(session_id)
    metadata = state.get("metadata", {})
    if metadata.get("title"):
        return metadata["title"]
    for m in state.get("messages", []):
        if m.get("role") == "user":
            title = str(m.get("content", ""))[:40].strip()
            if title:
                metadata["title"] = title
                metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
                save_conversation_state(state)
                return title
    return session_id[:20]
