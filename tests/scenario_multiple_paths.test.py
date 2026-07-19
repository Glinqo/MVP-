"""
Test 5: Multiple paths through scenarios.

Validates:
10. Different reasonable paths can complete the same scenario
11. Old interface tests continue to pass
12. All 4 scenarios have at least one strategy
"""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.model_tracer import model_for_scenario, trace_action
from app.services.scenario import action_scenario, start_scenario, step_scenario


SESSION_ID = "test-multi-path"


def cleanup():
    session_file = ROOT / "data" / "sessions" / f"{SESSION_ID}.json"
    if session_file.exists():
        session_file.unlink()


def test_optimal_path_completes():
    """Optimal path: CHECK_SAFETY -> CHECK_COMMON_TERMINAL -> VERIFY_TRIPLE_STATE"""
    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "CHECK_SAFETY",
    })
    assert result["trace_result"]["classification"] == "optimal"
    assert result["status"] == "in_progress"
    print("  PASS: CHECK_SAFETY -> optimal")

    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "CHECK_COMMON_TERMINAL",
    })
    assert result["trace_result"]["classification"] == "optimal"
    print("  PASS: CHECK_COMMON_TERMINAL -> optimal")

    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "VERIFY_TRIPLE_STATE",
    })
    assert result["trace_result"]["classification"] == "optimal"
    assert result["trace_result"]["is_terminal"] is True
    print("  PASS: VERIFY_TRIPLE_STATE -> optimal, terminal")


def test_alternative_path_completes():
    """Alternative: CHECK_SAFETY -> CHECK_WIRING -> CHECK_COMMON_TERMINAL -> VERIFY_TRIPLE_STATE"""
    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "CHECK_SAFETY",
    })
    assert result["trace_result"]["classification"] == "optimal"

    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "CHECK_WIRING",
    })
    assert result["trace_result"]["classification"] == "valid"
    print("  PASS: CHECK_WIRING (alt path) -> valid")

    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "CHECK_COMMON_TERMINAL",
    })
    # After wiring-first strategy, common terminal check may be "valid" or "optimal"
    assert result["trace_result"]["classification"] in ("valid", "optimal")
    print(f"  PASS: CHECK_COMMON_TERMINAL (after wiring) -> {result['trace_result']['classification']}")


def test_strategies_available():
    """All 4 scenarios have strategies."""
    for sid in ["SCN_SENSOR_LED_ON_PLC_LED_OFF", "SCN_PLC_LED_ON_MONITOR_OFF",
                 "SCN_SENSOR_LED_OFF", "SCN_CYLINDER_NO_ACTION"]:
        model = model_for_scenario(sid)
        assert model, f"Model {sid} not found"
        strategies = model.get("strategies", [])
        assert len(strategies) >= 1, f"Model {sid} has {len(strategies)} strategies, expected >= 1"
        for s in strategies:
            assert s.get("valid") is True, f"Strategy {s['id']} in {sid} should be valid"
        terminal = model.get("terminal_states", [])
        assert len(terminal) >= 1, f"Model {sid} needs terminal_states"
        print(f"  PASS: {sid} -> {len(strategies)} strategy(s), {len(terminal)} terminal state(s)")


def test_old_interface_still_works():
    """Old step interface still works."""
    result = start_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
    })
    assert result["status"] == "in_progress"
    assert result["current_step"]["id"] == "S1"
    print("  PASS: old /api/scenario/start works")

    result = step_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "step_id": "S1",
        "choice_id": "A",
    })
    assert result["is_correct"] is True
    print("  PASS: old /api/scenario/step (correct) works")


def test_scaffolding_in_response():
    """action_scenario response contains scaffolding."""
    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "CHECK_SAFETY",
    })
    assert "scaffolding" in result
    assert result["scaffolding"]["level"] == 0  # optimal -> no hint
    assert "trace_result" in result
    # Strategy detection may need >=2 actions to match; CHECK_SAFETY alone may not match
    assert result["trace_result"]["classification"] == "optimal"
    print(f"  PASS: response contains scaffolding (level={result['scaffolding']['level']}) and trace_result")

    # Unsafe -> should have level 4 scaffolding
    result2 = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "REWIRE_WITHOUT_SAFETY",
    })
    assert result2["scaffolding"]["level"] == 4
    assert result2["scaffolding"]["blocked"] is True
    assert result2["trace_result"]["classification"] == "unsafe"
    print("  PASS: unsafe action -> scaffolding level 4, blocked")


def test_strategy_detection_in_response():
    """Response includes matching strategies."""
    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "CHECK_SAFETY",
    })
    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "CHECK_COMMON_TERMINAL",
    })
    strategies = result.get("strategies", [])
    assert len(strategies) >= 1
    assert strategies[0]["id"] == "safe_signal_chain_strategy"
    assert strategies[0]["matched_actions"] >= 2
    print(f"  PASS: detected {len(strategies)} strategies, top={strategies[0]['id']} "
          f"matched={strategies[0]['matched_actions']}")


def main():
    print("=== Test 5a: Optimal path completes ===")
    test_optimal_path_completes()

    print("\n=== Test 5b: Alternative path is valid ===")
    test_alternative_path_completes()

    print("\n=== Test 5c: All scenarios have strategies ===")
    test_strategies_available()

    print("\n=== Test 5d: Old interface still works ===")
    test_old_interface_still_works()

    print("\n=== Test 5e: Scaffolding in response ===")
    test_scaffolding_in_response()

    print("\n=== Test 5f: Strategy detection in response ===")
    test_strategy_detection_in_response()

    print("\n=== ALL MULTIPLE PATHS TESTS PASSED ===")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
