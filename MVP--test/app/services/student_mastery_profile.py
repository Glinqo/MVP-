"""Four-dimensional student mastery profile for the personal ability graph.

This service is intentionally deterministic.  It does not let an LLM grade the
student; it fuses existing graph evidence with diagnostic traces, process
metrics, strategy tags, and cross-scenario coverage.
"""

from collections import defaultdict

from .data_loader import load_data
from .diagnostic_trace import list_student_traces
from .process_metrics import (
    compute_closure_verification,
    compute_diagnostic_efficiency,
    compute_evidence_quality,
    compute_fault_localization,
    compute_safety_compliance,
)
from .strategy_profile import build_cumulative_strategy_profile
from .coverage_matrix import build_coverage_matrix


NEGATIVE_CLASSIFICATIONS = {
    "unsafe",
    "premature",
    "unsupported_hypothesis",
    "closure_missing",
    "repeated_low_value",
    "valid_but_inefficient",
}
POSITIVE_CLASSIFICATIONS = {"optimal", "valid", "correct", "completed", "passed"}
SAFETY_ABILITY_IDS = {
    "electrical_safety_check",
    "power_isolation_confirmation",
    "dc24v_power_check",
    "multimeter_voltage_measurement",
}


def scalar100(value, default=0):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return int(default)
    if num <= 1.0:
        num *= 100
    return int(max(0, min(100, round(num))))


def average(values, default=0):
    values = [float(value) for value in values if value is not None]
    if not values:
        return default
    return sum(values) / len(values)


def trace_metrics(activities):
    return {
        "safety_compliance": round(compute_safety_compliance(activities), 2),
        "evidence_quality": round(compute_evidence_quality(activities), 2),
        "fault_localization": round(compute_fault_localization(activities), 2),
        "diagnostic_efficiency": round(compute_diagnostic_efficiency(activities), 2),
        "closure_verification": round(compute_closure_verification(activities), 2),
    }


def aggregate_metrics(metric_rows):
    keys = [
        "safety_compliance",
        "evidence_quality",
        "fault_localization",
        "diagnostic_efficiency",
        "closure_verification",
    ]
    return {key: round(average([row.get(key) for row in metric_rows]), 2) for key in keys}


def normalize_learning_event(event):
    """Create a compact event view suitable for mastery calculations."""
    event_type = event.get("event_type", "learning_event")
    outcome = event.get("outcome") or event.get("action_category") or ""
    ability_ids = list(dict.fromkeys(event.get("ability_ids") or []))
    category = "knowledge"
    polarity = "neutral"
    weight = 0.3

    if event_type in {"score", "diagnosis"}:
        category = "knowledge"
        polarity = "negative" if event.get("weak_abilities") else "positive"
        weight = 1.0
    elif event_type in {"question_explained", "knowledge_explained"}:
        category = "knowledge"
        polarity = "positive"
        weight = 0.4
    elif event_type in {"scenario_step_completed", "diagnostic_action", "scenario_step_mistake"}:
        category = "procedure"
        if outcome in POSITIVE_CLASSIFICATIONS:
            polarity = "positive"
        elif outcome in NEGATIVE_CLASSIFICATIONS or event_type == "scenario_step_mistake":
            polarity = "negative"
        weight = 1.0
    elif event_type == "feedback":
        category = "reflection"
        feedback = event.get("feedback")
        polarity = "positive" if feedback == "已掌握" else ("negative" if feedback else "neutral")
        weight = 0.5 if polarity == "positive" else 0.7

    if outcome == "unsafe" or event.get("action_category") == "unsafe":
        category = "safety"
        polarity = "negative"
        weight = 1.5

    return {
        "event_id": event.get("event_id"),
        "created_at": event.get("created_at"),
        "event_type": event_type,
        "ability_ids": ability_ids,
        "event_category": category,
        "polarity": polarity,
        "evidence_weight": weight,
        "scenario_id": event.get("scenario_id"),
        "action_id": event.get("action_id"),
        "outcome": outcome,
        "evidence_summary": event.get("note") or event.get("action_category_label") or "",
        "source": event.get("source", "session_event"),
    }


def collect_trace_evidence(traces):
    by_ability = defaultdict(lambda: {
        "total": 0,
        "positive": 0,
        "negative": 0,
        "unsafe": 0,
        "scenarios": set(),
        "fault_contexts": set(),
        "activities": [],
        "events": [],
        "metric_rows": [],
        "strategy_tags": [],
    })
    metric_rows = []

    for trace in traces:
        activities = trace.get("activities", [])
        metrics = trace_metrics(activities)
        metric_rows.append(metrics)
        scenario_id = trace.get("scenario_id", "")

        for event in trace.get("events", []):
            normalized = normalize_learning_event(event)
            for ability_id in normalized["ability_ids"]:
                bucket = by_ability[ability_id]
                bucket["events"].append(normalized)

        for activity in activities:
            classification = activity.get("classification") or ""
            ability_ids = activity.get("ability_ids") or []
            is_positive = classification in POSITIVE_CLASSIFICATIONS
            is_negative = classification in NEGATIVE_CLASSIFICATIONS
            is_unsafe = classification == "unsafe" or int(activity.get("risk_level", 0) or 0) >= 3
            for ability_id in ability_ids:
                bucket = by_ability[ability_id]
                bucket["total"] += 1
                bucket["positive"] += 1 if is_positive else 0
                bucket["negative"] += 1 if is_negative else 0
                bucket["unsafe"] += 1 if is_unsafe else 0
                if scenario_id:
                    bucket["scenarios"].add(scenario_id)
                    bucket["fault_contexts"].add(activity.get("scenario_id") or scenario_id)
                bucket["activities"].append(activity)
                bucket["metric_rows"].append(metrics)

    return by_ability, metric_rows


def strategy_tags_for_ability(ability_id, profile):
    tags = []
    for item in profile.get("weaknesses", []):
        related = item.get("related_abilities") or item.get("ability_ids") or []
        if not related or ability_id in related or ability_id in SAFETY_ABILITY_IDS and item.get("tag") == "safety_procedure_gap":
            tags.append({
                "tag": item.get("tag"),
                "label": item.get("label"),
                "severity": item.get("severity"),
                "persistence": item.get("persistence", "observed"),
                "count": item.get("count", 1),
            })
    return tags[:5]


def procedure_mastery(base_score, evidence, metrics):
    if evidence.get("total"):
        accuracy = evidence["positive"] / max(evidence["total"], 1)
        process = average([
            metrics.get("fault_localization", 0),
            metrics.get("diagnostic_efficiency", 0),
            metrics.get("closure_verification", 0),
        ])
        return scalar100((accuracy * 0.55 + process * 0.45) * 100)
    return scalar100(base_score * 0.45)


def transfer_score(evidence, coverage):
    scenarios = evidence.get("scenarios", set())
    contexts = evidence.get("fault_contexts", set())
    total = evidence.get("total", 0)
    if not total:
        return 0
    accuracy = evidence.get("positive", 0) / max(total, 1)
    score = accuracy * 100
    if coverage.get("cross_scenario_validated") or (len(scenarios) >= 2 and len(contexts) >= 2):
        score = min(100, score * 0.8 + 20)
    elif len(scenarios) >= 1:
        score = min(30, score)
    else:
        score = 0
    return scalar100(score)


def safety_score(ability_id, evidence, metrics, tags):
    if not evidence.get("total"):
        # Unknown is safer than claiming mastery: use a conservative baseline.
        base = 70 if ability_id in SAFETY_ABILITY_IDS else 85
    else:
        unsafe_ratio = evidence.get("unsafe", 0) / max(evidence.get("total", 1), 1)
        base = metrics.get("safety_compliance", 0.7) * 100 - unsafe_ratio * 45
    for tag in tags:
        if tag.get("tag") == "safety_procedure_gap":
            base -= {"critical": 35, "high": 25, "medium": 15, "low": 8}.get(tag.get("severity"), 15)
    return scalar100(base)


def fused_mastery(knowledge, procedure, transfer, safety):
    return scalar100(knowledge * 0.35 + procedure * 0.30 + transfer * 0.20 + safety * 0.15)


def uncertainty(confidence, evidence_count, trace_total):
    try:
        conf = float(confidence or 0)
    except (TypeError, ValueError):
        conf = 0
    evidence_factor = min(0.25, (evidence_count or 0) * 0.04 + trace_total * 0.03)
    return round(max(0.0, min(1.0, 1.0 - conf - evidence_factor)), 2)


def intervention_for(ability_name, dimensions, status, evidence):
    lowest_key = min(dimensions, key=dimensions.get)
    labels = {
        "knowledge_mastery": "知识理解",
        "procedure_mastery": "排故过程",
        "transfer_score": "迁移应用",
        "safety_score": "安全合规",
    }
    if dimensions["safety_score"] < 60:
        return {
            "type": "safety_gate",
            "title": f"先复核“{ability_name}”的安全步骤",
            "reason": "安全合规分低，暂不建议进入综合排故。",
        }
    if lowest_key == "knowledge_mastery":
        return {
            "type": "explain_then_recall",
            "title": f"看讲解后用 1 分钟复述“{ability_name}”",
            "reason": "知识理解是当前最低维度。",
        }
    if lowest_key == "procedure_mastery":
        return {
            "type": "scenario_practice",
            "title": f"做一次包含“{ability_name}”的排故角色扮演",
            "reason": "过程掌握证据不足或错误动作较多。",
        }
    if lowest_key == "transfer_score":
        return {
            "type": "cross_scenario",
            "title": f"换一个故障场景迁移练习“{ability_name}”",
            "reason": "尚未跨场景验证该能力。",
        }
    if status == "weak" or evidence.get("negative"):
        return {
            "type": "targeted_training",
            "title": f"完成“{ability_name}”关联训练任务",
            "reason": "最近存在薄弱或错误证据。",
        }
    return {
        "type": "evidence_building",
        "title": f"补充一次“{ability_name}”的可检查证据",
        "reason": "当前证据还不足以稳定判断掌握水平。",
    }


def coverage_by_ability(traces):
    try:
        matrix = build_coverage_matrix(traces)
    except Exception:
        return {}
    return {item.get("ability_id"): item for item in matrix.get("abilities", [])}


def build_student_mastery_profile(session_id, base_nodes):
    traces = list_student_traces(session_id)
    trace_evidence, global_metric_rows = collect_trace_evidence(traces)
    global_metrics = aggregate_metrics(global_metric_rows)
    profile = build_cumulative_strategy_profile(session_id)
    coverage = coverage_by_ability(traces)

    abilities = {}
    for node in base_nodes:
        ability_id = node.get("id")
        if not ability_id:
            continue
        evidence = trace_evidence.get(ability_id, {})
        metrics = aggregate_metrics(evidence.get("metric_rows", [])) if evidence else dict(global_metrics)
        knowledge = scalar100(node.get("mastery_score", 0))
        tags = strategy_tags_for_ability(ability_id, profile)
        procedure = procedure_mastery(knowledge, evidence, metrics)
        transfer = transfer_score(evidence, coverage.get(ability_id, {}))
        safety = safety_score(ability_id, evidence, metrics, tags)
        dimensions = {
            "knowledge_mastery": knowledge,
            "procedure_mastery": procedure,
            "transfer_score": transfer,
            "safety_score": safety,
        }
        cognitive_score = fused_mastery(knowledge, procedure, transfer, safety)
        gate_passed = safety >= 60 and not any(tag.get("tag") == "safety_procedure_gap" for tag in tags)
        intervention = intervention_for(node.get("label", ability_id), dimensions, node.get("status"), evidence)
        abilities[ability_id] = {
            **dimensions,
            "cognitive_mastery_score": cognitive_score,
            "uncertainty": uncertainty(node.get("confidence"), node.get("evidence_count", 0), evidence.get("total", 0) if evidence else 0),
            "process_metrics": metrics,
            "strategy_tags": tags,
            "cross_scenario_validated": bool(coverage.get(ability_id, {}).get("cross_scenario_validated")),
            "safety_gate": {
                "passed": gate_passed,
                "reason": "安全合规证据通过" if gate_passed else "安全能力需更多合规证据或教师复核",
            },
            "recommended_intervention": intervention,
            "why_next": intervention["reason"],
            "process_evidence": [
                {
                    "action_id": activity.get("action_id"),
                    "classification": activity.get("classification"),
                    "timestamp": activity.get("timestamp"),
                    "source": activity.get("source"),
                }
                for activity in (evidence.get("activities", []) if evidence else [])[-5:]
            ],
            "normalized_events": (evidence.get("events", []) if evidence else [])[-5:],
        }

    return {
        "session_id": session_id,
        "trace_count": len(traces),
        "aggregated_process_metrics": global_metrics,
        "strategy_profile": profile,
        "abilities": abilities,
        "source": "student_graph + diagnostic_trace + process_metrics + strategy_profile",
    }


def augment_student_nodes(session_id, nodes):
    profile = build_student_mastery_profile(session_id, nodes)
    for node in nodes:
        ability_profile = profile["abilities"].get(node.get("id"), {})
        node.update(ability_profile)
        if ability_profile.get("recommended_intervention"):
            node["next_best_action"] = ability_profile["recommended_intervention"]["title"]
    return profile
