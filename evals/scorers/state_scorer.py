# -*- coding: utf-8 -*-
"""L1 State Scorer - deterministic, no LLM judge."""
import json

def score_state(expected, actual):
    """ScoreConversationState against expected values.
    Returns dict with passed, failed, details.
    """
    results = {"passed": [], "failed": [], "score": 0.0, "total": 0}

    # Check slots
    exp_slots = expected.get("slots", {})
    act_slots = actual.get("slots", {})
    for key, exp_val in exp_slots.items():
        results["total"] += 1
        act_val = act_slots.get(key)
        # Unwrap dict-format slot values: {"value": "on", ...}
        if isinstance(act_val, dict):
            act_val = act_val.get("value")
        if act_val == exp_val:
            results["passed"].append(f"slot:{key}={exp_val}")
        else:
            results["failed"].append(f"slot:{key} expected={exp_val} got={act_val}")

    # Check pending_slot
    if "pending_slot" in expected:
        results["total"] += 1
        act_pending = actual.get("pending_slot")
        if act_pending == expected["pending_slot"]:
            results["passed"].append(f"pending_slot={expected['pending_slot']}")
        else:
            results["failed"].append(f"pending_slot expected={expected['pending_slot']} got={act_pending}")

    # Check slot retention
    if "slots_preserved" in expected:
        for key in expected["slots_preserved"]:
            results["total"] += 1
            if key in act_slots:
                results["passed"].append(f"slot_preserved:{key}")
            else:
                results["failed"].append(f"slot_preserved:{key} MISSING")

    # Check active_task_changed
    if "active_task_changed" in expected:
        results["total"] += 1
        act_changed = actual.get("active_task_changed", False)
        if act_changed == expected["active_task_changed"]:
            results["passed"].append(f"active_task_changed={act_changed}")
        else:
            results["failed"].append(f"active_task_changed expected={expected['active_task_changed']} got={act_changed}")

    # Calculate score
    if results["total"] > 0:
        results["score"] = len(results["passed"]) / results["total"]
    return results


def score_slot_accuracy(expected, actual):
    """Compute slot accuracy: exact match on expected slot values."""
    exp_slots = expected.get("slots", {})
    act_slots = actual.get("slots", {})
    if not exp_slots:
        return {"accuracy": 1.0, "matched": 0, "total": 0, "detail": "no slots expected"}
    matched = sum(1 for k, v in exp_slots.items() if act_slots.get(k) == v)
    return {"accuracy": matched / len(exp_slots), "matched": matched, "total": len(exp_slots),
            "detail": {k: {"expected": v, "actual": act_slots.get(k)} for k, v in exp_slots.items()}}

