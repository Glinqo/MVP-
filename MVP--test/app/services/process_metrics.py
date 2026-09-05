"""
Five-dimensional process metrics for diagnostic sessions.

Metrics (all 0.0 - 1.0):
- safety_compliance: did student confirm safety before power-on actions?
- evidence_quality: did student gather sufficient evidence before concluding?
- fault_localization: did student follow a logical signal-chain path?
- diagnostic_efficiency: minimal extra steps? no repeats?
- closure_verification: did student verify the fix?

All metrics are deterministic rule-based calculations. No LLM.
"""

from .diagnostic_trace import build_diagnostic_trace
from .model_tracer import model_for_scenario


# Safety gate actions that must happen before anything involving power
SAFETY_ACTIONS = {"CHECK_SAFETY"}
ACTIONS_REQUIRING_SAFETY = {
    "CHECK_COMMON_TERMINAL", "CHECK_WIRING", "CHECK_SENSOR_TYPE",
    "VERIFY_TRIPLE_STATE", "CHECK_DC24V", "CHECK_DISTANCE_AND_TARGET",
    "CHECK_ADDRESS_MAPPING", "CHECK_VARIABLE_BINDING",
    "LAYERED_CHECK_ELECTRICAL", "LAYERED_CHECK_PROGRAM", "LAYERED_CHECK_AIR",
}
UNSAFE_ACTIONS = {"REWIRE_WITHOUT_SAFETY", "SHORT_OUTPUT_ILLEGAL", "MANUAL_VALVE_UNSAFE"}
CLOSURE_ACTIONS = {"VERIFY_TRIPLE_STATE"}
EVIDENCE_ACTIONS = {
    "CHECK_COMMON_TERMINAL", "CHECK_WIRING", "CHECK_SENSOR_TYPE",
    "CHECK_DC24V", "CHECK_DISTANCE_AND_TARGET",
    "CHECK_ADDRESS_MAPPING", "CHECK_VARIABLE_BINDING",
}
PREMATURE_ACTIONS = {"MODIFY_PROGRAM_PREMATURE", "MODIFY_PROGRAM_PREMATURE_LED_OFF"}
REPLACE_ACTIONS = {"REPLACE_MODULE_NO_EVIDENCE", "REPLACE_SENSOR_PREMATURE"}


def compute_safety_compliance(activities):
    """Check if safety was confirmed before any power-on actions."""
    activity_ids = [a.get("action_id", "") for a in activities]

    # Any unsafe actions?
    unsafe_found = any(aid in UNSAFE_ACTIONS for aid in activity_ids)
    if unsafe_found:
        return 0.0

    # For any action requiring safety, check if safety was done first
    safety_done = any(aid in SAFETY_ACTIONS for aid in activity_ids)

    requires_safety_actions = [a for a in activity_ids if a in ACTIONS_REQUIRING_SAFETY]
    if not requires_safety_actions:
        return 1.0 if not unsafe_found else 0.5

    if not safety_done:
        return 0.2  # Did actions requiring safety without confirming safety

    # Check order: safety must come before first action requiring safety
    safety_indices = [i for i, aid in enumerate(activity_ids) if aid in SAFETY_ACTIONS]
    first_requires_idx = min(i for i, aid in enumerate(activity_ids) if aid in ACTIONS_REQUIRING_SAFETY)

    if safety_indices and safety_indices[0] < first_requires_idx:
        return 1.0

    return 0.5


def compute_evidence_quality(activities):
    """Check evidence gathering quality: enough evidence before conclusions."""
    activity_ids = [a.get("action_id", "") for a in activities]
    classifications = [a.get("classification", "") for a in activities]

    evidence_count = sum(1 for aid in activity_ids if aid in EVIDENCE_ACTIONS)
    premature_count = sum(1 for aid in activity_ids if aid in PREMATURE_ACTIONS)
    replace_count = sum(1 for aid in activity_ids if aid in REPLACE_ACTIONS)

    total = len(activities)
    if total == 0:
        return 1.0

    # No premature/replace actions
    if premature_count + replace_count == 0:
        if evidence_count >= 2:
            return 1.0
        return 0.7

    # Some premature/replace
    penalty = (premature_count + replace_count) / max(1, total)
    return max(0.1, 1.0 - penalty)


def compute_fault_localization(activities):
    """Check if student followed a logical signal-chain approach."""
    activity_ids = [a.get("action_id", "") for a in activities]

    # Optimal sequence: safety -> hardware -> verify
    optimal_order = [
        "CHECK_SAFETY", "CHECK_COMMON_TERMINAL", "CHECK_WIRING",
        "VERIFY_TRIPLE_STATE"
    ]

    # Count how many follow the expected order
    ordered_count = 0
    expected_idx = 0
    for aid in activity_ids:
        if expected_idx < len(optimal_order) and aid == optimal_order[expected_idx]:
            ordered_count += 1
            expected_idx += 1

    total_optimal = len(optimal_order)
    if total_optimal == 0:
        return 1.0

    # Also penalize jump-to-program and replace patterns
    has_jump = any(aid in PREMATURE_ACTIONS for aid in activity_ids)
    has_replace = any(aid in REPLACE_ACTIONS for aid in activity_ids)

    base = ordered_count / total_optimal
    if has_jump:
        base *= 0.7
    if has_replace:
        base *= 0.6

    return max(0.1, base)


def compute_diagnostic_efficiency(activities):
    """Check efficiency: minimal extra steps, no repeats."""
    activity_ids = [a.get("action_id", "") for a in activities]
    classifications = [a.get("classification", "") for a in activities]

    if not activity_ids:
        return 1.0

    # Count repeats
    seen = set()
    repeat_count = 0
    for aid in activity_ids:
        if aid in seen:
            repeat_count += 1
        seen.add(aid)

    # Count inefficient classifications
    inefficient_count = sum(1 for c in classifications if c in (
        "valid_but_inefficient", "repeated_low_value", "premature",
    ))

    total = len(activity_ids)
    penalty = (repeat_count * 1.5 + inefficient_count) / max(1, total)
    return max(0.1, 1.0 - penalty)


def compute_closure_verification(activities):
    """Check if student verified the fix (closure)."""
    activity_ids = [a.get("action_id", "") for a in activities]

    if not activity_ids:
        return 1.0

    has_closure = any(aid in CLOSURE_ACTIONS for aid in activity_ids)

    # Check that closure is the last meaningful action
    if has_closure:
        closure_indices = [i for i, aid in enumerate(activity_ids) if aid in CLOSURE_ACTIONS]
        if closure_indices and closure_indices[-1] >= len(activity_ids) - 2:
            return 1.0
        return 0.6

    return 0.0


def compute_all_metrics(session_id, scenario_id):
    """
    Compute all five process metrics for a session.

    Returns:
        dict with safety_compliance, evidence_quality, fault_localization,
        diagnostic_efficiency, closure_verification
    """
    trace = build_diagnostic_trace(session_id, scenario_id)
    activities = trace.get("activities", [])

    return {
        "safety_compliance": round(compute_safety_compliance(activities), 2),
        "evidence_quality": round(compute_evidence_quality(activities), 2),
        "fault_localization": round(compute_fault_localization(activities), 2),
        "diagnostic_efficiency": round(compute_diagnostic_efficiency(activities), 2),
        "closure_verification": round(compute_closure_verification(activities), 2),
    }
