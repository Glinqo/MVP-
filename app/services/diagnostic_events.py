"""
Diagnostic events engine for troubleshooting scenarios.

Upgrades scenario steps from simple "correct/incorrect" to structured diagnostic
events: fault states, hypotheses, action categories, and strategy biases.

Design references:
- CTAT behavior graph: correct path / error path
- PM4Py event log: trace / activity / conformance concepts
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .data_loader import ROOT, load_data


MODELS_PATH = ROOT / "knowledge" / "troubleshooting_models.json"

ACTION_CATEGORIES = {
    "optimal": "最佳动作——符合标准排故顺序",
    "valid": "有效动作——合理但非首选",
    "premature": "过早动作——前置条件未满足",
    "unsupported_hypothesis": "无证据动作——当前证据不支持该假设",
    "unsafe": "不安全动作——违反安全规程",
    "closure_missing": "闭环缺失——修复后未验证",
}

ACTION_CATEGORY_PRIORITY = {
    "unsafe": 5,
    "premature": 4,
    "unsupported_hypothesis": 3,
    "closure_missing": 2,
    "valid": 1,
    "optimal": 0,
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_models():
    """Load troubleshooting models, returning a dict keyed by scenario_id."""
    if not MODELS_PATH.exists():
        return {}
    data = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
    return {m["scenario_id"]: m for m in data.get("models", [])}


def model_for_scenario(scenario_id):
    """Get the troubleshooting model for a scenario, or None."""
    return load_models().get(scenario_id)


def action_by_id(model, action_id):
    """Find an action definition within a model."""
    for action in model.get("diagnostic_actions", []):
        if action["id"] == action_id:
            return action
    return None


def hypothesis_by_id(model, hypothesis_id):
    """Find a hypothesis definition within a model."""
    for hyp in model.get("hypotheses", []):
        if hyp["id"] == hypothesis_id:
            return hyp
    return None


def classify_action(model, action_id, current_state, action_history):
    """
    Classify a student's diagnostic action.

    Returns:
        dict with category, category_label, strategy_bias, related_abilities,
        evidence_gained, is_valid, blocked_by, and explanation.
    """
    action = action_by_id(model, action_id)
    if not action:
        return {
            "category": "unknown",
            "category_label": "未知动作",
            "strategy_bias": None,
            "related_abilities": [],
            "evidence_gained": None,
            "is_valid": False,
            "blocked_by": [],
            "explanation": f"动作 {action_id} 不在场景模型中",
        }

    category = action.get("category", "valid")
    required_state = action.get("required_state", {})
    strategy_bias = action.get("strategy_bias")
    related_abilities = action.get("related_abilities", [])
    evidence_gained = action.get("evidence_gained")
    blocked_by = []

    # Check required state
    for key, expected in required_state.items():
        current_val = current_state.get(key)
        if isinstance(expected, bool):
            if bool(current_val) is not expected:
                blocked_by.append(f"需要先完成: {key}")
        elif current_val != expected:
            blocked_by.append(f"需要 {key}={expected}，当前为 {current_val}")

    # Check required hypothesis
    required_hypothesis = action.get("requires_hypothesis")
    if required_hypothesis:
        # For unsafe actions that require a specific hypothesis, check if that hypothesis
        # is contradicted by current evidence
        pass

    is_valid = len(blocked_by) == 0
    if category == "unsafe":
        is_valid = False  # Unsafe actions are never valid

    # Build explanation
    explanation = ACTION_CATEGORIES.get(category, "未分类动作")
    if blocked_by:
        explanation += "；前置条件未满足：" + "、".join(blocked_by)

    return {
        "category": category,
        "category_label": ACTION_CATEGORIES.get(category, category),
        "strategy_bias": strategy_bias,
        "related_abilities": related_abilities,
        "evidence_gained": evidence_gained,
        "is_valid": is_valid,
        "blocked_by": blocked_by,
        "explanation": explanation,
    }


def check_completion(model, current_state, action_history):
    """
    Check if the troubleshooting session meets completion requirements.

    Returns:
        dict with is_complete, completed_items, missing_items, and closure_status.
    """
    requirements = model.get("completion_requirements", {})
    if not requirements:
        return {"is_complete": True, "completed_items": [], "missing_items": [], "closure_status": "no_requirements"}

    required_state = requirements.get("required_state", {})
    required_actions = requirements.get("required_actions", [])
    closure_action = requirements.get("closure_action")

    missing_items = []
    for key, expected in required_state.items():
        current_val = current_state.get(key)
        if isinstance(expected, bool):
            if bool(current_val) is not expected:
                missing_items.append(f"状态未满足: {key}")
        elif current_val != expected:
            missing_items.append(f"状态未满足: {key}={expected}，当前为 {current_val}")

    for action_id in required_actions:
        if action_id not in action_history:
            missing_items.append(f"未执行必要动作: {action_id}")

    closure_done = True
    if closure_action and closure_action not in action_history:
        missing_items.append(f"未执行闭环验证: {closure_action}")
        closure_done = False

    is_complete = len(missing_items) == 0

    return {
        "is_complete": is_complete,
        "completed_items": [
            f"状态已满足: {k}" for k in required_state
            if current_state.get(k)
        ] + [
            f"已执行: {a}" for a in required_actions if a in action_history
        ],
        "missing_items": missing_items,
        "closure_status": "verified" if closure_done else ("not_required" if not closure_action else "missing"),
    }


def evaluate_remaining_hypotheses(model, current_state, action_history):
    """
    Evaluate which hypotheses remain viable given current state and action history.

    Returns:
        list of hypothesis dicts with active/eliminated status and reasoning.
    """
    hypotheses = model.get("hypotheses", [])
    result = []
    for hyp in hypotheses:
        # Simple rule: if required state is checked and matches supporting evidence, active
        result.append({
            "id": hyp["id"],
            "label": hyp["label"],
            "description": hyp["description"],
            "related_abilities": hyp.get("related_abilities", []),
            "status": "active",  # All active at start; elimination logic TBD in later phase
        })
    return result


def compute_strategy_bias(action_classifications):
    """
    From a list of action classifications, compute overall strategy biases.

    Returns:
        list of bias dicts with id, label, description, and count.
    """
    bias_counts = {}
    for cls in action_classifications:
        bias = cls.get("strategy_bias")
        if bias:
            bias_counts[bias] = bias_counts.get(bias, 0) + 1

    all_models = load_models()
    # Build a lookup of bias_id -> definition from all models
    bias_defs = {}
    for m in all_models.values():
        for bias_id, bias_def in m.get("strategy_biases", {}).items():
            if bias_id not in bias_defs:
                bias_defs[bias_id] = bias_def

    biases = []
    seen = set()
    for bias_id, count in bias_counts.items():
        if bias_id in bias_defs and bias_id not in seen:
            bias_def = bias_defs[bias_id]
            biases.append({
                "id": bias_id,
                "label": bias_def["label"],
                "description": bias_def["description"],
                "count": count,
                "related_abilities": bias_def.get("related_abilities", []),
            })
            seen.add(bias_id)

    biases.sort(key=lambda b: -b["count"])
    return biases


def build_diagnostic_event(session_id, scenario_id, action_id, action_result, scenario_title,
                           ability_ids, strategy_bias, current_state):
    """
    Build a diagnostic event record for storage in the session.

    Returns:
        dict suitable for append_session_event.
    """
    return {
        "session_id": session_id,
        "event_type": "diagnostic_action",
        "scenario_id": scenario_id,
        "scenario_title": scenario_title,
        "action_id": action_id,
        "action_category": action_result["category"],
        "action_category_label": action_result["category_label"],
        "is_valid": action_result["is_valid"],
        "blocked_by": action_result["blocked_by"],
        "strategy_bias": strategy_bias,
        "evidence_gained": action_result["evidence_gained"],
        "ability_ids": ability_ids,
        "current_state_snapshot": dict(current_state),
        "created_at": now_iso(),
        "note": f"{scenario_title} / 动作 {action_id} / {action_result['category_label']}",
        "source": "student_diagnostic_action",
    }
