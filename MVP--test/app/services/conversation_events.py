"""
Conversation Events - Phase 4.

Unified SSE event model for the streaming chat pipeline.
All events follow a simple dataclass-like structure.
"""

import json
import uuid
from datetime import datetime, timezone


class ConversationEvent:
    """A single event in the conversation turn pipeline."""

    __slots__ = ("event", "data", "turn_id")

    def __init__(self, event, data=None, turn_id=None):
        self.event = event
        self.data = data or {}
        self.turn_id = turn_id

    def to_sse(self):
        """Format as SSE text."""
        payload = json.dumps(self.data, ensure_ascii=False, default=str)
        return "event: %s\ndata: %s\n\n" % (self.event, payload)

    def to_dict(self):
        return {"event": self.event, "data": self.data, "turn_id": self.turn_id}


def generate_turn_id():
    return "turn_%s_%s" % (
        datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        uuid.uuid4().hex[:8],
    )


# ---------------------------------------------------------------------------
# Event factory functions
# ---------------------------------------------------------------------------

def accepted(turn_id):
    return ConversationEvent("accepted", {"turn_id": turn_id}, turn_id)


def state_event(phase, turn_id=None, **kwargs):
    data = {"phase": phase}
    data.update(kwargs)
    return ConversationEvent("state", data, turn_id)


def tool_start(tool_name, label="", turn_id=None):
    return ConversationEvent("tool_start", {
        "tool": tool_name,
        "label": label or "Running %s" % tool_name,
    }, turn_id)


def tool_result(tool_name, success=True, data=None, refs=None, turn_id=None):
    return ConversationEvent("tool_result", {
        "tool": tool_name,
        "success": success,
        "data": data or {},
        "refs": refs or [],
    }, turn_id)


def delta(text, turn_id=None):
    return ConversationEvent("delta", {"text": text}, turn_id)


def cards_event(knowledge_refs=None, ability_cards=None, task_cards=None,
                tool_suggestions=None, turn_id=None):
    data = {}
    if knowledge_refs:
        data["knowledge_refs"] = knowledge_refs
    if ability_cards:
        data["ability_cards"] = ability_cards
    if task_cards:
        data["task_cards"] = task_cards
    if tool_suggestions:
        data["tool_suggestions"] = tool_suggestions
    return ConversationEvent("cards", data, turn_id)


def done_event(answer, turn_id=None, conversation_state_delta=None, metadata=None):
    data = {
        "answer": answer,
        "turn_id": turn_id,
    }
    if conversation_state_delta:
        data["conversation_state_delta"] = conversation_state_delta
    if metadata:
        data["metadata"] = metadata
    return ConversationEvent("done", data, turn_id)


def error_event(code, message, recoverable=True, turn_id=None):
    return ConversationEvent("error", {
        "code": code,
        "message": message,
        "recoverable": recoverable,
    }, turn_id)
