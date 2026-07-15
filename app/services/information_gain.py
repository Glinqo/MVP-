"""
Information gain calculation for diagnostic action selection.

Computes entropy and expected entropy reduction from candidate actions
on the remaining hypothesis space. Uses equal-weight or discrete-weight
hypotheses. No probabilistic inference beyond what the model provides.

Handles edge cases: empty hypothesis set, single remaining hypothesis,
actions that cannot distinguish any hypotheses.
"""

import math


def entropy(weights):
    """
    Calculate Shannon entropy for a set of hypothesis weights.

    Handles: empty set (0), single hypothesis (0).

    Args:
        weights: list of non-negative floats (confidence values).

    Returns:
        float: entropy value.
    """
    total = sum(weights)
    if total <= 0 or len(weights) <= 1:
        return 0.0

    normalized = [w / total for w in weights]
    ent = 0.0
    for p in normalized:
        if p > 0:
            ent -= p * math.log2(p)
    return ent


def expected_entropy_after_action(hypotheses, action_id, evidence_map):
    """
    Estimate expected entropy after performing an action.

    The action can either:
    - Eliminate some hypotheses (refutes_if_ok)
    - Confirm some hypotheses (supports_if_bad)

    Since we don't know the actual outcome before doing the action,
    we compute: weighted average of entropy under each possible outcome.

    For simplicity, we assume equal probability of each outcome and
    calculate the entropy reduction from the hypotheses each outcome
    would affect.

    Args:
        hypotheses: dict of {id: {confidence, status}}
        action_id: the action being evaluated
        evidence_map: from policy config: {action_id: {refutes_if_ok: [hid,...], supports_if_bad: [hid,...]}}

    Returns:
        (expected_entropy, hypothesis_reduction): entropy value and list of affected hypotheses
    """
    active = {hid: h for hid, h in hypotheses.items() if h["status"] == "active"}
    if not active:
        return 0.0, []

    action_evidence = evidence_map.get(action_id, {})
    refutes = set(action_evidence.get("refutes_if_ok", []))
    supports = set(action_evidence.get("supports_if_bad", []))

    affected = refutes | supports
    if not affected:
        return entropy([h["confidence"] for h in active.values()]), []

    # Scenario 1: action outcome refutes (eliminates some hypotheses)
    remaining_after_refute = {
        hid: h for hid, h in active.items()
        if hid not in refutes
    }
    ent_refute = entropy([h["confidence"] for h in remaining_after_refute.values()])

    # Scenario 2: action outcome supports (strengthens some, but may also
    # mean the refuted ones are less likely). For simplicity, we only
    # model the refute case for information gain.
    # A full model would weight by P(outcome). We use equal weight.

    # The information gain is primarily from elimination
    current_ent = entropy([h["confidence"] for h in active.values()])
    expected_ent = ent_refute  # Simplified: assume one outcome
    hypothesis_reduction = list(refutes)

    return expected_ent, hypothesis_reduction


def calculate_information_gain(hypotheses, action_id, evidence_map):
    """
    Calculate information gain from performing an action.

    IG = H(current) - H(expected_after_action)

    Handles:
    - Empty hypothesis set -> 0
    - Single remaining hypothesis -> 0
    - Action cannot distinguish any hypotheses -> 0
    - Multiple actions with equal IG -> same value (tie-break external)

    Returns:
        (information_gain, hypothesis_reduction_list)
    """
    active = {hid: h for hid, h in hypotheses.items() if h["status"] == "active"}
    if len(active) <= 1:
        return 0.0, []

    current_ent = entropy([h["confidence"] for h in active.values()])
    expected_ent, hypothesis_reduction = expected_entropy_after_action(hypotheses, action_id, evidence_map)

    ig = max(0.0, current_ent - expected_ent)
    return round(ig, 4), hypothesis_reduction


def normalized_information_gain(hypotheses, action_id, evidence_map):
    """
    Calculate information gain normalized to [0, 1].

    Normalization: IG / max_possible_IG where max_possible_IG is the
    entropy if one action could eliminate all hypotheses.
    """
    active = {hid: h for hid, h in hypotheses.items() if h["status"] == "active"}
    if len(active) <= 1:
        return 0.0, []

    ig, reduction = calculate_information_gain(hypotheses, action_id, evidence_map)
    max_ent = entropy([h["confidence"] for h in active.values()])

    if max_ent <= 0:
        return 0.0, []

    return round(ig / max_ent, 4), reduction
