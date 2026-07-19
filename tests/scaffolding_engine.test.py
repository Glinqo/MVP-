"""
Test 4: Scaffolding engine hint levels.

Validates:
8. First ordinary error -> light hint (level_1)
9. Consecutive same-type errors -> escalating hints
10. Safety violation -> immediate max-level safety hint (level_4)
"""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.model_tracer import model_for_scenario, trace_action
from app.services.scaffolding_engine import generate_hint, determine_hint_level
from app.services.troubleshooting_constraints import (
    check_safety_constraints,
    count_consecutive_deviations,
    get_deviation_trend,
)


def test_first_deviation_level_1():
    """First ordinary deviation -> level 1 hint."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    # First action: skip safety, go to premature
    out = trace_action(model, {"state_id": "STATE_INITIAL"}, "MODIFY_PROGRAM_PREMATURE", [])
    trace_result = out["trace_result"]
    trace = out["student_trace_snapshot"]

    level, reason = determine_hint_level(trace_result, trace[:-1] if len(trace) > 1 else [],
                                          trace_result["classification"], {})
    assert level == 1, f"First deviation: expected level 1, got {level}"
    print(f"  PASS: first premature action -> level {level} ({reason})")


def test_consecutive_deviation_escalation():
    """Two consecutive same-type -> level 2, three -> level 3."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    runtime = {"state_id": "STATE_INITIAL"}
    trace_before = []  # trace BEFORE current action (history only)

    # First premature
    out = trace_action(model, runtime, "MODIFY_PROGRAM_PREMATURE", trace_before)
    new_trace = out["student_trace_snapshot"]  # trace AFTER action
    t1 = out["trace_result"]
    # trace_before for hint = old history (empty for first call)
    level, _ = determine_hint_level(t1, trace_before, t1["classification"], {})
    assert level == 1, f"First deviation: level {level}"
    print(f"  PASS: deviation 1 -> level {level}")

    # Second premature (same type): trace_before should include the first
    runtime2 = out["runtime_state"]
    trace_before2 = new_trace   # history now includes first premature
    out2 = trace_action(model, runtime2, "MODIFY_PROGRAM_PREMATURE", trace_before2)
    t2 = out2["trace_result"]
    level2, _ = determine_hint_level(t2, trace_before2, t2["classification"], {})
    assert level2 == 2, f"Second consecutive: expected level 2, got {level2}"
    print(f"  PASS: deviation 2 (consecutive) -> level {level2}")

    # Third premature
    trace_before3 = out2["student_trace_snapshot"]
    out3 = trace_action(model, out2["runtime_state"], "MODIFY_PROGRAM_PREMATURE", trace_before3)
    t3 = out3["trace_result"]
    level3, _ = determine_hint_level(t3, trace_before3, t3["classification"], {})
    assert level3 == 3, f"Third consecutive: expected level 3, got {level3}"
    print(f"  PASS: deviation 3 (consecutive) -> level {level3}")


def test_safety_violation_level_4():
    """Safety violation -> immediate level 4."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    out = trace_action(model, {"state_id": "STATE_INITIAL"}, "REWIRE_WITHOUT_SAFETY", [])
    t = out["trace_result"]

    level, reason = determine_hint_level(t, [], t["classification"], {})
    assert level == 4, f"Safety violation: expected level 4, got {level}"
    print(f"  PASS: safety violation -> level {level} ({reason})")

    # Verify the hint message is a safety block
    flags = {}
    hint = generate_hint(model, t, [], flags, "STATE_INITIAL", "REWIRE_WITHOUT_SAFETY")
    assert hint["level"] == 4
    assert hint["blocked"] is True
    assert "安全" in hint["message"]
    print(f"  PASS: safety hint message contains safety warning, blocked={hint['blocked']}")


def test_safety_constraint_check():
    """Check safety constraints for various actions."""
    flags = {"safety_confirmed": False, "power_off_safety": False}

    # Unsafe action
    result = check_safety_constraints(flags, "REWIRE_WITHOUT_SAFETY", is_unsafe_action=True)
    assert result["blocked"] is True
    assert result["level"] == "critical"
    print("  PASS: unsafe action -> blocked, critical")

    # Safe action with safety gate
    result = check_safety_constraints(flags, "CHECK_COMMON_TERMINAL", is_unsafe_action=False)
    assert result["blocked"] is False
    assert result["level"] == "warning"
    print("  PASS: terminal check without safety -> warning (not blocked, but warned)")

    # Safe action with safety confirmed
    flags2 = {"safety_confirmed": True, "power_off_safety": True}
    result = check_safety_constraints(flags2, "CHECK_COMMON_TERMINAL", is_unsafe_action=False)
    assert result["level"] == "ok"
    print("  PASS: terminal check with safety -> ok")


def test_deviation_trend():
    """Deviation trend analysis."""
    trace = [
        {"action_id": "CHECK_SAFETY", "classification": "optimal", "deviation": None},
        {"action_id": "MODIFY_PROGRAM_PREMATURE", "classification": "premature", "deviation": "jump_to_program"},
        {"action_id": "MODIFY_PROGRAM_PREMATURE", "classification": "premature", "deviation": "jump_to_program"},
    ]
    trend = get_deviation_trend(trace)
    # 3 recent entries: optimal, premature, premature -> worsening (2/3 non-optimal)
    assert trend["trend"] in ("stable", "worsening")
    assert trend["dominant_deviation"] == "jump_to_program"
    assert trend["non_optimal_count"] == 2
    print(f"  PASS: trend={trend['trend']}, dominant={trend['dominant_deviation']}")

    # After recovery (add optimal action)
    trace2 = trace + [{"action_id": "CHECK_COMMON_TERMINAL", "classification": "optimal", "deviation": None}]
    trend2 = get_deviation_trend(trace2)
    # Last action is optimal - deviation is still present in window
    assert trend2["non_optimal_count"] == 2  # 2 premature still in window
    print(f"  PASS: trend after recovery -> {trend2['trend']} (non_optimal={trend2['non_optimal_count']})")


def test_repeated_action_level_3():
    """Repeated low-value action -> level 3."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    runtime = {"state_id": "STATE_INITIAL"}
    trace = []

    out = trace_action(model, runtime, "CHECK_SAFETY", trace)
    runtime = out["runtime_state"]
    trace = out["student_trace_snapshot"]

    # Repeat CHECK_SAFETY
    out = trace_action(model, runtime, "CHECK_SAFETY", trace)
    t = out["trace_result"]

    level, reason = determine_hint_level(t, trace, t["classification"], {})
    assert level == 3, f"Repeated low-value: expected level 3, got {level}"
    print(f"  PASS: repeated low-value action -> level {level} ({reason})")


def test_hint_generation():
    """Generate actual hint messages."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    # Optimal action -> no hint
    out = trace_action(model, {"state_id": "STATE_INITIAL"}, "CHECK_SAFETY", [])
    flags = {"power_off_safety": True}
    hint = generate_hint(model, out["trace_result"], [], flags, "STATE_INITIAL", "CHECK_SAFETY")
    assert hint["level"] == 0
    assert hint["message"] is None
    print("  PASS: optimal action -> level 0 (no hint)")

    # Valid but inefficient
    runtime = out["runtime_state"]
    trace = out["student_trace_snapshot"]
    out2 = trace_action(model, runtime, "CHECK_SENSOR_TYPE", trace)
    hint = generate_hint(model, out2["trace_result"], trace, flags,
                         runtime.get("state_id", "STATE_INITIAL"), "CHECK_SENSOR_TYPE")
    assert hint["level"] == 1
    assert hint["message"] is not None
    print(f"  PASS: valid_but_inefficient -> level {hint['level']}: '{hint['message']}'")


def main():
    print("=== Test 4a: First deviation -> level 1 ===")
    test_first_deviation_level_1()

    print("\n=== Test 4b: Consecutive deviation escalation ===")
    test_consecutive_deviation_escalation()

    print("\n=== Test 4c: Safety violation -> level 4 ===")
    test_safety_violation_level_4()

    print("\n=== Test 4d: Safety constraint check ===")
    test_safety_constraint_check()

    print("\n=== Test 4e: Deviation trend ===")
    test_deviation_trend()

    print("\n=== Test 4f: Repeated action -> level 3 ===")
    test_repeated_action_level_3()

    print("\n=== Test 4g: Hint generation ===")
    test_hint_generation()

    print("\n=== ALL SCAFFOLDING ENGINE TESTS PASSED ===")


if __name__ == "__main__":
    main()
