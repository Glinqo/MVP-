"""
Counterfactual action selection engine.

Ranks candidate diagnostic actions by utility:
    utility = IG_weight * info_gain
            - risk_weight * risk
            - cost_weight * action_cost
            - repeat_weight * repetition_penalty
            + ability_weight * ability_validation

Selects the next best action and explains why other actions were rejected.
All weights from diagnostic_action_policy.json.
"""

import json
from pathlib import Path

from .data_loader import ROOT
from .hypothesis_engine import (
    initialize_hypotheses,
    active_hypothesis_ids,
    get_hypotheses_summary,
)
from .information_gain import normalized_information_gain


POLICY_PATH = ROOT / "knowledge" / "diagnostic_action_policy.json"


def load_policy():
    if not POLICY_PATH.exists():
        return {}
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


# --- Candidate ranking ---

def rank_candidate_actions(model, hypotheses, state_flags, action_history,
                            student_weak_abilities=None):
    """
    Rank all candidate diagnostic actions by utility.

    Args:
        model: troubleshooting model dict
        hypotheses: dict from hypothesis_engine
        state_flags: current state flags {flag: value}
        action_history: list of action_ids already performed
        student_weak_abilities: set of ability_ids the student is weak in

    Returns:
        list of (action, utility_dict) sorted by utility descending
    """
    policy = load_policy()
    weights = policy.get("weights", {})
    risk_costs = policy.get("risk_costs", {})
    action_costs = policy.get("action_base_costs", {})
    evidence_map = policy.get("action_hypothesis_evidence", {}).get(
        model.get("scenario_id", ""), {}
    )
    rules = policy.get("rules", {})

    w_ig = weights.get("information_gain", 0.40)
    w_risk = weights.get("risk_penalty", 0.25)
    w_cost = weights.get("action_cost", 0.15)
    w_repeat = weights.get("repetition_penalty", 0.10)
    w_ability = weights.get("ability_validation", 0.10)
    unsafe_blocked = rules.get("unsafe_action_blocked", True)
    ability_max_boost = rules.get("ability_validation_max_boost", 0.15)

    student_weak = student_weak_abilities or set()
    results = []

    for action in model.get("diagnostic_actions", []):
        action_id = action["id"]
        category = action.get("category", "valid")

        # Unsafe actions: always blocked
        if unsafe_blocked and category == "unsafe":
            results.append((action, {
                "action_id": action_id,
                "title": action.get("label", action_id),
                "utility": -1.0,
                "information_gain": 0.0,
                "risk_penalty": 1.0,
                "action_cost_penalty": action_costs.get(action_id, 0.05),
                "repetition_penalty": 0.0,
                "ability_validation_value": 0.0,
                "blocked": True,
                "block_reason": "安全违规，该动作不可用",
                "hypothesis_reduction": [],
            }))
            continue

        # Check preconditions
        required_state = action.get("required_state", {})
        preconditions_met = all(
            state_flags.get(k) == v if not isinstance(v, bool) else bool(state_flags.get(k)) == v
            for k, v in required_state.items()
        )
        if not preconditions_met:
            # Action requires unmet preconditions -> lower utility
            pass  # Still rankable, just less utility

        # 1. Information gain
        info_gain, hypothesis_reduction = normalized_information_gain(
            hypotheses, action_id, evidence_map
        )

        # 2. Risk penalty
        risk = risk_costs.get(category, 0.10)

        # 3. Action cost
        action_cost = action_costs.get(action_id, 0.10)

        # 4. Repetition penalty
        repeat_count = action_history.count(action_id)
        repetition = min(0.5, repeat_count * 0.25)

        # 5. Ability validation
        ability_ids = set(action.get("related_abilities", []))
        overlap = ability_ids & student_weak
        ability_val = min(ability_max_boost, len(overlap) * 0.05)

        # Compute utility
        utility = (
            w_ig * info_gain
            - w_risk * risk
            - w_cost * action_cost
            - w_repeat * repetition
            + w_ability * ability_val
        )

        # Preconditions not met: further reduce utility
        if not preconditions_met:
            utility -= 0.15

        results.append((action, {
            "action_id": action_id,
            "title": action.get("label", action_id),
            "utility": round(utility, 4),
            "information_gain": round(info_gain, 4),
            "risk_penalty": round(risk, 4),
            "action_cost_penalty": round(action_cost, 4),
            "repetition_penalty": round(repetition, 4),
            "ability_validation_value": round(ability_val, 4),
            "blocked": False,
            "block_reason": None,
            "preconditions_met": preconditions_met,
            "hypothesis_reduction": hypothesis_reduction,
        }))

    # Sort by utility descending
    results.sort(key=lambda x: (-x[1]["utility"], x[0]["id"]))
    return results


# --- Next best action ---

def select_next_best_action(model, hypotheses, state_flags, action_history,
                             student_weak_abilities=None):
    """
    Select the single best next action.

    Returns the top-ranked action detail dict.
    """
    ranked = rank_candidate_actions(
        model, hypotheses, state_flags, action_history, student_weak_abilities
    )
    if not ranked:
        return None
    return ranked[0][1]


# --- Explanations ---

def explain_action_choice(best_action, model):
    """Generate a human-readable reason for choosing this action."""
    ig = best_action.get("information_gain", 0)
    reduction = best_action.get("hypothesis_reduction", [])
    risk = best_action.get("risk_penalty", 0)

    if best_action.get("blocked"):
        return best_action.get("block_reason", "该动作不可用")

    parts = []

    if ig > 0.3 and reduction:
        hyp_labels = []
        for hid in reduction:
            for h in model.get("hypotheses", []):
                if h["id"] == hid:
                    hyp_labels.append(h.get("label", hid))
                    break
        parts.append(f"该动作可以排除假设：{'、'.join(hyp_labels[:3])}")

    if ig <= 0.05:
        parts.append("该动作在当前状态下信息增益较低")

    if risk > 0.3:
        parts.append("注意该动作存在一定风险")

    if best_action.get("repetition_penalty", 0) > 0:
        parts.append("该动作之前已经执行过")

    if best_action.get("ability_validation_value", 0) > 0:
        parts.append("执行该动作同时可以验证你的相关能力")

    if not parts:
        parts.append("该动作是当前最优选择")

    return "。".join(parts) + "。"


def explain_rejected_actions(ranked_actions, best_action, model, max_items=3):
    """
    Explain why the top N rejected actions were not chosen.

    Args:
        ranked_actions: full list of (action, utility_dict)
        best_action: the chosen action
        model: model dict
        max_items: maximum number of rejected actions to explain

    Returns:
        list of {action_id, reason}
    """
    policy = load_policy()
    rules = policy.get("rules", {})
    max_items = rules.get("maximum_why_not_items", max_items)

    why_not = []
    best_id = best_action.get("action_id", "")

    for action, detail in ranked_actions:
        if detail["action_id"] == best_id:
            continue
        if len(why_not) >= max_items:
            break
        if detail.get("blocked"):
            why_not.append({
                "action_id": detail["action_id"],
                "title": detail.get("title", detail["action_id"]),
                "reason": detail.get("block_reason", "该动作不可用"),
            })
            continue

        reasons = []
        if detail["information_gain"] < best_action.get("information_gain", 0) - 0.1:
            reasons.append("信息增益较低")
        if detail["risk_penalty"] > best_action.get("risk_penalty", 0):
            reasons.append("风险更高")
        if detail["action_cost_penalty"] > best_action.get("action_cost_penalty", 0):
            reasons.append("成本更高")
        if detail["repetition_penalty"] > 0:
            reasons.append("已重复执行")
        if not detail.get("preconditions_met", True):
            reasons.append("前置条件未满足")
        if not reasons:
            reasons.append("综合效用略低于最优动作")

        why_not.append({
            "action_id": detail["action_id"],
            "title": detail.get("title", detail["action_id"]),
            "reason": "；".join(reasons) + "。",
        })

    return why_not


# --- Full analysis ---

def analyze_next_action(model, state_flags, action_history,
                         student_weak_abilities=None, existing_hypotheses=None):
    """
    Full analysis: hypothesis update + action ranking + explanation.

    Returns complete dict suitable for API response.
    """
    # Initialize or use existing hypotheses
    if existing_hypotheses is None:
        hypotheses = initialize_hypotheses(model)
    else:
        hypotheses = existing_hypotheses

    # Rank actions
    ranked = rank_candidate_actions(
        model, hypotheses, state_flags, action_history, student_weak_abilities
    )

    if not ranked:
        return {
            "next_best_action": None,
            "candidate_actions": [],
            "remaining_hypotheses": get_hypotheses_summary(hypotheses),
            "hypothesis_update_reason": None,
        }

    best = ranked[0][1]

    return {
        "next_best_action": {
            "action_id": best["action_id"],
            "title": best["title"],
            "utility": best["utility"],
            "information_gain": best["information_gain"],
            "risk_penalty": best["risk_penalty"],
            "action_cost_penalty": best["action_cost_penalty"],
            "ability_validation_value": best["ability_validation_value"],
            "reason": explain_action_choice(best, model),
            "expected_hypothesis_reduction": best.get("hypothesis_reduction", []),
            "why_not": explain_rejected_actions(ranked, best, model),
        },
        "candidate_actions": [
            {
                "action_id": d["action_id"],
                "title": d["title"],
                "utility": d["utility"],
                "information_gain": d["information_gain"],
                "blocked": d.get("blocked", False),
                "hypothesis_reduction": d.get("hypothesis_reduction", []),
            }
            for _, d in ranked[:6]
        ],
        "remaining_hypotheses": get_hypotheses_summary(hypotheses),
        "hypothesis_update_reason": None,
    }
