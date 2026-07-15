"""
Diagnostic trace standardization.

Converts raw session events into a normalized diagnostic trace suitable
for conformance checking against expert behavior models.

Borrows PM4Py event log concepts (trace, activity, timestamp) without
copying code or introducing AGPL dependencies.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .data_loader import ROOT
from .feedback import load_session_record


# Events to include in diagnostic traces (exclude pure UI, explanation, chat)
DIAGNOSTIC_EVENT_TYPES = {
    "scenario_started",
    "scenario_step_completed",
    "scenario_step_mistake",
    "diagnostic_action",
    "scenario_completed",
}

# Classification to risk level mapping
CLASSIFICATION_RISK = {
    "unsafe": 3,
    "premature": 2,
    "unsupported_hypothesis": 2,
    "closure_missing": 2,
    "valid_but_inefficient": 1,
    "repeated_low_value": 1,
    "valid": 0,
    "optimal": 0,
}

# Classification to cost category
CLASSIFICATION_COST = {
    "unsafe": "unsafe_intervention",
    "premature": "premature_program_check",
    "unsupported_hypothesis": "unsupported_hypothesis",
    "closure_missing": "closure_verification_missing",
    "repeated_low_value": "repeated_low_value_action",
    "valid_but_inefficient": "signal_chain_layer_jump",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_cost_config():
    path = ROOT / "knowledge" / "process_deviation_costs.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_cost(cost_config, cost_key):
    """Get the numeric cost for a deviation type."""
    costs = cost_config.get("costs", {})
    entry = costs.get(cost_key, {})
    return entry.get("cost", 1)


def extract_diagnostic_events(session_record):
    """Extract only diagnostic-relevant events from a session record."""
    events = session_record.get("events", [])
    return [e for e in events if e.get("event_type") in DIAGNOSTIC_EVENT_TYPES]


def build_diagnostic_trace(session_id, scenario_id, attempt=1):
    """
    Build a standardized diagnostic trace from session events.

    Returns:
        dict with trace_id, scenario_id, activities[]
    """
    record = load_session_record(session_id)
    all_events = extract_diagnostic_events(record)
    if scenario_id:
        events = [
            event for event in all_events
            if not event.get("scenario_id") or event.get("scenario_id") == scenario_id
        ]
    else:
        events = all_events

    activities = []
    for idx, event in enumerate(events):
        event_type = event.get("event_type", "")
        action_id = event.get("action_id", event.get("step_id", ""))
        classification = event.get("action_category", event.get("outcome", ""))
        ability_ids = event.get("ability_ids", [])

        # Normalize classification
        if classification in ("correct", "valid", "scenario_step_completed"):
            classification = "optimal"
        elif classification in ("incorrect", "scenario_step_mistake"):
            classification = "premature"

        risk_level = CLASSIFICATION_RISK.get(classification, 0)

        activities.append({
            "index": idx,
            "action_id": action_id,
            "event_type": event_type,
            "classification": classification,
            "ability_ids": ability_ids,
            "timestamp": event.get("created_at", ""),
            "risk_level": risk_level,
            "action_cost": get_cost(load_cost_config(), CLASSIFICATION_COST.get(classification, "move_on_log")),
            "scenario_id": event.get("scenario_id") or scenario_id,
            "strategy_bias": event.get("strategy_bias"),
            "note": event.get("note", ""),
            "source": event.get("source", "session_event"),
            "raw_event": event,
        })

    return {
        "trace_id": f"{session_id}:{scenario_id}:{attempt}",
        "session_id": session_id,
        "scenario_id": scenario_id,
        "attempt": attempt,
        "event_count": len(events),
        "events": events,
        "activities": activities,
    }


def list_student_traces(session_id):
    """List all diagnostic traces for a session (grouped by scenario)."""
    record = load_session_record(session_id)
    events = extract_diagnostic_events(record)

    # Group by scenario_id. Old scripted scenario events may not carry an
    # explicit scenario_id; keep them in a stable synthetic bucket so callers
    # still receive activities and evidence.
    traces = {}
    current_scenario = None
    attempt = 0

    for event in events:
        sid = event.get("scenario_id") or current_scenario or "scripted_scenario"
        if sid and sid != current_scenario:
            current_scenario = sid
            attempt += 1

        if current_scenario not in traces:
            traces[current_scenario] = {
                "scenario_id": current_scenario,
                "attempt": attempt,
                "activity_count": 0,
                "events": [],
            }
        traces[current_scenario]["activity_count"] += 1
        traces[current_scenario]["events"].append(event)

    result = []
    for trace in traces.values():
        full = build_diagnostic_trace(session_id, trace["scenario_id"], trace["attempt"])
        if not full.get("events"):
            full["events"] = trace["events"]
        if not full.get("activities"):
            full["activities"] = []
        full["activity_count"] = len(full.get("activities", []))
        result.append(full)
    return result
