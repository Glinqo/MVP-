"""Learning event store.

Provides queryable access to normalized student learning events.
Backed by the existing session JSON files, but presents events through
the normalized schema.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .data_loader import ROOT
from .feedback import load_session_record, safe_session_id
from .learning_event_normalizer import normalize_events, normalize_event

SESSIONS_DIR = ROOT / "data" / "sessions"


def get_events(session_id, event_type=None, ability_id=None, scenario_id=None,
               category=None, limit=100, offset=0, since=None, until=None):
    """Query normalized events for a session with optional filters.

    Args:
        session_id: Student session ID
        event_type: Filter by event type (e.g., "diagnostic_action")
        ability_id: Filter by ability ID
        scenario_id: Filter by scenario ID
        category: Filter by category (knowledge/procedure/evidence/meta)
        limit: Max events to return
        offset: Pagination offset
        since: ISO datetime, only events after this
        until: ISO datetime, only events before this

    Returns:
        dict with events[], total, filters_applied
    """
    record = load_session_record(session_id)
    raw_events = record.get("events", [])
    normalized = normalize_events(raw_events)

    # Apply filters
    if event_type:
        normalized = [e for e in normalized if e["event_type"] == event_type]
    if ability_id:
        normalized = [e for e in normalized if ability_id in e.get("ability_ids", [])]
    if scenario_id:
        normalized = [e for e in normalized if e.get("scenario_id") == scenario_id]
    if category:
        normalized = [e for e in normalized if e["category"] == category]
    if since:
        normalized = [e for e in normalized if e.get("created_at", "") >= since]
    if until:
        normalized = [e for e in normalized if e.get("created_at", "") <= until]

    total = len(normalized)
    page = normalized[offset:offset + limit]

    return {
        "session_id": session_id,
        "events": page,
        "total": total,
        "returned": len(page),
        "offset": offset,
        "limit": limit,
        "filters": {
            "event_type": event_type,
            "ability_id": ability_id,
            "scenario_id": scenario_id,
            "category": category,
            "since": since,
            "until": until,
        },
    }


def append_normalized_event(session_id, raw_event):
    """Append an event to the session, returning its normalized form.

    This is the single entry point for all new events. It:
    1. Normalizes the event
    2. Appends to session store
    3. Returns the normalized event

    Args:
        session_id: Student session ID
        raw_event: Raw event dict from any source

    Returns:
        dict with normalized_event and saved confirmation
    """
    norm = normalize_event(raw_event)
    if not norm:
        raise ValueError(f"Cannot normalize event: {raw_event}")

    # Append to session store (the raw format for backward compatibility)
    from .feedback import append_session_event
    append_session_event(session_id, raw_event)

    return {
        "saved": True,
        "session_id": session_id,
        "normalized_event": norm,
    }


def get_event_timeline(session_id):
    """Get a chronological timeline of all normalized events.

    Returns events sorted by created_at, with summary statistics.
    """
    result = get_events(session_id, limit=10000)
    events = result["events"]

    # Compute stats
    by_type = {}
    by_category = {}
    by_polarity = {"positive": 0, "negative": 0, "neutral": 0}
    ability_events = {}
    scenario_events = {}

    for e in events:
        et = e["event_type"]
        by_type[et] = by_type.get(et, 0) + 1

        cat = e["category"]
        by_category[cat] = by_category.get(cat, 0) + 1

        pol = e["polarity"]
        by_polarity[pol] = by_polarity.get(pol, 0) + 1

        for aid in e.get("ability_ids", []):
            ability_events[aid] = ability_events.get(aid, 0) + 1

        sid = e.get("scenario_id")
        if sid:
            scenario_events[sid] = scenario_events.get(sid, 0) + 1

    return {
        "session_id": session_id,
        "total_events": len(events),
        "events": events,
        "stats": {
            "by_type": by_type,
            "by_category": by_category,
            "by_polarity": by_polarity,
            "by_ability": ability_events,
            "by_scenario": scenario_events,
        },
    }


def get_ability_events(session_id, ability_id):
    """Get all events related to a specific ability, with score effects."""
    events = get_events(session_id, ability_id=ability_id, limit=10000)["events"]

    result = []
    running_score = 50  # baseline
    for e in events:
        score_effect = 0
        pol = e["polarity"]
        weight = e.get("evidence_weight", 1.0)

        if pol == "positive":
            score_effect = int(round(10 * weight))
        elif pol == "negative":
            score_effect = int(round(-8 * weight))

        running_score = max(0, min(100, running_score + score_effect))

        result.append({
            "event_type": e["event_type"],
            "summary": e["evidence_summary"],
            "outcome": e["outcome"],
            "polarity": pol,
            "score_effect": score_effect,
            "running_mastery": running_score,
            "created_at": e["created_at"],
        })

    return {
        "ability_id": ability_id,
        "event_count": len(result),
        "events": result,
    }


def list_sessions():
    """List all student sessions with basic metadata."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    for path in sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            event_count = len(record.get("events", []))
            sessions.append({
                "session_id": record.get("session_id", path.stem),
                "event_count": event_count,
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
                "feedback": record.get("feedback"),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return {"sessions": sessions, "total": len(sessions)}
