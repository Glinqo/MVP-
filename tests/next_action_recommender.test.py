"""Tests for next_action_recommender.py - Phase 5."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.next_action_recommender import recommend_next_actions, _compute_priority


def test_recommender_returns_actions():
    """Recommender returns actions list."""
    result = recommend_next_actions("default", count=5)
    assert "actions" in result
    assert len(result["actions"]) > 0
    assert len(result["actions"]) <= 5
    print("PASS: test_recommender_returns_actions")


def test_each_action_has_required_fields():
    """Each action has all required fields."""
    result = recommend_next_actions("default", count=3)
    required = ["type", "title", "ability_id", "ability_name", "reason", "estimated_minutes", "priority"]
    for action in result["actions"]:
        for field in required:
            assert field in action, f"Missing {field} in action"
        assert action["priority"] > 0, f"Priority should be > 0, got {action['priority']}"
        assert action["estimated_minutes"] > 0
    print("PASS: test_each_action_has_required_fields")


def test_actions_are_ranked():
    """Actions are ranked by priority descending."""
    result = recommend_next_actions("default", count=5)
    priorities = [a["priority"] for a in result["actions"]]
    assert priorities == sorted(priorities, reverse=True), "Actions not sorted by priority"
    print("PASS: test_actions_are_ranked")


def test_deterministic():
    """Same input produces same output."""
    r1 = recommend_next_actions("default", count=3)
    r2 = recommend_next_actions("default", count=3)
    ids1 = [a["ability_id"] for a in r1["actions"]]
    ids2 = [a["ability_id"] for a in r2["actions"]]
    assert ids1 == ids2, "Non-deterministic recommendations"
    print("PASS: test_deterministic")


def test_has_explanation():
    """Result includes explanation of ranking formula."""
    result = recommend_next_actions("default")
    assert "explanation" in result
    assert len(result["explanation"]) > 0
    print("PASS: test_has_explanation")


def test_demand_weight_contributes_to_priority():
    """Job graph demand_weight is accepted as the job-importance signal."""
    ability_state = {
        "cognitive_mastery_score": 80,
        "uncertainty": 0.1,
        "safety_score": 100,
    }
    with_demand, breakdown = _compute_priority(
        "plc_input_common_terminal",
        ability_state,
        {"plc_input_common_terminal": {"demand_weight": 2.0}},
        "default",
    )
    without_demand, _ = _compute_priority(
        "plc_input_common_terminal",
        ability_state,
        {"plc_input_common_terminal": {}},
        "default",
    )
    assert breakdown["job_weight"] > 0
    assert with_demand > without_demand
    print("PASS: test_demand_weight_contributes_to_priority")


if __name__ == "__main__":
    test_recommender_returns_actions()
    test_each_action_has_required_fields()
    test_actions_are_ranked()
    test_deterministic()
    test_has_explanation()
    test_demand_weight_contributes_to_priority()
    print("\nAll next_action_recommender tests PASSED")
