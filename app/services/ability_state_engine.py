"""Ability state engine - Phase 2.

Unified engine that computes per-ability mastery scores, status, uncertainty,
and generates explainable evidence chains from normalized learning events.

Wraps and extends student_mastery_profile.py with:
- Explicit state machine (unknown -> touched -> weak -> improving -> mastered)
- Uncertainty calculation from evidence sparsity/age/conflict
- Evidence chain explanation for each node
- Status transition rules
"""

from collections import defaultdict
from datetime import datetime, timezone
from .student_mastery_profile import (
    build_student_mastery_profile,
    scalar100,
    safety_score,
    transfer_score,
    procedure_mastery,
    strategy_tags_for_ability,
    aggregate_metrics,
)
from .diagnostic_trace import list_student_traces
from .strategy_profile import build_cumulative_strategy_profile
from .coverage_matrix import build_coverage_matrix
from .learning_event_store import get_ability_events


# Status thresholds
UNCERTAINTY_HIGH = 0.7
UNCERTAINTY_MEDIUM = 0.4
MASTERY_THRESHOLD = 75
IMPROVING_THRESHOLD = 55
WEAK_THRESHOLD = 35


def compute_ability_state(session_id, ability_id=None):
    """Compute complete ability state for one or all abilities.

    Returns per-ability:
    - Four scores (knowledge, procedure, transfer, safety)
    - cognitive_mastery_score (fused)
    - uncertainty (0-1)
    - status (unknown/touched/weak/improving/mastered)
    - status_reason (why this status)
    - evidence_summary (counts, recency, conflict flag)
    - recommended_action (type, title, reason)
    """
    from .graph import build_student_ability_graph
    nodes = build_student_ability_graph(session_id).get("nodes", [])

    profile = build_student_mastery_profile(session_id, nodes)
    abilities = profile.get("abilities", {})

    if ability_id:
        node = next((n for n in nodes if n.get("id") == ability_id), {})
        state = abilities.get(ability_id, {})
        return _build_single_state(ability_id, state, node, session_id)

    # All abilities
    result = {}
    for node in nodes:
        aid = node.get("id")
        if not aid:
            continue
        state = abilities.get(aid, _default_state(aid, node))
        result[aid] = _build_single_state(aid, state, node, session_id)

    return {
        "session_id": session_id,
        "abilities": result,
        "summary": profile.get("strategy_profile", {}),
    }


def _default_state(ability_id, node):
    return {
        "knowledge_mastery": scalar100(node.get("mastery_score", 0)),
        "procedure_mastery": 0,
        "transfer_score": 0,
        "safety_score": 100,
        "uncertainty": 1.0,
        "process_metrics": {},
        "strategy_tags": [],
        "cross_scenario_validated": False,
    }


def _build_single_state(ability_id, state, node, session_id):
    """Build a complete single-ability state dict."""
    knowledge = state.get("knowledge_mastery", scalar100(node.get("mastery_score", 0)))
    procedure = state.get("procedure_mastery", 0)
    transfer = state.get("transfer_score", 0)
    safety = state.get("safety_score", 100)
    cognitive = state.get("cognitive_mastery_score", _fuse(knowledge, procedure, transfer, safety))
    uncertainty_val = state.get("uncertainty", _calc_uncertainty(node, state))

    status, status_reason = _determine_status(
        knowledge, procedure, transfer, safety, uncertainty_val, state, node
    )

    evidence_summary = _build_evidence_summary(state, node, session_id, ability_id)

    # Recommended action
    recommended = state.get("recommended_intervention") or _generate_recommendation(
        ability_id, node.get("label", ability_id), status,
        knowledge, procedure, transfer, safety, uncertainty_val, state
    )

    return {
        "ability_id": ability_id,
        "ability_name": node.get("label", ability_id),
        "level": node.get("level", "basic"),
        "knowledge_mastery": knowledge,
        "procedure_mastery": procedure,
        "transfer_score": transfer,
        "safety_score": safety,
        "cognitive_mastery_score": cognitive,
        "uncertainty": round(uncertainty_val, 2),
        "status": status,
        "status_reason": status_reason,
        "evidence_summary": evidence_summary,
        "recommended_action": recommended,
        "cross_scenario_validated": state.get("cross_scenario_validated", False),
        "safety_gate": state.get("safety_gate", {"passed": True, "reason": ""}),
        "process_metrics": state.get("process_metrics", {}),
        "strategy_tags": state.get("strategy_tags", []),
        # Evidence events from Phase 1
        "recent_events": state.get("normalized_events", [])[:5],
    }


def _fuse(knowledge, procedure, transfer, safety):
    """Fuse four dimensions into a single cognitive mastery score."""
    return int(round(
        knowledge * 0.25 +
        procedure * 0.35 +
        transfer * 0.20 +
        safety * 0.20
    ))


def _calc_uncertainty(node, state):
    """Calculate uncertainty from evidence sparsity, age, and conflict."""
    evidence_count = node.get("evidence_count", 0)
    confidence = node.get("confidence", 0)

    # Base uncertainty from evidence count
    if evidence_count == 0:
        base = 0.9
    elif evidence_count <= 2:
        base = 0.7
    elif evidence_count <= 5:
        base = 0.5
    elif evidence_count <= 10:
        base = 0.3
    else:
        base = 0.15

    # Confidence inversion (low confidence = high uncertainty)
    if confidence > 0:
        conf_factor = 1.0 - confidence
        base = (base + conf_factor) / 2

    # Evidence age penalty
    last_updated = node.get("last_updated_at")
    if last_updated:
        try:
            last_dt = datetime.fromisoformat(str(last_updated).replace("Z", "+00:00"))
            days_ago = (datetime.now(timezone.utc) - last_dt).days
            if days_ago > 30:
                base += 0.2
            elif days_ago > 14:
                base += 0.1
        except (ValueError, TypeError):
            pass

    # Evidence conflict: if both positive and negative exist
    proc_metrics = state.get("process_metrics", {})
    if proc_metrics.get("evidence_quality", 0) < 0.5:
        base += 0.1

    return min(1.0, max(0.0, base))


def _determine_status(knowledge, procedure, transfer, safety, uncertainty_val, state, node):
    """Determine ability status with explicit reasoning."""
    cognitive = _fuse(knowledge, procedure, transfer, safety)
    evidence_count = node.get("evidence_count", 0)

    if evidence_count == 0:
        return "unknown", "?????????"

    if evidence_count <= 2 and uncertainty_val > UNCERTAINTY_HIGH:
        return "touched", "???????????????????????????"

    if safety < 60:
        return "weak", "????????????????????"

    if cognitive >= MASTERY_THRESHOLD and uncertainty_val < UNCERTAINTY_MEDIUM:
        return "mastered", f"??????({cognitive})?????(????{uncertainty_val:.2f})?"

    if cognitive >= IMPROVING_THRESHOLD:
        return "improving", f"?????({cognitive})???????"

    if cognitive <= WEAK_THRESHOLD:
        return "weak", f"?????({cognitive})???"

    # Check for negative evidence
    proc_metrics = state.get("process_metrics", {})
    if proc_metrics.get("fault_localization", 1.0) < 0.4:
        return "weak", "?????????????????????"

    return "improving", "???????????????????"


def _build_evidence_summary(state, node, session_id, ability_id):
    """Build evidence summary with counts, recency, and confidence."""
    evidence_count = node.get("evidence_count", 0)
    confidence = node.get("confidence", 0)
    last_updated = node.get("last_updated_at")

    # Get event-level evidence from Phase 1 store
    try:
        ability_evidence = get_ability_events(session_id, ability_id)
        event_count = ability_evidence.get("event_count", 0)
    except Exception:
        event_count = evidence_count

    return {
        "total_evidence": max(evidence_count, event_count),
        "confidence": round(confidence, 2),
        "last_updated_at": last_updated,
        "positive_count": sum(1 for e in state.get("normalized_events", []) if e.get("polarity") == "positive"),
        "negative_count": sum(1 for e in state.get("normalized_events", []) if e.get("polarity") == "negative"),
        "cross_scenario": state.get("cross_scenario_validated", False),
    }


def _generate_recommendation(ability_id, ability_name, status, knowledge, procedure, transfer, safety, uncertainty_val, state=None):
    """Generate a recommended action based on ability state."""
    state = state or {}
    if status == "unknown":
        return {
            "type": "explain",
            "title": f"???{ability_name}??????",
            "reason": "?????????????????????????",
            "estimated_minutes": 10,
        }
    if status == "touched":
        return {
            "type": "quiz",
            "title": f"???{ability_name}?????",
            "reason": "????????????????????",
            "estimated_minutes": 8,
        }
    if status == "weak":
        if safety < 60:
            return {
                "type": "safety_review",
                "title": f"???{ability_name}????????",
                "reason": "????????????????????????????",
                "estimated_minutes": 15,
            }
        return {
            "type": "scenario_practice",
            "title": f"????{ability_name}????????",
            "reason": f"???????({_fuse(knowledge, procedure, transfer, safety)})???????????",
            "estimated_minutes": 15,
        }
    if status == "improving":
        if not state.get("cross_scenario_validated", False):
            return {
                "type": "cross_scenario",
                "title": f"??????????{ability_name}?",
                "reason": "????????????????????",
                "estimated_minutes": 12,
            }
        return {
            "type": "scenario_practice",
            "title": f"?????????{ability_name}???",
            "reason": "????????????????",
            "estimated_minutes": 12,
        }
    if status == "mastered":
        if uncertainty_val > UNCERTAINTY_MEDIUM:
            return {
                "type": "quiz",
                "title": f"???{ability_name}??????",
                "reason": "???????????????????????",
                "estimated_minutes": 5,
            }
        return {
            "type": "reflection",
            "title": f"????????{ability_name}?",
            "reason": "??????????????????",
            "estimated_minutes": 10,
        }
    return {
        "type": "explain",
        "title": f"???{ability_name}?",
        "reason": "???????????",
        "estimated_minutes": 10,
    }
