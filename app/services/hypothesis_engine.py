"""
Hypothesis management engine for troubleshooting scenarios.

Manages hypothesis lifecycle: initialization, evidence-based update,
elimination of impossible hypotheses, and ranking of remaining hypotheses.

Uses set-based elimination and rule-based confidence levels.
No probabilistic inference, no LLM.
"""

import json
from pathlib import Path

from .data_loader import ROOT


POLICY_PATH = ROOT / "knowledge" / "diagnostic_action_policy.json"


def load_policy():
    if not POLICY_PATH.exists():
        return {}
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def initialize_hypotheses(model):
    """
    Initialize the full hypothesis set from the model.

    Returns:
        dict with hypothesis_id -> {id, label, confidence, status, evidence_for, evidence_against}
    """
    hypotheses = model.get("hypotheses", [])
    result = {}
    for hyp in hypotheses:
        result[hyp["id"]] = {
            "id": hyp["id"],
            "label": hyp.get("label", hyp["id"]),
            "description": hyp.get("description", ""),
            "confidence": _initial_confidence(hyp),
            "status": "active",
            "evidence_for": [],
            "evidence_against": [],
            "related_abilities": hyp.get("related_abilities", []),
        }
    return result


def _initial_confidence(hypothesis):
    """Assign initial confidence based on rule-based heuristics."""
    label = hypothesis.get("label", "")
    # Common failures get slightly higher initial confidence (domain heuristic)
    if "公共端" in label:
        return 0.30
    if "接线" in label:
        return 0.25
    if "模块" in label:
        return 0.15
    if "类型" in label:
        return 0.15
    if "程序" in label:
        return 0.15
    return 0.20


def update_hypotheses(hypotheses, revealed_evidence, action_id=None):
    """
    Update hypothesis status based on newly revealed evidence.

    revealed_evidence: dict of {fact_key: value} from the action's produces_state
    or observation.

    Returns:
        Updated hypotheses dict, and a list of update records.
    """
    updates = []

    for hid, hyp in hypotheses.items():
        if hyp["status"] != "active":
            continue

        # Check supporting/refuting evidence from the model
        model = _get_model_for_hypothesis(hid)
        if not model:
            continue

        hyp_def = None
        for h in model.get("hypotheses", []):
            if h["id"] == hid:
                hyp_def = h
                break

        if not hyp_def:
            continue

        supporting = hyp_def.get("supporting_evidence", [])
        refuting = hyp_def.get("refuting_evidence", [])

        # Check revealed evidence against supporting/refuting
        evidence_texts = []
        for key, value in revealed_evidence.items():
            evidence_texts.append(f"{key}={value}")

        evidence_str = " ".join(evidence_texts).lower()

        # Check refuting: does revealed evidence match any refuting pattern?
        for ref in refuting:
            if _evidence_matches(ref, revealed_evidence, evidence_str):
                hyp["status"] = "eliminated"
                hyp["evidence_against"].append(ref)
                updates.append({
                    "hypothesis_id": hid,
                    "label": hyp["label"],
                    "change": "eliminated",
                    "reason": f"反驳证据出现: {ref}",
                    "evidence": ref,
                })
                break

        if hyp["status"] != "active":
            continue

        # Check supporting
        for sup in supporting:
            if _evidence_matches(sup, revealed_evidence, evidence_str):
                if sup not in hyp["evidence_for"]:
                    hyp["evidence_for"].append(sup)
                    hyp["confidence"] = min(0.95, hyp["confidence"] + 0.15)
                    updates.append({
                        "hypothesis_id": hid,
                        "label": hyp["label"],
                        "change": "strengthened",
                        "reason": f"支持证据出现: {sup}",
                        "evidence": sup,
                    })

    return hypotheses, updates


def _evidence_matches(evidence_pattern, revealed_evidence, evidence_str):
    """Check if revealed evidence matches a pattern string."""
    # Simple keyword matching
    pattern_lower = evidence_pattern.lower()
    if any(kw in evidence_str for kw in pattern_lower.split()):
        return True
    # Check against individual keys
    for key, value in revealed_evidence.items():
        if str(key).lower() in pattern_lower or str(value).lower() in pattern_lower:
            return True
    return False


def _get_model_for_hypothesis(hypothesis_id):
    """Find which model contains this hypothesis."""
    from .model_tracer import _load_models
    models = _load_models()
    for model in models.values():
        for hyp in model.get("hypotheses", []):
            if hyp["id"] == hypothesis_id:
                return model
    return None


def eliminate_impossible_hypotheses(hypotheses, known_facts):
    """
    Eliminate hypotheses that contradict known facts.

    Uses the model's remaining_hypotheses in each state.
    """
    eliminated = []
    state_remaining = set()
    for fact in known_facts:
        if fact.startswith("remaining_hypotheses="):
            # This is a special fact carrying the state's remaining_hypotheses
            # Not used currently; state-based elimination is done differently
            pass

    for hid, hyp in list(hypotheses.items()):
        if hyp["status"] == "active":
            # Check refuting evidence accumulation
            if len(hyp["evidence_against"]) >= 2:
                hyp["status"] = "eliminated"
                eliminated.append({
                    "hypothesis_id": hid,
                    "label": hyp["label"],
                    "reason": "多条反驳证据累积",
                })

    return hypotheses, eliminated


def rank_remaining_hypotheses(hypotheses):
    """
    Rank remaining active hypotheses by confidence (descending).

    Returns:
        List of hypothesis dicts, sorted by confidence.
    """
    active = [h for h in hypotheses.values() if h["status"] == "active"]
    active.sort(key=lambda h: -h["confidence"])
    return active


def active_hypothesis_count(hypotheses):
    """Count active (not eliminated) hypotheses."""
    return sum(1 for h in hypotheses.values() if h["status"] == "active")


def active_hypothesis_ids(hypotheses):
    """Get list of active hypothesis IDs."""
    return [h["id"] for h in hypotheses.values() if h["status"] == "active"]


def get_hypotheses_summary(hypotheses):
    """Get a summary suitable for API response."""
    active = rank_remaining_hypotheses(hypotheses)
    eliminated = [h for h in hypotheses.values() if h["status"] == "eliminated"]
    return {
        "active_count": len(active),
        "eliminated_count": len(eliminated),
        "total_count": len(hypotheses),
        "active": [
            {"id": h["id"], "label": h["label"], "confidence": round(h["confidence"], 2)}
            for h in active
        ],
        "eliminated": [
            {"id": h["id"], "label": h["label"], "evidence_against": h.get("evidence_against", [])[:2]}
            for h in eliminated
        ],
    }
