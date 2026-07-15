"""Learning event normalizer.

Converts all student behaviors into a single unified event schema.
Normalizes events from chat, quiz, explanation, scenario, feedback,
and device-state sources into the standard learning_event format.
"""

import hashlib
from datetime import datetime, timezone

# All supported event types
VALID_EVENT_TYPES = frozenset({
    "chat_question",
    "quiz_answered",
    "question_explained",
    "scenario_started",
    "diagnostic_action",
    "scenario_completed",
    "task_completed",
    "feedback_submitted",
    "device_state_recorded",
})

# Outcome polarity mapping
POSITIVE_OUTCOMES = frozenset({"optimal", "valid", "correct", "mastered", "improving"})
NEGATIVE_OUTCOMES = frozenset({"incorrect", "mistake", "weak", "unsafe", "premature",
                                "unsupported_hypothesis", "repeated_low_value"})


def normalize_event(raw_event):
    """Convert any existing event format to the unified learning_event schema.

    Args:
        raw_event: dict from any event source (chat, quiz, scenario, feedback, etc.)

    Returns:
        dict with unified learning_event schema, or None if un-normalizable.
    """
    if not raw_event or not isinstance(raw_event, dict):
        return None

    # Extract common fields, with fallbacks
    event_type = _infer_event_type(raw_event)
    if event_type is None:
        return None

    session_id = raw_event.get("session_id", "default")
    ability_ids = _extract_ability_ids(raw_event)
    scenario_id = raw_event.get("scenario_id") or raw_event.get("scenario", {}).get("id")
    action_id = raw_event.get("action_id") or raw_event.get("choice_id")

    # Category mapping
    category, polarity = _classify_category(raw_event, event_type)

    # Outcome
    outcome = _extract_outcome(raw_event, event_type)

    # Evidence weight (defaults to 1.0, adjusted by source reliability)
    evidence_weight = _compute_evidence_weight(event_type, outcome, raw_event)

    # Evidence summary
    evidence_summary = _build_evidence_summary(event_type, outcome, raw_event, ability_ids)

    # Generate deterministic event_id from key fields
    event_id = _generate_event_id(raw_event, session_id, event_type)

    # Timestamp
    created_at = raw_event.get("created_at") or raw_event.get("timestamp") or datetime.now(timezone.utc).isoformat()

    return {
        "event_id": event_id,
        "session_id": session_id,
        "event_type": event_type,
        "ability_ids": ability_ids,
        "scenario_id": scenario_id,
        "action_id": action_id,
        "category": category,
        "polarity": polarity,
        "outcome": outcome,
        "evidence_weight": evidence_weight,
        "evidence_summary": evidence_summary,
        "created_at": created_at,
        # Preserve original for traceability
        "_original_event_type": raw_event.get("event_type"),
        "_source": raw_event.get("source") or raw_event.get("_source"),
    }


def normalize_events(raw_events):
    """Normalize a list of events, filtering out un-normalizable ones."""
    result = []
    for e in (raw_events or []):
        norm = normalize_event(e)
        if norm:
            result.append(norm)
    return result


def _infer_event_type(raw_event):
    """Infer the standard event_type from a raw event."""
    raw_type = raw_event.get("event_type", "")

    # Direct mapping
    type_map = {
        "chat_message": "chat_question",
        "score": "quiz_answered",
        "diagnosis": "quiz_answered",
        "question_explained": "question_explained",
        "knowledge_explained": "question_explained",
        "scenario_started": "scenario_started",
        "scenario_step_completed": "diagnostic_action",
        "scenario_step_mistake": "diagnostic_action",
        "diagnostic_action": "diagnostic_action",
        "feedback": "feedback_submitted",
        "task_completed": "task_completed",
        "device_state_recorded": "device_state_recorded",
    }

    if raw_type in type_map:
        return type_map[raw_type]

    # Infer from other fields
    if raw_event.get("scenario_id") and raw_event.get("action_id"):
        return "diagnostic_action"
    if raw_event.get("feedback"):
        return "feedback_submitted"
    if raw_event.get("outcome") and raw_event.get("ability_ids"):
        return "diagnostic_action"

    return None


def _extract_ability_ids(raw_event):
    """Extract ability_ids from various formats."""
    # Direct field
    ids = raw_event.get("ability_ids", [])
    if ids and isinstance(ids, list):
        return ids

    # ability_hits format (scenario)
    hits = raw_event.get("ability_hits", [])
    if hits and isinstance(hits, list):
        return [h.get("id") or h.get("ability_id") for h in hits if isinstance(h, dict)]

    # Single ability_id
    aid = raw_event.get("ability_id")
    if aid:
        return [aid]

    # From note parsing
    note = raw_event.get("note", "")
    # Common patterns: "ability_name / ..."
    parts = note.split("/")
    if len(parts) > 1:
        first = parts[0].strip()
        # Could be a title, not an ID

    return []


def _classify_category(raw_event, event_type):
    """Determine category and polarity."""
    if event_type in ("chat_question", "quiz_answered", "question_explained"):
        return "knowledge", _polarity_from_outcome(raw_event)
    if event_type in ("scenario_started",):
        return "procedure", "neutral"
    if event_type in ("diagnostic_action", "scenario_completed"):
        return "procedure", _polarity_from_outcome(raw_event)
    if event_type in ("task_completed",):
        return "procedure", "positive"
    if event_type in ("feedback_submitted",):
        return "meta", "neutral"
    if event_type in ("device_state_recorded",):
        return "evidence", "neutral"
    return "general", "neutral"


def _polarity_from_outcome(raw_event):
    """Map outcome/classification to polarity."""
    outcome = str(raw_event.get("outcome", "")).lower()
    classification = str(raw_event.get("classification", "")).lower()
    is_correct = raw_event.get("is_correct")

    if is_correct is True:
        return "positive"
    if is_correct is False:
        return "negative"

    combined = outcome + " " + classification
    if any(w in combined for w in POSITIVE_OUTCOMES):
        return "positive"
    if any(w in combined for w in NEGATIVE_OUTCOMES):
        return "negative"

    return "neutral"


def _extract_outcome(raw_event, event_type):
    """Extract human-readable outcome string."""
    outcome = raw_event.get("outcome")
    if outcome:
        return str(outcome)

    classification = raw_event.get("classification")
    if classification:
        return str(classification)

    is_correct = raw_event.get("is_correct")
    if is_correct is True:
        return "correct"
    if is_correct is False:
        return "incorrect"

    if event_type in ("scenario_started", "feedback_submitted", "device_state_recorded"):
        return "recorded"

    return "unknown"


def _compute_evidence_weight(event_type, outcome, raw_event):
    """Compute evidence weight based on source reliability.

    Higher weight = stronger evidence for the ability assessment.
    """
    base = 1.0

    # Source-type adjustments
    source = raw_event.get("source") or raw_event.get("source_type", "")
    if source in ("enterprise_official", "teacher_material"):
        base = 1.2
    elif source in ("job_posting", "recruitment_platform"):
        base = 0.9
    elif source == "project_curated":
        base = 1.0

    # Event-type adjustments
    if event_type == "diagnostic_action":
        # Direct procedure evidence is strong
        base *= 1.0
    elif event_type == "quiz_answered":
        base *= 0.8
    elif event_type == "chat_question":
        base *= 0.6

    # Outcome adjustments
    if outcome in ("unsafe", "invalid"):
        base *= 0.3  # Low-weight negative evidence
    elif outcome in ("premature", "unsupported_hypothesis"):
        base *= 0.5

    return round(base, 2)


def _build_evidence_summary(event_type, outcome, raw_event, ability_ids):
    """Build a concise human-readable evidence summary."""
    type_labels = {
        "chat_question": "????",
        "quiz_answered": "????",
        "question_explained": "????",
        "scenario_started": "??????",
        "diagnostic_action": "??????",
        "scenario_completed": "??????",
        "task_completed": "??????",
        "feedback_submitted": "????",
        "device_state_recorded": "??????",
    }

    label = type_labels.get(event_type, event_type)

    note = raw_event.get("note") or raw_event.get("evidence_summary") or ""
    if note:
        return f"{label}?{note[:60]}"

    # Build from ability names if available
    if ability_ids:
        names = raw_event.get("ability_names") or []
        if names:
            return f"{label}????{'?'.join(names[:3])}?"

    outcome_text = str(outcome) if outcome and outcome not in ("unknown", "recorded") else ""
    if outcome_text:
        return f"{label}?{outcome_text}?"

    return label


def _generate_event_id(raw_event, session_id, event_type):
    """Generate a deterministic event_id from key fields."""
    event_id = raw_event.get("event_id")
    if event_id:
        return event_id

    # Build from key fields for idempotency
    parts = [
        session_id,
        event_type,
        raw_event.get("scenario_id") or "",
        raw_event.get("action_id") or raw_event.get("choice_id") or "",
        raw_event.get("created_at") or raw_event.get("timestamp") or "",
    ]
    raw = "|".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f"evt_{h}"
