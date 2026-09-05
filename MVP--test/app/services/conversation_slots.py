"""
Conversation slot management - Phase 2.

Centralizes slot schema, extraction from user messages, pending_slot
resolution, and merging UI context into server-side slot state.
"""

import re
from datetime import datetime, timezone
from .conversation_state import load_conversation_state, save_conversation_state


# ---------------------------------------------------------------------------
# Slot Schema (fixed, based on existing assist.py fields)
# ---------------------------------------------------------------------------

SLOT_SCHEMAS = {
    "sensor_led": {
        "label": "传感器动作灯",
        "values": ["on", "off", "unknown"],
        "aliases": {
            "on":  ["传感器灯亮", "传感器亮了", "传感器亮", "传感器动作灯亮"],
            "off": ["传感器灯不亮", "传感器不亮", "传感器没亮", "传感器动作灯不亮"],
        },
    },
    "plc_input_led": {
        "label": "PLC 输入指示灯",
        "values": ["on", "off", "unknown"],
        "aliases": {
            "on":  ["PLC输入灯亮", "PLC灯亮", "输入灯亮", "PLC 输入灯亮"],
            "off": ["PLC输入灯不亮", "PLC灯不亮", "输入灯不亮", "PLC 输入灯不亮"],
        },
    },
    "online_monitor": {
        "label": "PLC 在线监控",
        "values": ["changed", "unchanged", "unknown"],
        "aliases": {
            "changed":   ["变化", "有变化", "变了", "监控变了"],
            "unchanged": ["没变化", "不变", "没有变化", "没变", "监控不变", "监控没变"],
        },
    },
    "sensor_type": {
        "label": "传感器类型",
        "values": ["NPN", "PNP", "unknown"],
        "aliases": {
            "NPN": ["npn", "NPN型", "npn型"],
            "PNP": ["pnp", "PNP型", "pnp型"],
        },
    },
    "common_terminal": {
        "label": "PLC 输入公共端",
        "values": ["connected", "disconnected", "unknown"],
        "aliases": {
            "connected":    ["接了", "接好了", "接上", "已接", "连了", "接好"],
            "disconnected": ["没接", "未接", "没接好", "断开", "没连"],
        },
    },
}

ALL_SLOTS = list(SLOT_SCHEMAS.keys())

EMPTY_SLOT = {"value": "unknown", "source": None, "confidence": 0.0, "updated_turn": 0}


# ---------------------------------------------------------------------------
# Pending slot answer aliases (simpler, generic patterns for short answers)
# ---------------------------------------------------------------------------

PENDING_SLOT_ALIASES = {
    "sensor_led": {
        "on":  ["亮", "会亮", "亮了", "有"],
        "off": ["不亮", "没亮", "没有", "不是"],
    },
    "plc_input_led": {
        "on":  ["亮", "会亮", "亮了", "有", "是"],
        "off": ["不亮", "没亮", "没有", "不是"],
    },
    "online_monitor": {
        "changed":   ["变化", "有变化", "变了", "有", "是"],
        "unchanged": ["没变化", "不变", "没有变化", "没变", "没有", "不是"],
    },
    "sensor_type": {
        "NPN": ["npn", "NPN", "NPN型"],
        "PNP": ["pnp", "PNP", "PNP型"],
    },
    "common_terminal": {
        "connected":    ["接了", "接好了", "有", "是"],
        "disconnected": ["没接", "未接", "没有", "不是"],
    },
}
# ---------------------------------------------------------------------------
# Source priority mapping (higher = more authoritative)
# ---------------------------------------------------------------------------

SOURCE_PRIORITY = {
    "user_text":           5,
    "ui_context":          4,
    "pending_slot_answer": 3,
    "llm_extraction":      2,
    "system_inference":    1,
}


# ---------------------------------------------------------------------------
# Text-based slot extraction (rule-first)
# ---------------------------------------------------------------------------

def extract_slots_from_message(message):
    """Extract known slot values from a user message using rule-based patterns.

    Returns a dict of {slot_name: {"value": ..., "source": "user_text", "confidence": 1.0}}
    Matches longer patterns first to avoid greediness issues.
    """
    if not message:
        return {}

    text = str(message).strip()
    results = {}

    for slot_name, schema in SLOT_SCHEMAS.items():
        aliases = schema.get("aliases", {})
        all_pairs = []
        for canonical_value, patterns in aliases.items():
            for pattern in patterns:
                all_pairs.append((canonical_value, pattern))
        all_pairs.sort(key=lambda x: -len(x[1]))
        for canonical_value, pattern in all_pairs:
            if pattern in text:
                results[slot_name] = {
                    "value": canonical_value,
                    "source": "user_text",
                    "confidence": 1.0,
                    "updated_turn": 0,
                }
                break

    return results


# ---------------------------------------------------------------------------
# Pending slot resolution
# ---------------------------------------------------------------------------

def resolve_pending_slot_answer(pending_slot, user_message):
    """Try to resolve a short user message as an answer to the pending slot question.

    Uses PENDING_SLOT_ALIASES which contain shorter, more generic patterns
    suitable for short answers.

    Returns (slot_name, value_dict) or (None, None) if unrecognized.
    """
    if not pending_slot:
        return None, None

    text = str(user_message).strip().lower() if user_message else ""
    if not text:
        return None, None

    pending_aliases_map = PENDING_SLOT_ALIASES.get(pending_slot, {})
    if pending_aliases_map:
        all_pairs = []
        for canonical_value, patterns in pending_aliases_map.items():
            for pattern in patterns:
                all_pairs.append((canonical_value, pattern))
        all_pairs.sort(key=lambda x: -len(x[1]))
        for canonical_value, pattern in all_pairs:
            if pattern.lower() in text:
                return pending_slot, {
                    "value": canonical_value,
                    "source": "pending_slot_answer",
                    "confidence": 0.9,
                    "updated_turn": 0,
                }

    schema = SLOT_SCHEMAS.get(pending_slot)
    if schema:
        for canonical_value in schema.get("values", []):
            if canonical_value.lower() == text:
                return pending_slot, {
                    "value": canonical_value,
                    "source": "pending_slot_answer",
                    "confidence": 1.0,
                    "updated_turn": 0,
                }

    return None, None


# ---------------------------------------------------------------------------
# Slot update with source priority
# ---------------------------------------------------------------------------

def apply_slot_updates(existing_slots, new_slots):
    """Merge new_slots into existing_slots, respecting source priority.

    Higher-confidence / higher-priority sources win.
    Returns the merged slots dict.
    """
    merged = dict(existing_slots)

    for slot_name, new_val in new_slots.items():
        new_source = new_val.get("source", "system_inference")
        new_conf = new_val.get("confidence", 0.0)

        existing = merged.get(slot_name)
        if existing and isinstance(existing, dict):
            old_source = existing.get("source", "system_inference")
            old_conf = existing.get("confidence", 0.0)

            new_prio = SOURCE_PRIORITY.get(new_source, 0)
            old_prio = SOURCE_PRIORITY.get(old_source, 0)

            if new_source == old_source:
                if new_conf >= old_conf:
                    merged[slot_name] = new_val
            elif new_prio >= old_prio:
                merged[slot_name] = new_val
        else:
            merged[slot_name] = new_val

    return merged


# ---------------------------------------------------------------------------
# Missing slots detection
# ---------------------------------------------------------------------------

def get_missing_slots(slots, required_fields=None):
    """Return list of field names that are still unknown.
    
    If required_fields is None, checks all known slot schemas.
    """
    if required_fields is None:
        required_fields = ALL_SLOTS

    missing = []
    for field in required_fields:
        slot = slots.get(field, EMPTY_SLOT)
        if isinstance(slot, dict):
            value = slot.get("value", "unknown")
        else:
            value = str(slot) if slot else "unknown"
        if value in ("unknown", "", None):
            missing.append(field)
    return missing


# ---------------------------------------------------------------------------
# UI context merge
# ---------------------------------------------------------------------------

def merge_ui_context_into_slots(slots, ui_context):
    """Merge frontend form context into server-side slots.

    UI context values are treated with source="ui_context", confidence=0.85.
    """
    if not ui_context:
        return dict(slots)

    ui_slots = {}
    for key, value in ui_context.items():
        if key in SLOT_SCHEMAS and value and str(value).strip():
            str_val = str(value).strip()
            schema_vals = SLOT_SCHEMAS[key].get("values", [])
            aliases = SLOT_SCHEMAS[key].get("aliases", {})
            matched = None
            if str_val in schema_vals:
                matched = str_val
            else:
                for canonical, patterns in aliases.items():
                    if str_val in patterns or str_val.lower() in [p.lower() for p in patterns]:
                        matched = canonical
                        break
            if matched:
                ui_slots[key] = {
                    "value": matched,
                    "source": "ui_context",
                    "confidence": 0.85,
                    "updated_turn": 0,
                }

    return apply_slot_updates(slots, ui_slots)


# ---------------------------------------------------------------------------
# Convert slots to assist-compatible context dict
# ---------------------------------------------------------------------------

def slots_to_assist_context(slots):
    """Convert slot dict to a flat {field: value} dict for assist() context."""
    flat = {}
    for slot_name in ALL_SLOTS:
        slot = slots.get(slot_name)
        if isinstance(slot, dict):
            flat[slot_name] = slot.get("value", "unknown")
        else:
            flat[slot_name] = "unknown"
    return flat


# ---------------------------------------------------------------------------
# Slot summary for API response
# ---------------------------------------------------------------------------

def slots_summary(slots):
    """Return a compact summary of current slots for the frontend."""
    summary = {}
    for slot_name in ALL_SLOTS:
        slot = slots.get(slot_name)
        if isinstance(slot, dict):
            summary[slot_name] = slot.get("value", "unknown")
        else:
            summary[slot_name] = "unknown" if not slot else str(slot)
    return summary
