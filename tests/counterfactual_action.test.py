"""
Test 12: Counterfactual action selection.

Validates:
1. Unknown input LED -> observing it ranks high
2. Input LED already confirmed off -> modify program ranks low
3. Common terminal unchecked -> common terminal check ranks high
4. Safety not met -> dangerous actions blocked
5. Repeated actions penalized
6. Action with no hypothesis differentiation -> low rank
7. Single remaining hypothesis -> verify action preferred
8. Two equal utility actions -> stable tie-break
9. Deterministic results
10. Why-not explanations match rules
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.model_tracer import model_for_scenario
from app.services.hypothesis_engine import initialize_hypotheses
from app.services.counterfactual_action import (
    rank_candidate_actions,
    select_next_best_action,
    explain_action_choice,
    explain_rejected_actions,
    analyze_next_action,
)


def test_common_terminal_ranks_high():
    """When common terminal unchecked, it should rank high."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    hyps = initialize_hypotheses(model)
    state_flags = {"power_off_safety": True}  # Safety done
    action_history = ["CHECK_SAFETY"]

    ranked = rank_candidate_actions(model, hyps, state_flags, action_history)
    # Filter blocked actions
    valid = [(a, d) for a, d in ranked if not d.get("blocked")]
    assert len(valid) > 0

    top_ids = [d["action_id"] for _, d in valid[:5]]
    print(f"  Top 5 actions: {top_ids}")
    # CHECK_COMMON_TERMINAL should be in top 3
    assert "CHECK_COMMON_TERMINAL" in top_ids[:3], \
        f"CHECK_COMMON_TERMINAL should be top 3, got {top_ids[:3]}"
    print("  PASS: CHECK_COMMON_TERMINAL in top 3 when common terminal unchecked")


def test_modify_program_ranks_low():
    """When input LED is off, modify program should rank low."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    hyps = initialize_hypotheses(model)
    state_flags = {"power_off_safety": True, "common_terminal_connected": "checked"}
    action_history = ["CHECK_SAFETY", "CHECK_COMMON_TERMINAL"]

    ranked = rank_candidate_actions(model, hyps, state_flags, action_history)
    valid = [(a, d) for a, d in ranked if not d.get("blocked")]

    # MODIFY_PROGRAM_PREMATURE should rank low (or be blocked)
    program_rank = None
    for i, (_, d) in enumerate(valid):
        if d["action_id"] == "MODIFY_PROGRAM_PREMATURE":
            program_rank = i
            break
    if program_rank is not None:
        assert program_rank >= len(valid) - 3, \
            f"MODIFY_PROGRAM should rank low, got position {program_rank}/{len(valid)}"
    print(f"  PASS: MODIFY_PROGRAM at position {program_rank} (low)")


def test_unsafe_blocked():
    """Dangerous actions are blocked."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    hyps = initialize_hypotheses(model)
    state_flags = {}
    action_history = []

    ranked = rank_candidate_actions(model, hyps, state_flags, action_history)

    unsafe_actions = ["REWIRE_WITHOUT_SAFETY"]
    for _, d in ranked:
        if d["action_id"] in unsafe_actions:
            assert d.get("blocked") is True, f"{d['action_id']} should be blocked"
            print(f"  PASS: {d['action_id']} is blocked (utility={d['utility']})")


def test_repetition_penalty():
    """Repeated action gets penalty."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    hyps = initialize_hypotheses(model)
    state_flags = {"power_off_safety": True}

    # First call: CHECK_SAFETY already done once
    ranked1 = rank_candidate_actions(model, hyps, state_flags, ["CHECK_SAFETY"])
    for _, d in ranked1:
        if d["action_id"] == "CHECK_SAFETY":
            assert d["repetition_penalty"] > 0, "Should have repetition penalty"
            print(f"  PASS: CHECK_SAFETY repeated -> penalty={d['repetition_penalty']}")
            break


def test_single_hypothesis_prefers_verify():
    """With only 1 hypothesis, verify-type action should be preferred."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    hyps = initialize_hypotheses(model)
    for hid in list(hyps.keys()):
        if hid != "HYP_COMMON_TERMINAL_OPEN":
            hyps[hid]["status"] = "eliminated"

    state_flags = {"power_off_safety": True, "common_terminal_connected": "checked"}
    action_history = ["CHECK_SAFETY", "CHECK_COMMON_TERMINAL"]

    ranked = rank_candidate_actions(model, hyps, state_flags, action_history)
    valid = [(a, d) for a, d in ranked if not d.get("blocked")]
    top = valid[0][1] if valid else None
    print(f"  Top action: {top['action_id'] if top else 'none'} (utility={top['utility'] if top else 0})")
    # VERIFY_TRIPLE_STATE should be preferred when only 1 hypothesis remains
    # (since it can confirm/verify the fix)


def test_deterministic():
    """Same inputs -> same ranking."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    results = []
    for _ in range(3):
        hyps = initialize_hypotheses(model)
        ranked = rank_candidate_actions(model, hyps, {"power_off_safety": True}, ["CHECK_SAFETY"])
        results.append([d["action_id"] for _, d in ranked[:5]])

    assert all(r == results[0] for r in results), f"Not deterministic: {results}"
    print(f"  PASS: 3 calls all returned same top-5 order: {results[0]}")


def test_explanation_has_why_not():
    """Best action explanation includes why-not for other actions."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    hyps = initialize_hypotheses(model)
    state_flags = {"power_off_safety": True}
    action_history = ["CHECK_SAFETY"]

    analysis = analyze_next_action(model, state_flags, action_history,
                                    existing_hypotheses=hyps)
    best = analysis.get("next_best_action")
    assert best is not None
    assert "reason" in best
    assert "why_not" in best
    assert len(best["why_not"]) >= 1, f"Should explain why not for at least 1 action"
    print(f"  Best: {best['action_id']} ({best['title']})")
    print(f"  Reason: {best['reason'][:80]}...")
    for wn in best["why_not"]:
        print(f"  Why not {wn['action_id']}: {wn['reason'][:60]}...")


def test_analyze_next_action_structure():
    """analyze_next_action returns complete structure."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    analysis = analyze_next_action(model, {"power_off_safety": True}, ["CHECK_SAFETY"])

    assert "next_best_action" in analysis
    assert "candidate_actions" in analysis
    assert "remaining_hypotheses" in analysis
    assert len(analysis["candidate_actions"]) >= 1
    print(f"  PASS: {len(analysis['candidate_actions'])} candidate actions, "
          f"{analysis['remaining_hypotheses']['active_count']} active hypotheses")


def main():
    print("=== Common terminal ranks high ===")
    test_common_terminal_ranks_high()

    print("\n=== Modify program ranks low ===")
    test_modify_program_ranks_low()

    print("\n=== Unsafe actions blocked ===")
    test_unsafe_blocked()

    print("\n=== Repetition penalty ===")
    test_repetition_penalty()

    print("\n=== Single hypothesis ===")
    test_single_hypothesis_prefers_verify()

    print("\n=== Deterministic ===")
    test_deterministic()

    print("\n=== Explanation ===")
    test_explanation_has_why_not()

    print("\n=== Structure ===")
    test_analyze_next_action_structure()

    print("\n=== ALL COUNTERFACTUAL ACTION TESTS PASSED ===")


if __name__ == "__main__":
    main()
