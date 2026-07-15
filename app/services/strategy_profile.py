"""
Student troubleshooting strategy profile.

Analyzes recurring patterns in student diagnostic traces to build a
strategy profile with: weakness tags, strength tags, preferred strategy,
and persistence tracking.

Persistence rules (avoids one-off labeling):
- observed: seen once
- recurring: seen across 2+ steps within same scenario
- persistent: seen across 2+ different scenarios
"""

from collections import Counter, defaultdict

from .diagnostic_trace import build_diagnostic_trace, list_student_traces
from .model_tracer import model_for_scenario
from .conformance_engine import align_trace, select_best_expert_strategy


# Classification to weakness tag mapping
WEAKNESS_TAGS = {
    "unsafe": {
        "tag": "safety_procedure_gap",
        "label": "安全规程缺口",
        "severity": "critical",
    },
    "premature": {
        "tag": "program_first_bias",
        "label": "过早归因程序",
        "severity": "medium",
    },
    "unsupported_hypothesis": {
        "tag": "trial_and_error_pattern",
        "label": "试错模式",
        "severity": "medium",
    },
    "closure_missing": {
        "tag": "closure_verification_gap",
        "label": "闭环验证缺失",
        "severity": "medium",
    },
    "repeated_low_value": {
        "tag": "repeated_low_value_pattern",
        "label": "重复低价值观察",
        "severity": "low",
    },
    "valid_but_inefficient": {
        "tag": "inefficient_path_pattern",
        "label": "低效路径偏好",
        "severity": "low",
    },
}

STRENGTH_TAGS = {
    "optimal_safety_pattern": {"tag": "safety_first_habit", "label": "安全优先习惯"},
    "evidence_before_conclusion": {"tag": "evidence_driven", "label": "证据驱动排故"},
    "systematic_approach": {"tag": "systematic_approach", "label": "系统化方法"},
    "closure_verification_strength": {"tag": "closure_verification_habit", "label": "闭环验证习惯"},
}


def build_strategy_profile(session_id, scenario_id):
    """
    Build a strategy profile from a single diagnostic trace.

    Returns:
        dict with weaknesses, strengths, preferred_strategy_id, tags
    """
    trace = build_diagnostic_trace(session_id, scenario_id)
    activities = trace.get("activities", [])

    # Count classifications
    class_counts = Counter(a.get("classification", "valid") for a in activities)

    # Weaknesses
    weaknesses = []
    for classification, info in WEAKNESS_TAGS.items():
        count = class_counts.get(classification, 0)
        if count > 0:
            severity = info["severity"]
            weaknesses.append({
                "tag": info["tag"],
                "label": info["label"],
                "count": count,
                "severity": severity,
                "evidence_event_ids": [
                    a.get("action_id", "") for a in activities
                    if a.get("classification") == classification
                ][:3],
            })

    weaknesses.sort(key=lambda w: (
        {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(w["severity"], 99),
        -w["count"]
    ))

    # Strengths
    strengths = []
    optimal_count = class_counts.get("optimal", 0)
    valid_count = class_counts.get("valid", 0)
    evidence_actions = {"CHECK_COMMON_TERMINAL", "CHECK_WIRING", "CHECK_SENSOR_TYPE",
                         "CHECK_DC24V", "CHECK_DISTANCE_AND_TARGET", "CHECK_ADDRESS_MAPPING"}
    activity_ids = [a.get("action_id", "") for a in activities]

    if optimal_count >= 2:
        strengths.append({"tag": "systematic_approach", "label": "系统化方法", "evidence_event_ids": []})
    if any(aid in evidence_actions for aid in activity_ids) and class_counts.get("premature", 0) == 0:
        strengths.append({"tag": "evidence_driven", "label": "证据驱动排故", "evidence_event_ids": []})
    if any(aid == "VERIFY_TRIPLE_STATE" for aid in activity_ids):
        strengths.append({"tag": "closure_verification_habit", "label": "闭环验证习惯", "evidence_event_ids": []})

    # Preferred strategy
    model = model_for_scenario(scenario_id)
    preferred_strategy_id = None
    if model:
        alignments = align_trace(model, trace)
        best = select_best_expert_strategy(alignments)
        if best:
            preferred_strategy_id = best["strategy_id"]

    return {
        "session_id": session_id,
        "scenario_id": scenario_id,
        "total_actions": len(activities),
        "weaknesses": weaknesses,
        "strengths": strengths,
        "preferred_strategy_id": preferred_strategy_id,
        "classification_counts": dict(class_counts),
    }


def build_cumulative_strategy_profile(session_id):
    """
    Build a cumulative strategy profile across all scenarios in a session.

    Persistence tracking:
    - observed: seen once
    - recurring: seen across 2+ steps in same scenario
    - persistent: seen across 2+ different scenarios
    """
    traces = list_student_traces(session_id)
    if not traces:
        return {
            "session_id": session_id,
            "weaknesses": [],
            "strengths": [],
            "preferred_strategy_id": None,
            "trace_count": 0,
        }

    all_weaknesses = []
    all_strengths = []
    strategy_ids = []
    scenario_ids = set()

    for trace_info in traces:
        sid = trace_info.get("scenario_id", "")
        if not sid:
            continue
        scenario_ids.add(sid)
        profile = build_strategy_profile(session_id, sid)
        all_weaknesses.extend(profile.get("weaknesses", []))
        all_strengths.extend(profile.get("strengths", []))
        if profile.get("preferred_strategy_id"):
            strategy_ids.append(profile["preferred_strategy_id"])

    # Merge weaknesses with persistence tracking
    merged_weaknesses = {}
    for w in all_weaknesses:
        tag = w["tag"]
        if tag not in merged_weaknesses:
            merged_weaknesses[tag] = dict(w)
            merged_weaknesses[tag]["scenario_count"] = 1
        else:
            merged_weaknesses[tag]["count"] += w["count"]
            merged_weaknesses[tag]["scenario_count"] += 1

    # Determine persistence level
    for tag, w in merged_weaknesses.items():
        if w["scenario_count"] >= 2:
            w["persistence"] = "persistent"
        elif w["count"] >= 2:
            w["persistence"] = "recurring"
        else:
            w["persistence"] = "observed"

    weaknesses_list = sorted(merged_weaknesses.values(),
                              key=lambda w: (
                                  {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(w["severity"], 99),
                                  -w["count"]
                              ))

    # Deduplicate strengths
    seen_tags = set()
    strengths_list = []
    for s in all_strengths:
        if s["tag"] not in seen_tags:
            seen_tags.add(s["tag"])
            strengths_list.append(s)

    # Most common strategy
    preferred = Counter(strategy_ids).most_common(1)
    preferred_id = preferred[0][0] if preferred else None

    return {
        "session_id": session_id,
        "weaknesses": weaknesses_list,
        "strengths": strengths_list,
        "preferred_strategy_id": preferred_id,
        "trace_count": len(traces),
        "scenario_count": len(scenario_ids),
    }
