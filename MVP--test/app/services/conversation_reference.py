# -*- coding: utf-8 -*-
"""
Conversation Reference Resolver - Phase 6.1.
Lightweight coreference and backward-reference resolution for slot-aware parsing.
No LLM needed. Rule-based.
"""

# Patterns for "the former" / "the latter" references
_FORMER_PATTERNS = [
    "前者",
    "第一个",
    "前一个",
]

_LATTER_PATTERNS = [
    "后者",
    "第二个",
    "后一个",
]

# Patterns for "go back to topic X"
_BACK_REF_PATTERNS = [
    "回到刚才",
    "回到上一个",
    "刚才说的",
    "前面说的",
    "上面说的",
    "上一个问题",
]

# Topic-to-slot mapping for backward references
_TOPIC_SLOT_MAP = {
    "传感器类型": "sensor_type",
    "传感器": "sensor_type",
    "NPN": "sensor_type",
    "PNP": "sensor_type",
    "传感器灯": "sensor_led",
    "PLC输入灯": "plc_input_led",
    "PLC输入": "plc_input_led",
    "在线监控": "online_monitor",
    "监控": "online_monitor",
    "公共端": "common_terminal",
    "COM": "common_terminal",
}


def resolve_former_latter(message, recent_entities):
    """Resolve "the former" / "the latter" references.
    recent_entities: list of (entity_name, entity_value) tuples from recent turns.
    Returns resolved entity value or None.
    """
    text = str(message).strip() if message else ""
    if not text or len(recent_entities) < 2:
        return None

    for pat in _FORMER_PATTERNS:
        if pat in text:
            return recent_entities[0][1]

    for pat in _LATTER_PATTERNS:
        if pat in text:
            return recent_entities[1][1]

    return None


def resolve_back_reference(message, history):
    """Resolve backward references like "go back to sensor type".
    history: list of recent messages with role/content.
    Returns (slot_name, slot_value) or (None, None).
    """
    text = str(message).strip() if message else ""
    if not text:
        return None, None

    # Check if this is a back-reference
    is_back_ref = any(pat in text for pat in _BACK_REF_PATTERNS)
    if not is_back_ref:
        return None, None

    # Find the referenced topic
    for topic, slot_name in _TOPIC_SLOT_MAP.items():
        if topic in text:
            # Search history for this slot value
            for msg in reversed(history):
                content = msg.get("content", "")
                if topic in content:
                    return slot_name, content[:80]
            return slot_name, None

    return None, None


def extract_recent_entities(history, max_turns=5):
    """Extract named entities from recent conversation turns.
    Returns list of (name, value) tuples.
    """
    from .conversation_slots import extract_slots_from_message
    entities = []
    for msg in history[-max_turns:]:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            slots = extract_slots_from_message(content)
            for slot_name, slot_data in slots.items():
                val = slot_data.get("value") if isinstance(slot_data, dict) else slot_data
                entities.append((slot_name, val))
    return entities


def classify_message_relation(message, active_task):
    """Classify message relation to current task.
    Returns one of: continue_task, side_question, new_task, cancel_task, uncertain.
    """
    text = str(message).strip() if message else ""
    if not text:
        return "uncertain"

    # Cancel signals
    cancel_kw = ["不查了", "换个问题", "不管了", "先不查", "另外一个"]
    if any(kw in text for kw in cancel_kw):
        return "cancel_task"

    # New task signals
    if active_task:
        from .conversation_policy import _is_diagnosis_request
        if _is_diagnosis_request(text):
            return "new_task" if not active_task else "continue_task"

    # Side question signals (knowledge questions during active task)
    if active_task:
        from .conversation_policy import is_simple_knowledge_question
        if is_simple_knowledge_question(text):
            return "side_question"

    # Default
    if active_task:
        return "continue_task"
    return "uncertain"

