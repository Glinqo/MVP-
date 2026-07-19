"""
Behavior graph tracer for troubleshooting scenarios.

Core concepts borrowed from CTAT behavior graph:
- States: nodes in the graph, each with known_facts and remaining_hypotheses
- Transitions: edges, each triggered by an action, with classification and strategy
- Strategies: named expert paths through the graph
- Student trace: ordered list of (state_before, action_id, transition_result) tuples

The tracer is deterministic: same (model, state, action, trace) always produces
the same classification, state transition, and strategy match.
"""

import json
from pathlib import Path
from collections import Counter

from .data_loader import ROOT


MODELS_PATH = ROOT / "knowledge" / "troubleshooting_models.json"


# --- Model loading ---

def _load_models():
    if not MODELS_PATH.exists():
        return {}
    data = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
    return {m["scenario_id"]: m for m in data.get("models", [])}


def model_for_scenario(scenario_id):
    return _load_models().get(scenario_id)


# --- State lookup ---

def state_by_id(model, state_id):
    for s in model.get("states", []):
        if s["id"] == state_id:
            return s
    return None


# --- Transition matching ---

def find_matching_transitions(model, state_id, action_id):
    """
    Find all transitions matching a given (state_id, action_id) pair.
    Returns list of transition dicts, sorted by classification priority.
    """
    matches = []
    for t in model.get("transitions", []):
        if t.get("from_state") == state_id and t.get("action_id") == action_id:
            matches.append(t)

    # Sort: optimal first, then valid, then deviations
    priority_order = {
        "optimal": 0, "valid": 1, "valid_but_inefficient": 2,
        "closure_missing": 3, "repeated_low_value": 4,
        "premature": 5, "unsupported_hypothesis": 6, "unsafe": 7
    }
    matches.sort(key=lambda t: priority_order.get(t.get("classification", "valid"), 99))
    return matches


def _best_transition_match(model, state_id, action_id, student_trace):
    """
    Find the best matching transition considering current state and action history.

    Preference order:
    1. Exact match with strategy_id (student is on a known strategy)
    2. Exact match without strategy
    3. Fallback: use action's default classification from diagnostic_actions
    """
    transitions = find_matching_transitions(model, state_id, action_id)

    if not transitions:
        return None

    # If multiple matches, prefer the one whose strategy best matches trace
    if len(transitions) == 1:
        return transitions[0]

    # Check which strategy the student is currently on
    current_strategy = detect_current_strategy_id(model, student_trace)
    if current_strategy:
        for t in transitions:
            if t.get("strategy_id") == current_strategy:
                return t

    # Default: first (highest priority)
    return transitions[0]


# --- Action classification ---

def classify_action(model, state_id, action_id, student_trace):
    """
    Classify a student action within the behavior graph.

    Returns:
        dict with: accepted, classification, matched_transition_id,
        matched_strategy_id, state_before, state_after, deviations,
        missing_requirements, repeated_action
    """
    # Check if this is a repeated action (same action already in trace)
    repeated = _is_repeated_action(action_id, student_trace)

    transition = _best_transition_match(model, state_id, action_id, student_trace)

    if transition:
        classification = transition.get("classification", "valid")
        # If repeated and the transition is not already "repeated_low_value",
        # downgrade optimal/valid to valid_but_inefficient
        if repeated and classification in ("optimal", "valid"):
            classification = "valid_but_inefficient"

        return {
            "accepted": classification not in ("unsafe",),
            "classification": classification,
            "matched_transition_id": transition.get("id"),
            "matched_strategy_id": transition.get("strategy_id"),
            "state_before": state_id,
            "state_after": transition.get("to_state", state_id),
            "deviations": [transition.get("deviation")] if transition.get("deviation") else [],
            "missing_requirements": [],
            "repeated_action": repeated,
        }

    # No matching transition: try to find action in diagnostic_actions
    for action in model.get("diagnostic_actions", []):
        if action["id"] == action_id:
            return {
                "accepted": action.get("category") != "unsafe",
                "classification": action.get("category", "valid"),
                "matched_transition_id": None,
                "matched_strategy_id": None,
                "state_before": state_id,
                "state_after": state_id,  # No state change for unmapped action
                "deviations": [action.get("strategy_bias")] if action.get("strategy_bias") else [],
                "missing_requirements": [],
                "repeated_action": repeated,
            }

    # Completely unknown action
    return {
        "accepted": True,
        "classification": "valid",
        "matched_transition_id": None,
        "matched_strategy_id": None,
        "state_before": state_id,
        "state_after": state_id,
        "deviations": [],
        "missing_requirements": [],
        "repeated_action": repeated,
    }


def _is_repeated_action(action_id, student_trace):
    """Check if the same action was already in the trace."""
    for item in student_trace:
        if item.get("action_id") == action_id:
            return True
    return False


# --- Strategy detection ---

def _compute_strategy_match_score(trace_action_ids, strategy_sequence):
    """
    Compute how well a student trace matches a strategy's optimal sequence.
    Returns (matched_count, total_count) for partial matching.
    """
    matched = 0
    strategy_idx = 0
    for aid in trace_action_ids:
        if strategy_idx < len(strategy_sequence) and aid == strategy_sequence[strategy_idx]:
            matched += 1
            strategy_idx += 1
    return matched, len(strategy_sequence)


def detect_current_strategy_id(model, student_trace):
    """Detect which strategy the student is most likely following."""
    trace_action_ids = [item.get("action_id") for item in student_trace]
    strategies = model.get("strategies", [])

    best_id = None
    best_score = 0
    best_completeness = 0

    for strategy in strategies:
        optimal = strategy.get("optimal_sequence", [])
        matched, total = _compute_strategy_match_score(trace_action_ids, optimal)
        completeness = matched / total if total > 0 else 0

        if matched > best_score or (matched == best_score and completeness > best_completeness):
            best_score = matched
            best_completeness = completeness
            best_id = strategy["id"]

    # Only return if at least 2 actions matched
    return best_id if best_score >= 1 else None


def detect_matching_strategies(model, student_trace, min_match=1):
    """
    Return all strategies that match the student trace (with match scores).
    Sorted by match count descending.
    """
    trace_action_ids = [item.get("action_id") for item in student_trace]
    results = []
    for strategy in model.get("strategies", []):
        optimal = strategy.get("optimal_sequence", [])
        matched, total = _compute_strategy_match_score(trace_action_ids, optimal)
        if matched >= min_match:
            results.append({
                "id": strategy["id"],
                "label": strategy["label"],
                "priority": strategy.get("priority", 99),
                "matched_actions": matched,
                "total_actions": total,
                "completeness": matched / total if total > 0 else 0,
            })

    results.sort(key=lambda r: (-r["matched_actions"], r["priority"]))
    return results


# --- Trace action (the main entry point) ---

def trace_action(model, runtime_state, action_id, student_trace):
    """
    Main entry point: trace a student action through the behavior graph.

    Args:
        model: the troubleshooting model dict
        runtime_state: dict with at least "state_id" key (current state)
        action_id: the action being performed
        student_trace: list of previous trace results

    Returns:
        dict with classification, state transition, strategy match, and trace snapshot
    """
    state_id = runtime_state.get("state_id", "STATE_INITIAL")

    result = classify_action(model, state_id, action_id, student_trace)

    # Build new runtime state with updated state_id
    new_state = dict(runtime_state)
    new_state["state_id"] = result["state_after"]

    # Detect matching strategies
    strategies = detect_matching_strategies(model, student_trace + [{"action_id": action_id}])

    # Check if terminal state reached
    terminal_states = model.get("terminal_states", [])
    is_terminal = result["state_after"] in terminal_states

    # Build updated trace entry
    trace_entry = {
        "action_id": action_id,
        "state_before": state_id,
        "state_after": result["state_after"],
        "classification": result["classification"],
        "strategy_id": result["matched_strategy_id"],
        "repeated": result["repeated_action"],
    }

    return {
        "trace_result": {
            "accepted": result["accepted"],
            "classification": result["classification"],
            "matched_transition_id": result["matched_transition_id"],
            "matched_strategy_id": result["matched_strategy_id"],
            "state_before": state_id,
            "state_after": result["state_after"],
            "deviations": result["deviations"],
            "missing_requirements": result["missing_requirements"],
            "repeated_action": result["repeated_action"],
            "is_terminal": is_terminal,
        },
        "strategies": strategies,
        "runtime_state": new_state,
        "student_trace_snapshot": student_trace + [trace_entry],
    }


# --- State flag helpers ---

def state_flags_from_runtime(model, runtime_state):
    """Extract known flags from runtime state for a model."""
    state_id = runtime_state.get("state_id", "STATE_INITIAL")
    state = state_by_id(model, state_id)
    if state:
        return dict(state.get("flags", {}))
    return {}


def missing_required_flags(model, runtime_state):
    """Return flags that are still false (not yet achieved)."""
    flags = state_flags_from_runtime(model, runtime_state)
    return [k for k, v in flags.items() if not v]
