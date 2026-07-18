# -*- coding: utf-8 -*-
"""Diagnosis Task Success Scorer."""

def score_diagnosis_task(trace, success_criteria, hidden_ground_truth):
    """Score a diagnosis E2E task.
    Returns dict with diagnosis_level, success, actionable, metrics.
    """
    result = {"passed": [], "failed": [], "metrics": {}}

    # Diagnosis resolution levels:
    # 0 = no progress
    # 1 = identified symptom
    # 2 = identified subsystem
    # 3 = identified root cause
    # 4 = root cause + actionable fix

    all_assistant_text = " ".join(
        t.get("content", "") for t in trace if t.get("role") == "assistant"
    ).lower()

    root_cause = hidden_ground_truth.get("root_cause", "").lower()
    root_keywords = [w for w in root_cause.split() if len(w) > 1]

    # Level 0: no progress
    diagnosis_level = 0

    # Level 1: identified correct symptom area
    if any(kw in all_assistant_text for kw in ["传感器", "PLC", "输入", "信号"]):
        diagnosis_level = 1

    # Level 2: identified correct subsystem
    if any(kw in all_assistant_text for kw in root_keywords[:2]):
        diagnosis_level = 2

    # Level 3: identified root cause
    match_count = sum(1 for kw in root_keywords if kw in all_assistant_text)
    if match_count >= len(root_keywords) * 0.6:
        diagnosis_level = 3

    # Level 4: actionable fix provided
    action_keywords = ["接", "检查", "测量", "确认", "更换", "调整", "修复"]
    if diagnosis_level >= 3 and any(kw in all_assistant_text for kw in action_keywords):
        diagnosis_level = 4

    result["metrics"]["diagnosis_level"] = diagnosis_level
    result["metrics"]["actionable"] = diagnosis_level >= 3

    # Check must_identify keywords
    must_ids = success_criteria.get("must_identify", [])
    for kw in must_ids:
        if kw in all_assistant_text:
            result["passed"].append(f"identified:{kw}")
        else:
            result["failed"].append(f"not_identified:{kw}")

    # Check minimum diagnosis level
    min_level = success_criteria.get("min_diagnosis_level", 2)
    if diagnosis_level >= min_level:
        result["passed"].append(f"diagnosis_level:{diagnosis_level}")
    else:
        result["failed"].append(f"diagnosis_level:{diagnosis_level}<{min_level}")

    # Check if system asked about required unknowns
    must_ask = success_criteria.get("must_ask_about", [])
    for topic in must_ask:
        if any(topic in t.get("content", "") for t in trace if t.get("role") == "assistant"):
            result["passed"].append(f"asked_about:{topic}")
        else:
            result["failed"].append(f"did_not_ask:{topic}")

    total = len(result["passed"]) + len(result["failed"])
    result["score"] = len(result["passed"]) / max(total, 1)
    result["total"] = total
    return result


def score_learning_task(trace, success_criteria):
    """Score a learning E2E task."""
    result = {"passed": [], "failed": [], "metrics": {}}

    all_text = " ".join(
        t.get("content", "") for t in trace if t.get("role") == "assistant"
    ).lower()

    must_explain = success_criteria.get("must_explain", [])
    explained = sum(1 for kw in must_explain if kw in all_text)
    result["metrics"]["concepts_explained"] = explained

    min_concepts = success_criteria.get("min_concepts_explained", 2)
    if explained >= min_concepts:
        result["passed"].append(f"concepts:{explained}")
    else:
        result["failed"].append(f"concepts:{explained}<{min_concepts}")

    total = len(result["passed"]) + len(result["failed"])
    result["score"] = len(result["passed"]) / max(total, 1)
    result["total"] = total
    return result

