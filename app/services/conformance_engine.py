"""
Lightweight conformance checking engine.

Aligns student diagnostic traces against expert behavior model strategies.
Computes alignment moves, costs, and fitness scores.

Concepts borrowed from PM4Py (conformance checking, alignment, move types)
without copying AGPL-licensed source code. Pure Python, no dependencies.

Move types:
- sync_move: student action matches model action (cost 0)
- move_on_log: student did an action the model doesn't require (penalty)
- move_on_model: student skipped a required model action (penalty)
- unsafe_move: student did a dangerous action (heavy penalty)
"""

import json
from pathlib import Path

from .data_loader import ROOT
from .model_tracer import model_for_scenario


def load_cost_config():
    path = ROOT / "knowledge" / "process_deviation_costs.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_deviation_cost(cost_config, classification):
    """Map a classification to its numeric cost."""
    cost_map = {
        "unsafe": "unsafe_intervention",
        "premature": "premature_program_check",
        "unsupported_hypothesis": "unsupported_hypothesis",
        "closure_missing": "closure_verification_missing",
        "repeated_low_value": "repeated_low_value_action",
        "valid_but_inefficient": "signal_chain_layer_jump",
    }
    cost_key = cost_map.get(classification, "move_on_log")
    costs = cost_config.get("costs", {})
    return costs.get(cost_key, {}).get("cost", 2)


def align_trace(model, diagnostic_trace):
    """
    Align a student diagnostic trace against all valid strategies in the model.

    For each strategy, computes an alignment with sync/move_on_log/move_on_model/unsafe moves.

    Returns:
        list of alignment results, one per strategy
    """
    strategies = model.get("strategies", [])
    activities = diagnostic_trace.get("activities", [])
    cost_config = load_cost_config()
    student_action_ids = [a.get("action_id", "") for a in activities]
    student_classifications = {a.get("action_id", ""): a.get("classification", "valid") for a in activities}

    results = []
    for strategy in strategies:
        if not strategy.get("valid", True):
            continue

        optimal_seq = strategy.get("optimal_sequence", [])
        alignment = _compute_alignment(optimal_seq, student_action_ids, student_classifications, cost_config)

        results.append({
            "strategy_id": strategy["id"],
            "strategy_label": strategy.get("label", strategy["id"]),
            "strategy_priority": strategy.get("priority", 99),
            "alignment": alignment["moves"],
            "total_cost": alignment["total_cost"],
            "sync_count": alignment["sync_count"],
            "move_on_log_count": alignment["move_on_log_count"],
            "move_on_model_count": alignment["move_on_model_count"],
            "unsafe_count": alignment["unsafe_count"],
            "fitness": alignment["fitness"],
            "missing_actions": alignment["missing_actions"],
            "extra_actions": alignment["extra_actions"],
            "unsafe_actions": alignment["unsafe_actions"],
        })

    # Sort by: lowest cost first, then highest fitness
    results.sort(key=lambda r: (r["total_cost"], -r["fitness"]))
    return results


def _compute_alignment(optimal_seq, student_actions, student_classifications, cost_config):
    """
    Compute alignment between one strategy sequence and student actions.

    Uses a greedy approach: walk student actions, try to match against
    remaining model actions. Extra student actions become move_on_log;
    unmatched model actions become move_on_model.
    """
    moves = []
    total_cost = 0
    sync_count = 0
    move_on_log_count = 0
    move_on_model_count = 0
    unsafe_count = 0
    extra_actions = []
    missing_actions = []
    unsafe_actions = []

    model_idx = 0
    student_idx = 0

    while student_idx < len(student_actions) or model_idx < len(optimal_seq):
        if student_idx >= len(student_actions):
            # No more student actions -> remaining model actions are move_on_model
            missing = optimal_seq[model_idx]
            cost = get_deviation_cost(cost_config, "closure_missing")
            moves.append({
                "move_type": "move_on_model",
                "student_action": None,
                "model_action": missing,
                "cost": cost,
            })
            missing_actions.append(missing)
            total_cost += cost
            move_on_model_count += 1
            model_idx += 1
            continue

        if model_idx >= len(optimal_seq):
            # No more model actions -> remaining student actions are move_on_log
            student_action = student_actions[student_idx]
            classification = student_classifications.get(student_action, "valid")

            if classification == "unsafe":
                cost = get_deviation_cost(cost_config, "unsafe")
                move_type = "unsafe_move"
                unsafe_actions.append(student_action)
                unsafe_count += 1
            else:
                cost = get_deviation_cost(cost_config, classification)
                move_type = "move_on_log"
                extra_actions.append(student_action)
                move_on_log_count += 1

            moves.append({
                "move_type": move_type,
                "student_action": student_action,
                "model_action": None,
                "cost": cost,
            })
            total_cost += cost
            student_idx += 1
            continue

        student_action = student_actions[student_idx]
        model_action = optimal_seq[model_idx]
        classification = student_classifications.get(student_action, "valid")

        if student_action == model_action:
            # Sync
            moves.append({
                "move_type": "sync_move",
                "student_action": student_action,
                "model_action": model_action,
                "cost": 0,
            })
            sync_count += 1
            student_idx += 1
            model_idx += 1
        elif classification == "unsafe":
            # Unsafe is always a penalty
            cost = get_deviation_cost(cost_config, "unsafe")
            moves.append({
                "move_type": "unsafe_move",
                "student_action": student_action,
                "model_action": None,
                "cost": cost,
            })
            unsafe_actions.append(student_action)
            unsafe_count += 1
            total_cost += cost
            student_idx += 1
            # Don't advance model_idx for unsafe
        elif student_action in optimal_seq[model_idx + 1:]:
            # Student skipped current model action -> move_on_model
            cost = get_deviation_cost(cost_config, "closure_missing")
            moves.append({
                "move_type": "move_on_model",
                "student_action": None,
                "model_action": model_action,
                "cost": cost,
            })
            missing_actions.append(model_action)
            total_cost += cost
            move_on_model_count += 1
            model_idx += 1
            # Don't advance student_idx
        else:
            # Student did something not in model at all -> move_on_log
            cost = get_deviation_cost(cost_config, classification)
            moves.append({
                "move_type": "move_on_log",
                "student_action": student_action,
                "model_action": None,
                "cost": cost,
            })
            extra_actions.append(student_action)
            total_cost += cost
            move_on_log_count += 1
            student_idx += 1

    # Calculate fitness: 1.0 - (total_cost / max_possible_cost)
    # max_possible_cost: worst-case scenario
    max_possible = len(optimal_seq) * 5 + len(student_actions) * 3
    fitness = max(0.0, min(1.0, 1.0 - total_cost / max(1, max_possible)))

    return {
        "moves": moves,
        "total_cost": total_cost,
        "sync_count": sync_count,
        "move_on_log_count": move_on_log_count,
        "move_on_model_count": move_on_model_count,
        "unsafe_count": unsafe_count,
        "fitness": round(fitness, 4),
        "missing_actions": missing_actions,
        "extra_actions": extra_actions,
        "unsafe_actions": unsafe_actions,
    }


def calculate_alignment_cost(alignment):
    """Calculate total cost from an alignment result."""
    return alignment.get("total_cost", 0)


def select_best_expert_strategy(alignments):
    """
    Select the expert strategy that best matches the student trace.

    Returns the alignment with lowest cost and highest fitness.
    """
    if not alignments:
        return None
    return alignments[0]  # Already sorted by cost ASC, fitness DESC


def check_conformance(session_id, scenario_id):
    """
    Convenience: build a diagnostic trace and check conformance against model.

    Returns:
        dict with trace, alignments, best_strategy, fitness
    """
    from .diagnostic_trace import build_diagnostic_trace

    trace = build_diagnostic_trace(session_id, scenario_id)
    model = model_for_scenario(scenario_id)
    if not model:
        return {"trace": trace, "error": f"no model for {scenario_id}"}

    alignments = align_trace(model, trace)
    best = select_best_expert_strategy(alignments)

    return {
        "trace": trace,
        "alignments": alignments,
        "best_strategy_id": best["strategy_id"] if best else None,
        "best_strategy_label": best["strategy_label"] if best else None,
        "best_fitness": best["fitness"] if best else 0,
        "best_total_cost": best["total_cost"] if best else 0,
    }
