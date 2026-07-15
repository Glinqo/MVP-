"""Next action recommender - Phase 5.

Recommends specific next actions for a student based on their ability state.
Uses the priority formula:
    priority = job_weight * 0.25 + low_mastery * 0.30 + high_uncertainty * 0.20
             + safety_risk * 0.15 + recent_errors * 0.10
"""

from .ability_state_engine import compute_ability_state
from .graph import build_job_ability_graph, build_student_ability_graph
from .learning_event_store import get_ability_events


def recommend_next_actions(session_id, count=5):
    """Generate ranked next-action recommendations for a student.

    Args:
        session_id: Student session ID
        count: Max number of recommendations to return

    Returns:
        dict with actions[] and explanation
    """
    state = compute_ability_state(session_id)
    abilities = state.get("abilities", {})

    # Get job graph for importance weights
    try:
        job_graph = build_job_ability_graph()
        job_nodes = {n["id"]: n for n in job_graph.get("nodes", [])}
    except Exception:
        job_nodes = {}

    scored = []
    for aid, astate in abilities.items():
        priority, breakdown = _compute_priority(aid, astate, job_nodes, session_id)
        if priority > 0:
            scored.append({
                "ability_id": aid,
                "ability_name": astate.get("ability_name", aid),
                "priority": round(priority, 3),
                "priority_breakdown": breakdown,
                "status": astate.get("status", "unknown"),
                "cognitive_mastery": astate.get("cognitive_mastery_score", 0),
                "uncertainty": astate.get("uncertainty", 0),
                "recommended_action": astate.get("recommended_action", {}),
            })

    scored.sort(key=lambda x: -x["priority"])
    top = scored[:count]

    return {
        "session_id": session_id,
        "actions": [
            {
                "type": a["recommended_action"].get("type", "explain"),
                "title": a["recommended_action"].get("title", ""),
                "ability_id": a["ability_id"],
                "ability_name": a["ability_name"],
                "reason": a["recommended_action"].get("reason", ""),
                "estimated_minutes": a["recommended_action"].get("estimated_minutes", 10),
                "priority": a["priority"],
            }
            for a in top
        ],
        "total_abilities_scored": len(scored),
        "explanation": "???????????(0.25) + ????(0.30) + ?????(0.20) + ????(0.15) + ????(0.10)?",
    }


def _compute_priority(ability_id, astate, job_nodes, session_id):
    """Compute priority score with breakdown for an ability."""
    # Job weight (0.25)
    job_weight = 0.0
    if ability_id in job_nodes:
        job_node = job_nodes[ability_id]
        importance = job_node.get("importance", job_node.get("demand_weight", 0))
        if importance <= 1.0:
            importance *= 100
        job_weight = min(1.0, importance / 100)

    # Low mastery (0.30): invert cognitive score
    cognitive = astate.get("cognitive_mastery_score", 50) / 100.0
    low_mastery = max(0.0, 1.0 - cognitive)

    # High uncertainty (0.20)
    uncertainty = astate.get("uncertainty", 0.5)

    # Safety risk (0.15)
    safety_score = astate.get("safety_score", 100) / 100.0
    safety_risk = max(0.0, 1.0 - safety_score)

    # Recent errors (0.10)
    recent_errors = _compute_recent_error_factor(session_id, ability_id)

    priority = (
        job_weight * 0.25 +
        low_mastery * 0.30 +
        uncertainty * 0.20 +
        safety_risk * 0.15 +
        recent_errors * 0.10
    )

    breakdown = {
        "job_weight": round(job_weight, 2),
        "low_mastery": round(low_mastery, 2),
        "uncertainty": round(uncertainty, 2),
        "safety_risk": round(safety_risk, 2),
        "recent_errors": round(recent_errors, 2),
    }

    return priority, breakdown


def _compute_recent_error_factor(session_id, ability_id):
    """Compute recent error factor from event history."""
    try:
        evidence = get_ability_events(session_id, ability_id)
        events = evidence.get("events", [])
        if not events:
            return 0.0

        # Count recent negative events (last 10)
        recent = events[-10:]
        negative_count = sum(1 for e in recent if e.get("score_effect", 0) < 0)
        return min(1.0, negative_count / max(len(recent), 1) * 2.0)
    except Exception:
        return 0.0
