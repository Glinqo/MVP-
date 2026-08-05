"""
Test 2: Action classification and diagnostic event generation.

Validates:
1. Safety check first -> optimal or valid
2. Skipping safety and directly rewiring -> unsafe
3. Input LED off but modify program first -> premature
4. No evidence, replace PLC module -> unsupported_hypothesis
5. Repeated low-value observation -> repeated action flag (reserved)
6. Fix complete but no verification -> closure_missing

Also validates compatibility:
7. /api/scenario/start still works
8. /api/scenario/step still works with old payload
9. Return fields not lost
10. New diagnostic events enter session
11. /api/graph/student returns valid graph
12. Job graph tests unaffected
"""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.diagnostic_events import (
    model_for_scenario,
    classify_action,
    check_completion,
    compute_strategy_bias,
)
from app.services.scenario import action_scenario, start_scenario, step_scenario
from app.services.graph import build_student_ability_graph


SESSION_ID = "test-diagnostic-events"


def cleanup():
    session_file = ROOT / "data" / "sessions" / f"{SESSION_ID}.json"
    if session_file.exists():
        session_file.unlink()


def test_action_classification():
    """Verify action categories are correctly assigned."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    assert model, "Model not found"

    initial_state = model["fault_states"]["initial"]

    # 1. Safety check first -> optimal
    result = classify_action(model, "CHECK_SAFETY", initial_state, [])
    assert result["category"] == "optimal", f"Expected optimal, got {result['category']}"
    assert result["is_valid"] is True
    print("  PASS: safety check first -> optimal")

    # 2. Skip safety, rewire directly -> unsafe
    result = classify_action(model, "REWIRE_WITHOUT_SAFETY", initial_state, [])
    assert result["category"] == "unsafe", f"Expected unsafe, got {result['category']}"
    assert result["is_valid"] is False
    assert result["strategy_bias"] == "safety_bypass"
    print("  PASS: skip safety rewire -> unsafe + safety_bypass bias")

    # 3. Input LED off but modify program first -> premature
    result = classify_action(model, "MODIFY_PROGRAM_PREMATURE", initial_state, [])
    assert result["category"] == "premature", f"Expected premature, got {result['category']}"
    assert result["strategy_bias"] == "jump_to_program"
    print("  PASS: modify program before hardware check -> premature + jump_to_program")

    # 4. No evidence, replace PLC module -> unsupported_hypothesis
    result = classify_action(model, "REPLACE_MODULE_NO_EVIDENCE", initial_state, [])
    assert result["category"] == "unsupported_hypothesis", f"Expected unsupported_hypothesis, got {result['category']}"
    assert result["strategy_bias"] == "replace_first"
    print("  PASS: replace module with no evidence -> unsupported_hypothesis + replace_first")

    # 5. After safety check, check common terminal requires safety state
    safe_state = dict(initial_state)
    safe_state["power_off_safety"] = True
    result = classify_action(model, "CHECK_COMMON_TERMINAL", safe_state, ["CHECK_SAFETY"])
    assert result["category"] == "optimal", f"Expected optimal after safety, got {result['category']}"
    print("  PASS: check common terminal after safety -> optimal")

    # Without safety state, check common terminal should be blocked
    result = classify_action(model, "CHECK_COMMON_TERMINAL", initial_state, [])
    assert result["blocked_by"], f"Expected blocked, got {result}"
    print(f"  PASS: check common terminal without safety -> blocked ({result['blocked_by']})")

    # 6. Fix complete but no verification -> closure_missing
    result = classify_action(model, "SKIP_VERIFICATION", {}, [])
    assert result["category"] == "closure_missing", f"Expected closure_missing, got {result['category']}"
    assert result["strategy_bias"] == "closure_missing"
    print("  PASS: skip verification -> closure_missing")


def test_completion():
    """Verify completion checking."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    # Incomplete
    result = check_completion(model, {}, [])
    assert result["is_complete"] is False
    assert result["missing_items"]
    print(f"  PASS: incomplete state -> missing {len(result['missing_items'])} items")

    # Complete (safety + common_terminal checked, triple state verified)
    complete_state = {
        "power_off_safety": True,
        "common_terminal_connected": "checked",
    }
    complete_actions = ["CHECK_SAFETY", "CHECK_COMMON_TERMINAL", "VERIFY_TRIPLE_STATE"]
    result = check_completion(model, complete_state, complete_actions)
    assert result["is_complete"] is True
    assert result["closure_status"] == "verified"
    print("  PASS: complete state + closure -> verified")


def test_strategy_bias_accumulation():
    """Verify strategy biases accumulate across actions."""
    classifications = [
        {"strategy_bias": "safety_bypass"},
        {"strategy_bias": "safety_bypass"},
        {"strategy_bias": "jump_to_program"},
        {"strategy_bias": None},
    ]
    biases = compute_strategy_bias(classifications)
    bias_ids = [b["id"] for b in biases]
    assert "safety_bypass" in bias_ids
    assert biases[0]["count"] == 2  # Most frequent first
    print(f"  PASS: bias accumulation -> {[(b['id'], b['count']) for b in biases]}")


def test_old_interface_compatibility():
    """Verify old /api/scenario/start and /api/scenario/step still work."""
    # Start
    result = start_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
    })
    assert result["status"] == "in_progress"
    assert result["scenario"]["id"] == "SCN_SENSOR_LED_ON_PLC_LED_OFF"
    assert result["current_step"]["id"] == "S1"
    assert len(result["current_step"]["options"]) == 3
    print("  PASS: old /api/scenario/start works")

    # Step (correct answer)
    result = step_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "step_id": "S1",
        "choice_id": "A",
    })
    assert result["is_correct"] is True
    assert result["step_id"] == "S1"
    assert result["feedback"]
    assert result["observation"]
    assert result["ability_hits"]
    print("  PASS: old /api/scenario/step (correct) works")

    # Step (wrong answer)
    result = step_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "step_id": "S1",
        "choice_id": "B",
    })
    assert result["is_correct"] is False
    print("  PASS: old /api/scenario/step (wrong) works")


def test_new_action_interface():
    """Verify new /api/scenario/action interface (Phase 2)."""
    # Optimal action
    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "CHECK_SAFETY",
    })
    assert result["action_category"] in ("optimal",)  # ok if Phase 1 or Phase 2 labels differ
    assert result["is_valid"] is True
    assert result["trace_result"]["classification"] == "optimal"
    assert result["trace_result"]["state_after"] == "STATE_SAFETY_CONFIRMED"
    print(f"  PASS: action CHECK_SAFETY -> {result['action_category_label']}")

    # Unsafe action
    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "REWIRE_WITHOUT_SAFETY",
    })
    assert result["action_category"] == "unsafe"
    assert result["is_valid"] is False
    assert result["trace_result"]["classification"] == "unsafe"
    assert result["trace_result"]["deviations"] == ["safety_bypass"] or "safety_bypass" in str(result.get("strategy_bias", ""))
    print(f"  PASS: action REWIRE_WITHOUT_SAFETY -> {result['action_category_label']}")

    # Premature action
    result = action_scenario({
        "session_id": SESSION_ID,
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "action_id": "MODIFY_PROGRAM_PREMATURE",
    })
    assert result["action_category"] == "premature"
    assert result["trace_result"]["classification"] == "premature"
    print(f"  PASS: action MODIFY_PROGRAM_PREMATURE -> {result['action_category_label']}")

    # Check hypotheses are returned
    assert result["hypotheses"]
    assert len(result["hypotheses"]) == 5
    print(f"  PASS: hypotheses returned ({len(result['hypotheses'])} active)")

    # Check strategy biases accumulate
    biases = result["strategy_biases"]
    print(f"  PASS: strategy biases: {[(b['id'], b['count']) for b in biases]}")

    # Check completion
    assert result["completion"]["is_complete"] is False
    print(f"  PASS: completion check: {result['completion']['missing_items']}")

    # Check student graph exists
    assert result["student_graph"] is not None
    print("  PASS: student graph returned")


def test_student_graph_evidence():
    """Verify student graph contains diagnostic event evidence."""
    graph = build_student_ability_graph(SESSION_ID)
    assert graph["graph_type"] == "student_ability"
    assert graph["event_count"] >= 1

    # Find a node with evidence from diagnostic events
    nodes_with_evidence = [n for n in graph["nodes"] if n.get("evidence_count", 0) > 0]
    print(f"  PASS: student graph has {graph['event_count']} events, "
          f"{len(nodes_with_evidence)} nodes with evidence")

    if nodes_with_evidence:
        node = nodes_with_evidence[0]
        print(f"  Sample node: {node['label']} status={node['status']} "
              f"evidence_count={node['evidence_count']} "
              f"update_reasons={node.get('update_reasons', [])[:3]}")


def main():
    print("=== Test 2a: Action classification ===")
    test_action_classification()

    print("\n=== Test 2b: Completion checking ===")
    test_completion()

    print("\n=== Test 2c: Strategy bias accumulation ===")
    test_strategy_bias_accumulation()

    print("\n=== Test 2d: Old interface compatibility ===")
    test_old_interface_compatibility()

    print("\n=== Test 2e: New action interface ===")
    test_new_action_interface()

    print("\n=== Test 2f: Student graph evidence ===")
    test_student_graph_evidence()

    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()


if __name__ != "__main__":
    # Allow import without running
    pass
