"""
Test 3: Behavior graph model tracer.

Validates:
1. Optimal path recognized as optimal
2. Second reasonable path recognized as valid
3. Correct but extra-step path recognized as valid_but_inefficient
4. Skip safety gate recognized as unsafe
5. Modify program before hardware check recognized as premature
6. Replace component with no evidence recognized as unsupported_hypothesis
7. Repeated observation of same low-value evidence recognized
8. Deterministic: same inputs always produce same outputs
"""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.model_tracer import (
    model_for_scenario,
    trace_action,
    state_flags_from_runtime,
    detect_matching_strategies,
)


def test_optimal_path():
    """Optimal: CHECK_SAFETY -> CHECK_COMMON_TERMINAL -> VERIFY_TRIPLE_STATE"""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    assert model, "Model not found"
    assert model.get("states"), "States not configured"

    runtime = {"state_id": "STATE_INITIAL"}
    trace = []

    # Step 1: optimal
    out = trace_action(model, runtime, "CHECK_SAFETY", trace)
    assert out["trace_result"]["classification"] == "optimal", f"Step 1: expected optimal, got {out['trace_result']['classification']}"
    assert out["trace_result"]["state_after"] == "STATE_SAFETY_CONFIRMED"
    assert out["trace_result"]["matched_strategy_id"] == "safe_signal_chain_strategy"
    assert out["trace_result"]["is_terminal"] is False
    runtime = out["runtime_state"]
    trace = out["student_trace_snapshot"]
    print("  PASS: step 1 CHECK_SAFETY -> optimal, state=STATE_SAFETY_CONFIRMED")

    # Step 2: optimal
    out = trace_action(model, runtime, "CHECK_COMMON_TERMINAL", trace)
    assert out["trace_result"]["classification"] == "optimal", f"Step 2: expected optimal, got {out['trace_result']['classification']}"
    assert out["trace_result"]["state_after"] == "STATE_COMMON_TERMINAL_CHECKED"
    runtime = out["runtime_state"]
    trace = out["student_trace_snapshot"]
    print("  PASS: step 2 CHECK_COMMON_TERMINAL -> optimal, state=STATE_COMMON_TERMINAL_CHECKED")

    # Step 3: optimal (terminal)
    out = trace_action(model, runtime, "VERIFY_TRIPLE_STATE", trace)
    assert out["trace_result"]["classification"] == "optimal"
    assert out["trace_result"]["state_after"] == "STATE_REPAIR_VERIFIED"
    assert out["trace_result"]["is_terminal"] is True
    print("  PASS: step 3 VERIFY_TRIPLE_STATE -> optimal, terminal state")


def test_second_valid_path():
    """Valid alternative: CHECK_SAFETY -> CHECK_WIRING -> CHECK_COMMON_TERMINAL"""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    runtime = {"state_id": "STATE_INITIAL"}
    trace = []

    out = trace_action(model, runtime, "CHECK_SAFETY", trace)
    assert out["trace_result"]["classification"] == "optimal"
    runtime = out["runtime_state"]
    trace = out["student_trace_snapshot"]

    out = trace_action(model, runtime, "CHECK_WIRING", trace)
    assert out["trace_result"]["classification"] == "valid", f"Step 2: expected valid, got {out['trace_result']['classification']}"
    assert out["trace_result"]["state_after"] == "STATE_WIRING_CHECKED"
    assert out["trace_result"]["matched_strategy_id"] == "wiring_first_strategy"
    print("  PASS: alternative path CHECK_WIRING -> valid, strategy=wiring_first_strategy")


def test_valid_but_inefficient():
    """Check sensor type first (valid but not most efficient)"""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    runtime = {"state_id": "STATE_INITIAL"}
    trace = []

    out = trace_action(model, runtime, "CHECK_SAFETY", trace)
    runtime = out["runtime_state"]
    trace = out["student_trace_snapshot"]

    out = trace_action(model, runtime, "CHECK_SENSOR_TYPE", trace)
    assert out["trace_result"]["classification"] == "valid_but_inefficient", \
        f"Expected valid_but_inefficient, got {out['trace_result']['classification']}"
    print("  PASS: CHECK_SENSOR_TYPE after safety -> valid_but_inefficient")


def test_unsafe_action():
    """Skip safety, directly rewire -> unsafe"""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    runtime = {"state_id": "STATE_INITIAL"}
    out = trace_action(model, runtime, "REWIRE_WITHOUT_SAFETY", [])
    assert out["trace_result"]["classification"] == "unsafe", f"Expected unsafe, got {out['trace_result']['classification']}"
    assert out["trace_result"]["accepted"] is False
    assert out["trace_result"]["deviations"] == ["safety_bypass"]
    print("  PASS: REWIRE_WITHOUT_SAFETY -> unsafe, not accepted")


def test_premature_action():
    """PLC input LED off but modify program first -> premature"""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    runtime = {"state_id": "STATE_INITIAL"}
    out = trace_action(model, runtime, "MODIFY_PROGRAM_PREMATURE", [])
    assert out["trace_result"]["classification"] == "premature", f"Expected premature, got {out['trace_result']['classification']}"
    assert out["trace_result"]["deviations"] == ["jump_to_program"]
    print("  PASS: MODIFY_PROGRAM_PREMATURE -> premature, deviation=jump_to_program")


def test_unsupported_hypothesis():
    """No evidence, replace PLC module -> unsupported_hypothesis"""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    runtime = {"state_id": "STATE_INITIAL"}
    out = trace_action(model, runtime, "REPLACE_MODULE_NO_EVIDENCE", [])
    assert out["trace_result"]["classification"] == "unsupported_hypothesis", \
        f"Expected unsupported_hypothesis, got {out['trace_result']['classification']}"
    assert out["trace_result"]["deviations"] == ["replace_first"]
    print("  PASS: REPLACE_MODULE_NO_EVIDENCE -> unsupported_hypothesis, deviation=replace_first")


def test_repeated_low_value():
    """Repeat CHECK_SAFETY in STATE_SAFETY_CONFIRMED -> repeated_low_value"""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    runtime = {"state_id": "STATE_INITIAL"}
    trace = []

    out = trace_action(model, runtime, "CHECK_SAFETY", trace)
    runtime = out["runtime_state"]
    trace = out["student_trace_snapshot"]

    # Now repeat CHECK_SAFETY
    out = trace_action(model, runtime, "CHECK_SAFETY", trace)
    assert out["trace_result"]["classification"] == "repeated_low_value", \
        f"Expected repeated_low_value, got {out['trace_result']['classification']}"
    assert out["trace_result"]["repeated_action"] is True
    print("  PASS: repeat CHECK_SAFETY -> repeated_low_value")


def test_deterministic():
    """Same inputs always produce same outputs."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    runtime = {"state_id": "STATE_INITIAL"}

    results = []
    for _ in range(5):
        out = trace_action(model, dict(runtime), "CHECK_SAFETY", [])
        results.append(out["trace_result"]["classification"])

    assert all(r == "optimal" for r in results), f"Not deterministic: {results}"
    print(f"  PASS: 5 identical calls all returned 'optimal'")


def test_strategy_detection():
    """Detect matching strategies from a student trace."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    trace = []
    runtime = {"state_id": "STATE_INITIAL"}

    out = trace_action(model, runtime, "CHECK_SAFETY", trace)
    runtime = out["runtime_state"]
    trace = out["student_trace_snapshot"]

    out = trace_action(model, runtime, "CHECK_COMMON_TERMINAL", trace)
    trace = out["student_trace_snapshot"]

    strategies = detect_matching_strategies(model, trace)
    assert len(strategies) > 0, "No strategies detected"
    top = strategies[0]
    assert top["id"] == "safe_signal_chain_strategy", f"Expected safe_signal_chain_strategy, got {top['id']}"
    assert top["matched_actions"] >= 2
    print(f"  PASS: detected {len(strategies)} strategies, top={top['id']}, matched={top['matched_actions']}")


def test_cylinder_multiple_paths():
    """Cylinder scenario: layered_strategy (electrical->program->air) or alt (electrical->air->program)."""
    model = model_for_scenario("SCN_CYLINDER_NO_ACTION")
    assert model.get("strategies"), "Cylinder model missing strategies"
    assert len(model["strategies"]) >= 2, f"Expected >=2 strategies, got {len(model['strategies'])}"

    # Path 1: electrical -> program
    runtime = {"state_id": "STATE_INITIAL"}
    trace = []
    out = trace_action(model, runtime, "LAYERED_CHECK_ELECTRICAL", trace)
    assert out["trace_result"]["classification"] == "optimal"
    runtime = out["runtime_state"]
    trace = out["student_trace_snapshot"]

    out = trace_action(model, runtime, "LAYERED_CHECK_PROGRAM", trace)
    assert out["trace_result"]["classification"] == "optimal"
    assert out["trace_result"]["state_after"] == "STATE_PROGRAM_CHECKED"
    print("  PASS: cylinder path1 (electrical->program) -> optimal")

    # Path 2: electrical -> air (valid alternative)
    runtime2 = {"state_id": "STATE_INITIAL"}
    trace2 = []
    out = trace_action(model, runtime2, "LAYERED_CHECK_ELECTRICAL", trace2)
    runtime2 = out["runtime_state"]
    trace2 = out["student_trace_snapshot"]

    out = trace_action(model, runtime2, "LAYERED_CHECK_AIR", trace2)
    assert out["trace_result"]["classification"] in ("valid", "optimal"), \
        f"Expected valid, got {out['trace_result']['classification']}"
    print(f"  PASS: cylinder path2 (electrical->air) -> {out['trace_result']['classification']}")

    # Unsafe: manual valve
    out = trace_action(model, {"state_id": "STATE_INITIAL"}, "MANUAL_VALVE_UNSAFE", [])
    assert out["trace_result"]["classification"] == "unsafe"
    print("  PASS: MANUAL_VALVE_UNSAFE -> unsafe")


def main():
    print("=== Test 3a: Optimal path ===")
    test_optimal_path()

    print("\n=== Test 3b: Second valid path ===")
    test_second_valid_path()

    print("\n=== Test 3c: Valid but inefficient ===")
    test_valid_but_inefficient()

    print("\n=== Test 3d: Unsafe ===")
    test_unsafe_action()

    print("\n=== Test 3e: Premature ===")
    test_premature_action()

    print("\n=== Test 3f: Unsupported hypothesis ===")
    test_unsupported_hypothesis()

    print("\n=== Test 3g: Repeated low-value ===")
    test_repeated_low_value()

    print("\n=== Test 3h: Deterministic ===")
    test_deterministic()

    print("\n=== Test 3i: Strategy detection ===")
    test_strategy_detection()

    print("\n=== Test 3j: Cylinder multiple paths ===")
    test_cylinder_multiple_paths()

    print("\n=== ALL MODEL TRACER TESTS PASSED ===")


if __name__ == "__main__":
    main()
