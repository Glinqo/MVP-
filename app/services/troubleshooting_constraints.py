"""
Constraint checking for troubleshooting scenarios.

All constraint functions are deterministic (no LLM). They check:
- Safety constraints: has safety been confirmed before power-on actions?
- Action preconditions: does the current state satisfy action requirements?
- Hypothesis support: does evidence support the hypothesis being tested?
- Completion: have all required checks been performed?
"""

from .data_loader import load_data


# --- Safety constraints ---

SAFETY_GATE_ACTIONS = {
    "CHECK_SAFETY",
    "REWIRE_WITHOUT_SAFETY",
    "SHORT_OUTPUT_ILLEGAL",
    "MANUAL_VALVE_UNSAFE",
}

UNSAFE_ACTIONS = {
    "REWIRE_WITHOUT_SAFETY",
    "SHORT_OUTPUT_ILLEGAL",
    "MANUAL_VALVE_UNSAFE",
}

ACTIONS_REQUIRING_SAFETY = {
    "CHECK_SENSOR_TYPE", "CHECK_COMMON_TERMINAL", "CHECK_WIRING",
    "VERIFY_TRIPLE_STATE",
    "CHECK_DC24V", "CHECK_DISTANCE_AND_TARGET",
    "CHECK_ADDRESS_MAPPING", "CHECK_VARIABLE_BINDING",
    "LAYERED_CHECK_ELECTRICAL", "LAYERED_CHECK_PROGRAM", "LAYERED_CHECK_AIR",
}


def check_safety_constraints(state_flags, action_id, is_unsafe_action=False):
    """
    Check if safety constraints are satisfied.

    Returns:
        dict with: safe (bool), blocked (bool), message, level
    """
    if is_unsafe_action:
        return {
            "safe": False,
            "blocked": True,
            "block_reason": "safety_violation",
            "message": "安全警告：此动作违反安全规程。请先断电并确认急停、气源、电源状态。",
            "level": "critical",
        }

    if action_id in ACTIONS_REQUIRING_SAFETY:
        if not state_flags.get("safety_confirmed", False):
            if not state_flags.get("power_off_safety", False):
                return {
                    "safe": False,
                    "blocked": False,
                    "block_reason": None,
                    "message": "建议先确认安全状态（断电、急停、气源）再继续。",
                    "level": "warning",
                }

    return {"safe": True, "blocked": False, "block_reason": None, "message": None, "level": "ok"}


# --- Precondition checking ---

def check_action_preconditions(model, action_id, state_flags):
    """
    Check if the action's required state preconditions are met.

    Returns list of missing precondition strings.
    """
    action = None
    for a in model.get("diagnostic_actions", []):
        if a["id"] == action_id:
            action = a
            break

    if not action:
        return []

    required_state = action.get("required_state", {})
    missing = []
    for key, expected in required_state.items():
        current = state_flags.get(key)
        if isinstance(expected, bool):
            if bool(current) is not expected:
                missing.append(f"需要先完成: {key}")
        elif current != expected:
            missing.append(f"需要 {key}={expected}，当前为 {current}")

    return missing


# --- Hypothesis support checking ---

def check_hypothesis_support(model, action_id, state_flags, state_id):
    """
    Check whether current evidence supports the hypothesis the action is testing.

    Returns dict with supported, evidence_for, evidence_against.
    """
    action = None
    for a in model.get("diagnostic_actions", []):
        if a["id"] == action_id:
            action = a
            break

    if not action:
        return {"supported": True, "evidence_for": [], "evidence_against": []}

    required_hypothesis = action.get("requires_hypothesis")
    if not required_hypothesis:
        return {"supported": True, "evidence_for": [], "evidence_against": []}

    # Check if this hypothesis is still active (not eliminated)
    state = None
    for s in model.get("states", []):
        if s["id"] == state_id:
            state = s
            break

    if state and required_hypothesis not in state.get("remaining_hypotheses", []):
        return {
            "supported": False,
            "evidence_for": [],
            "evidence_against": [f"假设 {required_hypothesis} 已被排除"],
        }

    # Find the hypothesis definition
    for hyp in model.get("hypotheses", []):
        if hyp["id"] == required_hypothesis:
            # Check supporting evidence against known facts
            supporting = hyp.get("supporting_evidence", [])
            refuting = hyp.get("refuting_evidence", [])
            known_facts = state.get("known_facts", []) if state else []

            evidence_for = [e for e in supporting if any(f in e for f in known_facts)]
            evidence_against = [e for e in refuting if any(f in e for f in known_facts)]

            return {
                "supported": len(evidence_for) > 0 or len(evidence_against) == 0,
                "evidence_for": evidence_for,
                "evidence_against": evidence_against,
            }

    return {"supported": True, "evidence_for": [], "evidence_against": []}


# --- Completion checking ---

def check_completion_constraints(model, state_flags, state_id):
    """
    Check if the scenario completion requirements are met.

    Returns:
        dict with is_complete, missing_state_items, missing_closure
    """
    requirements = model.get("completion_requirements", {})
    terminal_states = model.get("terminal_states", [])

    if state_id in terminal_states:
        return {"is_complete": True, "missing_state_items": [], "missing_closure": None}

    required_state = requirements.get("required_state", {})
    missing = []
    for key, expected in required_state.items():
        current = state_flags.get(key)
        if isinstance(expected, bool):
            if bool(current) is not expected:
                missing.append(key)
        elif current != expected:
            missing.append(f"{key}={expected}")

    closure_action = requirements.get("closure_action")
    missing_closure = closure_action if closure_action else None

    return {
        "is_complete": len(missing) == 0 and not missing_closure,
        "missing_state_items": missing,
        "missing_closure": missing_closure,
    }


# --- Deviation counting ---

def count_consecutive_deviations(student_trace, deviation_type=None):
    """
    Count consecutive deviations of a specific type (or all types if None).

    Uses the classification field to identify deviations.
    Maps: premature->jump_to_program, unsafe->safety_bypass,
          unsupported_hypothesis->replace_first, closure_missing->closure_missing,
          repeated_low_value->repeated

    Returns:
        int: consecutive count from the end of the trace
    """
    _classification_to_type = {
        "premature": "jump_to_program",
        "unsafe": "safety_bypass",
        "unsupported_hypothesis": "replace_first",
        "closure_missing": "closure_missing",
        "repeated_low_value": "repeated",
        "valid_but_inefficient": "inefficient",
    }

    count = 0
    for entry in reversed(student_trace):
        classification = entry.get("classification", "optimal")
        entry_deviation = _classification_to_type.get(classification)

        if deviation_type:
            if entry_deviation == deviation_type:
                count += 1
            else:
                break
        else:
            if classification not in ("optimal", "valid"):
                count += 1
            else:
                break
    return count


def get_deviation_trend(student_trace, window=5):
    """
    Analyze recent deviation trend from the student trace.

    Returns:
        dict with: trend ("improving", "worsening", "stable", "none"),
        recent_classifications, dominant_deviation
    """
    recent = student_trace[-window:] if len(student_trace) > window else student_trace
    if not recent:
        return {"trend": "none", "recent_classifications": [], "dominant_deviation": None}

    classifications = [e.get("classification", "optimal") for e in recent]
    deviations = [e.get("deviation") for e in recent if e.get("deviation")]

    # Count how many are non-optimal
    non_optimal = sum(1 for c in classifications if c not in ("optimal", "valid"))

    if non_optimal == 0:
        trend = "none"
    elif len(recent) >= 2 and non_optimal > sum(1 for c in classifications[-2:] if c in ("optimal", "valid")):
        trend = "worsening"
    elif len(recent) >= 2 and classifications[-1] in ("optimal", "valid"):
        trend = "improving"
    else:
        trend = "stable"

    # Dominant deviation
    dominant = None
    if deviations:
        from collections import Counter
        dominant = Counter(deviations).most_common(1)[0][0]

    return {
        "trend": trend,
        "recent_classifications": classifications,
        "dominant_deviation": dominant,
        "non_optimal_count": non_optimal,
        "window_size": len(recent),
    }
