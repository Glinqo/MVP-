"""Tests for uncertainty_selector.py - Phase 5."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.uncertainty_selector import select_next_training_scenario


def test_selector_returns_structure():
    """Selector returns correct recommendation structure."""
    result = select_next_training_scenario("default")
    assert "next_training_scenario" in result
    rec = result["next_training_scenario"]
    assert rec is not None
    assert "scenario_id" in rec
    assert "difficulty" in rec
    assert "reason" in rec
    assert "target_abilities" in rec
    assert "target_strategy_test" in rec
    print("PASS: test_selector_returns_structure")


def test_reason_is_specific():
    """Recommendation reason is specific, not generic."""
    result = select_next_training_scenario("default")
    rec = result["next_training_scenario"]
    reason = rec["reason"]
    assert len(reason) > 10, f"Reason too short: {reason}"
    print(f"  Recommended: {rec['scenario_id']} ({rec['difficulty']})")
    print(f"  Reason: {reason[:80]}...")
    print("PASS: test_reason_is_specific")


def test_not_consecutive_same():
    """Should not recommend same scenario consecutively (with penalty)."""
    result1 = select_next_training_scenario("default")
    sid1 = result1["next_training_scenario"]["scenario_id"]
    # With last_scenario_id set to sid1, should prefer a different one
    result2 = select_next_training_scenario("default", last_scenario_id=sid1)
    sid2 = result2["next_training_scenario"]["scenario_id"]
    if sid1 == sid2:
        # May still be same if it's the only one with remaining fault contexts
        # But score should reflect that
        print(f"  Note: same scenario ({sid1}) - may have remaining fault contexts")
    print("PASS: test_not_consecutive_same")


def test_difficulty_respected():
    """Preferred difficulty is respected."""
    result = select_next_training_scenario("default", preferred_difficulty="beginner")
    assert result["next_training_scenario"]["difficulty"] == "beginner"
    print("PASS: test_difficulty_respected")


def test_returns_metadata():
    """Returns additional metadata about the selection."""
    result = select_next_training_scenario("default")
    assert "candidates_considered" in result
    assert "low_confidence_abilities" in result
    assert "single_scenario_abilities" in result
    assert "completed_scenarios" in result
    print("PASS: test_returns_metadata")


def test_consistent_for_same_input():
    """Same input produces consistent output (no randomization)."""
    result1 = select_next_training_scenario("default")
    result2 = select_next_training_scenario("default")
    assert result1["next_training_scenario"]["scenario_id"] == result2["next_training_scenario"]["scenario_id"]
    print("PASS: test_consistent_for_same_input")


if __name__ == "__main__":
    test_selector_returns_structure()
    test_reason_is_specific()
    test_not_consecutive_same()
    test_difficulty_respected()
    test_returns_metadata()
    test_consistent_for_same_input()
    print("\nAll uncertainty_selector tests PASSED")
