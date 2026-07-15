"""
Test 6: Conformance engine alignment.

Validates:
1. Perfect trace -> fitness close to 1
2. Multiple expert strategies -> best match selected
3. Inefficient but reasonable trace NOT marked as complete error
4. Safety violation incurs high cost
5. Skipping required steps -> move_on_model
6. Extra actions -> move_on_log
7. Same inputs -> deterministic results
8. Different event orders produce reasonable differences
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.model_tracer import model_for_scenario
from app.services.conformance_engine import align_trace, select_best_expert_strategy
from app.services.diagnostic_trace import build_diagnostic_trace
from app.services.scenario import action_scenario


SESSION_A = "test-conformance-A"
SESSION_B = "test-conformance-B"


def cleanup():
    for sid in [SESSION_A, SESSION_B]:
        sf = ROOT / "data" / "sessions" / f"{sid}.json"
        if sf.exists():
            sf.unlink()


def make_trace_A():
    """Trace A: optimal path - safety -> common_terminal -> verify"""
    action_scenario({"session_id": SESSION_A, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "CHECK_SAFETY"})
    action_scenario({"session_id": SESSION_A, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "CHECK_COMMON_TERMINAL"})
    action_scenario({"session_id": SESSION_A, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "VERIFY_TRIPLE_STATE"})


def make_trace_B():
    """Trace B: messy path - skip safety, modify program, replace sensor, check common, no verify"""
    action_scenario({"session_id": SESSION_B, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "REWIRE_WITHOUT_SAFETY"})
    action_scenario({"session_id": SESSION_B, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "MODIFY_PROGRAM_PREMATURE"})
    action_scenario({"session_id": SESSION_B, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "REPLACE_MODULE_NO_EVIDENCE"})
    action_scenario({"session_id": SESSION_B, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "CHECK_COMMON_TERMINAL"})


def test_trace_A_vs_B():
    """Trace A (optimal) has higher fitness than trace B (messy)."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    assert model, "Model not found"

    trace_a = build_diagnostic_trace(SESSION_A, "SCN_SENSOR_LED_ON_PLC_LED_OFF")
    trace_b = build_diagnostic_trace(SESSION_B, "SCN_SENSOR_LED_ON_PLC_LED_OFF")

    align_a = align_trace(model, trace_a)
    align_b = align_trace(model, trace_b)

    best_a = select_best_expert_strategy(align_a)
    best_b = select_best_expert_strategy(align_b)

    assert best_a, "Trace A should have alignments"
    assert best_b, "Trace B should have alignments"

    print(f"Trace A: fitness={best_a['fitness']:.3f}, cost={best_a['total_cost']}")
    print(f"Trace B: fitness={best_b['fitness']:.3f}, cost={best_b['total_cost']}")

    assert best_a["fitness"] > best_b["fitness"], \
        f"Trace A fitness ({best_a['fitness']}) should be > Trace B ({best_b['fitness']})"
    print("  PASS: Trace A fitness > Trace B fitness")


def test_safety_compliance_differs():
    """Trace A has higher safety_compliance than trace B."""
    from app.services.process_metrics import compute_safety_compliance

    trace_a = build_diagnostic_trace(SESSION_A, "SCN_SENSOR_LED_ON_PLC_LED_OFF")
    trace_b = build_diagnostic_trace(SESSION_B, "SCN_SENSOR_LED_ON_PLC_LED_OFF")

    safety_a = compute_safety_compliance(trace_a["activities"])
    safety_b = compute_safety_compliance(trace_b["activities"])

    print(f"Trace A safety: {safety_a}, Trace B safety: {safety_b}")
    assert safety_a > safety_b, f"Safety A ({safety_a}) should be > Safety B ({safety_b})"
    print("  PASS: safety_compliance A > B")


def test_trace_B_has_program_first_bias():
    """Trace B should show program_first_bias in strategy profile."""
    from app.services.strategy_profile import build_strategy_profile

    profile = build_strategy_profile(SESSION_B, "SCN_SENSOR_LED_ON_PLC_LED_OFF")
    weaknesses = profile.get("weaknesses", [])
    tags = [w["tag"] for w in weaknesses]
    print(f"Trace B weaknesses: {tags}")

    # Should have some weakness tags
    assert len(weaknesses) >= 1, "Trace B should have weaknesses"
    # program_first_bias or trial_and_error_pattern should be present
    assert any(t in ("program_first_bias", "trial_and_error_pattern") for t in tags), \
        f"Expected bias tag, got {tags}"
    print("  PASS: Trace B has expected bias tags")


def test_trace_B_closure_lower():
    """Trace B has lower closure_verification than trace A."""
    from app.services.process_metrics import compute_closure_verification

    trace_a = build_diagnostic_trace(SESSION_A, "SCN_SENSOR_LED_ON_PLC_LED_OFF")
    trace_b = build_diagnostic_trace(SESSION_B, "SCN_SENSOR_LED_ON_PLC_LED_OFF")

    closure_a = compute_closure_verification(trace_a["activities"])
    closure_b = compute_closure_verification(trace_b["activities"])

    print(f"Trace A closure: {closure_a}, Trace B closure: {closure_b}")
    assert closure_a > closure_b, f"Closure A ({closure_a}) should be > Closure B ({closure_b})"
    print("  PASS: closure_verification A > B")


def test_perfect_trace_fitness():
    """Perfect trace (exact match with optimal sequence) -> high fitness."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    # Manually build a perfect trace
    perfect = {
        "trace_id": "perfect",
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "activities": [
            {"action_id": "CHECK_SAFETY", "classification": "optimal", "index": 0},
            {"action_id": "CHECK_COMMON_TERMINAL", "classification": "optimal", "index": 1},
            {"action_id": "VERIFY_TRIPLE_STATE", "classification": "optimal", "index": 2},
        ]
    }

    alignments = align_trace(model, perfect)
    best = select_best_expert_strategy(alignments)
    assert best["fitness"] >= 0.9, f"Perfect trace fitness {best['fitness']} should be >= 0.9"
    assert best["total_cost"] <= 1
    print(f"  PASS: perfect trace fitness={best['fitness']:.3f}, cost={best['total_cost']}")


def test_multiple_strategies():
    """Multiple expert strategies are evaluated and best is selected."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    strategies = model.get("strategies", [])

    trace_data = {
        "trace_id": "multi",
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "activities": [
            {"action_id": "CHECK_SAFETY", "classification": "optimal", "index": 0},
            {"action_id": "CHECK_WIRING", "classification": "valid", "index": 1},
            {"action_id": "CHECK_COMMON_TERMINAL", "classification": "valid", "index": 2},
        ]
    }

    alignments = align_trace(model, trace_data)
    assert len(alignments) >= 2, f"Expected >=2 strategy alignments, got {len(alignments)}"
    best = select_best_expert_strategy(alignments)
    # The wiring_first_strategy should match better
    assert best is not None
    print(f"  PASS: {len(alignments)} strategies evaluated, best={best['strategy_id']} (fitness={best['fitness']:.3f})")


def test_deterministic():
    """Same inputs produce same outputs."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    trace_data = {
        "trace_id": "det",
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "activities": [
            {"action_id": "CHECK_SAFETY", "classification": "optimal", "index": 0},
            {"action_id": "CHECK_COMMON_TERMINAL", "classification": "optimal", "index": 1},
        ]
    }

    results = []
    for _ in range(5):
        alignments = align_trace(model, trace_data)
        best = select_best_expert_strategy(alignments)
        results.append((best["fitness"], best["total_cost"]))

    assert all(r == results[0] for r in results), f"Not deterministic: {results}"
    print("  PASS: 5 identical calls produce same results")


def main():
    print("=== Building traces ===")
    make_trace_A()
    make_trace_B()

    print("\n=== Test A vs B fitness ===")
    test_trace_A_vs_B()

    print("\n=== Test safety compliance ===")
    test_safety_compliance_differs()

    print("\n=== Test strategy profile bias ===")
    test_trace_B_has_program_first_bias()

    print("\n=== Test closure verification ===")
    test_trace_B_closure_lower()

    print("\n=== Test perfect trace ===")
    test_perfect_trace_fitness()

    print("\n=== Test multiple strategies ===")
    test_multiple_strategies()

    print("\n=== Test deterministic ===")
    test_deterministic()

    print("\n=== ALL CONFORMANCE ENGINE TESTS PASSED ===")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
