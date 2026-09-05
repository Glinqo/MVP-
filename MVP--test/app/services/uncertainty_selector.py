"""Uncertainty-driven training scenario selector.

Selects the next training scenario based on:
- Low-confidence abilities in the personal graph
- Abilities with only single-scenario evidence
- Unvalidated fault contexts
- Neighbor counterexample pairs that distinguish strategy profiles
- Safety prerequisite requirements

Avoids:
- Continuous repetition of same scenario
- Only targeting weakest abilities (diversity)
- Advanced scenarios without safety prerequisites
"""

import random
from .graph import build_student_ability_graph
from .coverage_matrix import build_coverage_matrix, get_abilities_needing_validation
from .strategy_profile import build_cumulative_strategy_profile
from .diagnostic_trace import list_student_traces
from .scenario_composer import (
    list_all_variants,
    get_neighbor_counterexample_pairs,
    compose_scenario,
)


def select_next_training_scenario(session_id, last_scenario_id=None, preferred_difficulty=None):
    """Select the next training scenario for a student.

    Returns dict with recommended scenario, variant, difficulty, and rationale.
    """
    # Gather student state
    student_graph = build_student_ability_graph(session_id)
    nodes = student_graph.get("nodes", [])
    traces = list_student_traces(session_id)
    profile = build_cumulative_strategy_profile(session_id)
    coverage = build_coverage_matrix(traces)
    needing_validation = get_abilities_needing_validation()

    # Track which scenarios have been done
    completed_scenarios = set()
    for t in traces:
        sid = t.get("scenario_id", "")
        if sid:
            completed_scenarios.add(sid)

    # Build ability lookup
    ability_map = {}
    for node in nodes:
        ms = node.get("mastery_score", 0)
        confidence = ms * 100 if ms <= 1.0 else ms
        ability_map[node["id"]] = {
            "name": node.get("label", node["id"]),
            "confidence": confidence,
            "status": node.get("status", "unknown"),
        }

    # ---- Scoring factors ----

    # Factor 1: Low-confidence abilities (weight 0.35)
    low_confidence_abilities = []
    for nid, info in ability_map.items():
        if info["confidence"] < 50:
            low_confidence_abilities.append(nid)

    # Factor 2: Single-scenario abilities (weight 0.30)
    single_scenario_abilities = [
        a["ability_id"] for a in needing_validation
        if a["reason"] == "single_scenario"
    ]

    # Factor 3: Unvalidated fault contexts (weight 0.20)
    all_variants = list_all_variants()
    candidate_scenarios = _score_scenarios(
        all_variants, ability_map, low_confidence_abilities,
        single_scenario_abilities, completed_scenarios, profile
    )

    # Factor 4: Neighbor counterexample pairs (weight 0.15)
    neighbor_pairs = get_neighbor_counterexample_pairs()
    neighbor_candidates = _evaluate_neighbor_pairs(
        neighbor_pairs, completed_scenarios, profile, ability_map
    )

    # Merge and rank
    merged = _merge_candidates(
        candidate_scenarios, neighbor_candidates, ability_map,
        completed_scenarios, last_scenario_id, profile
    )

    # Select best candidate
    if not merged:
        # Fallback: return any available scenario
        return _fallback_selection(all_variants, completed_scenarios, ability_map)

    best = merged[0]
    difficulty = _determine_difficulty(best, ability_map, preferred_difficulty)

    # Build recommendation
    reason_parts = []
    if best.get("low_confidence_match"):
        reason_parts.append(f"?????{best['low_confidence_match']}?????")
    if best.get("single_scenario_abilities"):
        names = ", ".join(best["single_scenario_abilities"][:2])
        reason_parts.append(f"{names}?????????")
    if best.get("neighbor_pair_reason"):
        reason_parts.append(best["neighbor_pair_reason"])
    if last_scenario_id and best["scenario_id"] != last_scenario_id:
        reason_parts.append(f"?????{last_scenario_id}???????")
    elif last_scenario_id and best["scenario_id"] == last_scenario_id:
        reason_parts.append("??????????????")

    if not reason_parts:
        reason_parts.append("??????????????")

    reason = "?".join(reason_parts) + "?"

    target_abilities = best.get("target_abilities", [])
    target_strategy_test = best.get("target_strategy_test")

    return {
        "next_training_scenario": {
            "scenario_id": best["scenario_id"],
            "variant_id": best.get("variant_id"),
            "difficulty": difficulty,
            "reason": reason,
            "target_abilities": target_abilities,
            "target_strategy_test": target_strategy_test,
            "score": best.get("score", 0),
        },
        "candidates_considered": len(merged),
        "low_confidence_abilities": low_confidence_abilities,
        "single_scenario_abilities": single_scenario_abilities,
        "completed_scenarios": list(completed_scenarios),
    }


def _score_scenarios(all_variants, ability_map, low_conf, single_scenario,
                     completed, profile):
    """Score each scenario based on how well it addresses student needs."""
    candidates = []

    for sid, variants in all_variants.items():
        # Collect abilities for this scenario from variants
        scenario_abilities = set()
        for v in variants:
            # Assume each variant's fault targets specific abilities
            scenario_abilities.add(v.get("fault_id", ""))

        # Score: low-confidence overlap
        low_conf_overlap = [a for a in low_conf if a in _variant_related_abilities(variants)]
        single_overlap = [a for a in single_scenario if a in _variant_related_abilities(variants)]

        score = 0.0
        score += len(low_conf_overlap) * 3.5
        score += len(single_overlap) * 3.0

        # Bonus for uncompleted scenarios
        if sid not in completed:
            score += 2.0
        else:
            # Penalty for already completed
            score -= 1.0

        # Bonus for having multiple variants (more fault contexts available)
        score += min(len(variants) - 1, 2) * 0.5

        if score > 0:
            # Best variant to recommend
            best_variant = _pick_best_variant(variants, low_conf_overlap, single_overlap)
            candidates.append({
                "scenario_id": sid,
                "variant_id": best_variant["id"] if best_variant else None,
                "score": score,
                "low_confidence_match": low_conf_overlap,
                "single_scenario_abilities": single_overlap,
                "target_abilities": list(set(low_conf_overlap + single_overlap)),
            })

    candidates.sort(key=lambda c: -c["score"])
    return candidates


def _variant_related_abilities(variants):
    """Get all ability IDs related to a set of variants (approximated via fault IDs)."""
    # This is a simplification; the full mapping is in coverage_matrix
    # For selector purposes, use fault_ids as proxy
    return {v.get("fault_id", "") for v in variants}


def _pick_best_variant(variants, low_conf, single_scenario):
    """Pick the variant most relevant to the student's needs."""
    if not variants:
        return None
    # For now, return the first one (deterministic)
    # In a more advanced version, match variant fault to specific ability gaps
    return variants[0]


def _evaluate_neighbor_pairs(pairs, completed, profile, ability_map):
    """Evaluate which neighbor counterexample pairs would benefit the student."""
    candidates = []
    weaknesses = profile.get("weaknesses", [])

    for pair in pairs:
        sid_a = pair["scenario_a"]["scenario_id"]
        sid_b = pair["scenario_b"]["scenario_id"]

        # Check if student has done one but not the other
        a_done = sid_a in completed
        b_done = sid_b in completed

        if a_done and not b_done:
            target_sid = sid_b
            pair_label = pair["scenario_b"]["title"]
        elif b_done and not a_done:
            target_sid = sid_a
            pair_label = pair["scenario_a"]["title"]
        elif not a_done and not b_done:
            # Neither done: pick one
            target_sid = sid_a
            pair_label = pair["scenario_a"]["title"]
        else:
            continue  # Both done

        # Check if student has the target bias
        bias_tag = pair.get("bias_if_both_wrong")
        has_bias = any(w["tag"] == bias_tag for w in weaknesses)

        score = 3.0
        if has_bias:
            score += 3.0  # Higher priority to address known bias

        candidates.append({
            "scenario_id": target_sid,
            "score": score,
            "neighbor_pair_reason": f"??????????{pair_label}?????{pair.get('target_strategy_test','??')}",
            "target_abilities": pair.get("target_abilities", []),
            "target_strategy_test": pair.get("target_strategy_test"),
        })

    return candidates


def _merge_candidates(scenario_candidates, neighbor_candidates, ability_map,
                      completed, last_scenario_id, profile):
    """Merge and deduplicate candidates, producing a final ranked list."""
    merged = {}

    for c in scenario_candidates:
        sid = c["scenario_id"]
        merged[sid] = dict(c)

    for nc in neighbor_candidates:
        sid = nc["scenario_id"]
        if sid in merged:
            merged[sid]["score"] += nc["score"]
            merged[sid]["neighbor_pair_reason"] = nc.get("neighbor_pair_reason")
            merged[sid]["target_strategy_test"] = nc.get("target_strategy_test")
            existing = set(merged[sid].get("target_abilities", []))
            existing.update(nc.get("target_abilities", []))
            merged[sid]["target_abilities"] = list(existing)
        else:
            merged[sid] = dict(nc)
            merged[sid]["low_confidence_match"] = []
            merged[sid]["single_scenario_abilities"] = []

    # Apply constraints
    result = []
    for sid, c in merged.items():
        # Avoid repeating last scenario unless it has remaining fault contexts
        if sid == last_scenario_id:
            c["score"] -= 2.0

        # Avoid consecutive same scenario
        if sid == last_scenario_id:
            c["score"] -= 1.0

        result.append(c)

    result.sort(key=lambda c: -c["score"])
    return result


def _determine_difficulty(candidate, ability_map, preferred):
    """Determine appropriate difficulty level."""
    if preferred:
        return preferred

    # Check if target abilities have low confidence
    target_abilities = candidate.get("target_abilities", [])
    if target_abilities:
        avg_conf = sum(
            ability_map.get(a, {}).get("confidence", 50) for a in target_abilities
        ) / len(target_abilities)

        if avg_conf < 30:
            return "beginner"
        elif avg_conf < 60:
            return "intermediate"
        else:
            return "advanced"

    return "intermediate"


def _fallback_selection(all_variants, completed, ability_map):
    """Fallback when no candidates matched."""
    for sid in all_variants:
        if sid not in completed:
            return {
                "next_training_scenario": {
                    "scenario_id": sid,
                    "variant_id": None,
                    "difficulty": "intermediate",
                    "reason": "?????????????????",
                    "target_abilities": [],
                    "target_strategy_test": None,
                    "score": 0,
                },
                "candidates_considered": 0,
                "low_confidence_abilities": [],
                "single_scenario_abilities": [],
                "completed_scenarios": list(completed),
            }

    # All done: cycle back
    all_sids = list(all_variants.keys())
    if all_sids:
        sid = all_sids[0]
        return {
            "next_training_scenario": {
                "scenario_id": sid,
                "variant_id": None,
                "difficulty": "advanced",
                "reason": "?????????????????????",
                "target_abilities": [],
                "target_strategy_test": None,
                "score": 0,
            },
            "candidates_considered": 0,
            "low_confidence_abilities": [],
            "single_scenario_abilities": [],
            "completed_scenarios": list(completed),
        }

    return {
        "next_training_scenario": None,
        "reason": "??????????",
    }
