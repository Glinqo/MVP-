"""Tests for ability_state_engine.py - Phase 2."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.ability_state_engine import compute_ability_state, _generate_recommendation


def test_all_abilities_have_complete_structure():
    """All 25 abilities have complete state structures."""
    state = compute_ability_state("default")
    abilities = state.get("abilities", {})
    assert len(abilities) == 25, f"Expected 25 abilities, got {len(abilities)}"

    required_fields = [
        "knowledge_mastery", "procedure_mastery", "transfer_score", "safety_score",
        "cognitive_mastery_score", "uncertainty", "status", "status_reason",
        "evidence_summary", "recommended_action"
    ]
    for aid, astate in abilities.items():
        for field in required_fields:
            assert field in astate, f"Missing {field} in {aid}"

    print("PASS: test_all_abilities_have_complete_structure")


def test_blank_student_returns_unknown():
    """Blank student returns unknown status for all abilities."""
    state = compute_ability_state("default")
    for aid, astate in state["abilities"].items():
        assert astate["status"] in ("unknown", "touched", "weak", "improving", "mastered"), \
            f"Invalid status {astate['status']} for {aid}"
    print("PASS: test_blank_student_returns_unknown")


def test_scores_in_range():
    """All scores are in 0-100 range."""
    state = compute_ability_state("default")
    for aid, astate in state["abilities"].items():
        for key in ["knowledge_mastery", "procedure_mastery", "transfer_score", "safety_score", "cognitive_mastery_score"]:
            val = astate[key]
            assert 0 <= val <= 100, f"{key} for {aid} = {val}, expected 0-100"
        assert 0 <= astate["uncertainty"] <= 1, f"uncertainty for {aid} = {astate['uncertainty']}"
    print("PASS: test_scores_in_range")


def test_status_has_reason():
    """Every status has an explanatory reason."""
    state = compute_ability_state("default")
    for aid, astate in state["abilities"].items():
        reason = astate.get("status_reason", "")
        assert len(reason) > 0, f"Empty status_reason for {aid}"
    print("PASS: test_status_has_reason")


def test_single_ability_query():
    """Querying a single ability returns just that ability."""
    state = compute_ability_state("default", ability_id="electrical_safety_check")
    assert "ability_id" in state
    assert state["ability_id"] == "electrical_safety_check"
    assert "status" in state
    print("PASS: test_single_ability_query")


def test_recommendation_has_type():
    """Every recommendation has a valid type."""
    state = compute_ability_state("default")
    valid_types = {"explain", "quiz", "scenario_practice", "cross_scenario",
                   "safety_review", "reflection", "targeted_training", "evidence_building"}
    for aid, astate in state["abilities"].items():
        rec = astate.get("recommended_action", {})
        assert rec.get("type") in valid_types, f"Invalid recommendation type {rec.get('type')} for {aid}"
    print("PASS: test_recommendation_has_type")


def test_improving_without_cross_scenario_recommends_transfer_practice():
    """Improving abilities without cross-scenario validation should recommend transfer practice."""
    rec = _generate_recommendation(
        "plc_input_common_terminal",
        "PLC 输入公共端判断",
        "improving",
        70,
        65,
        20,
        90,
        0.2,
        {"cross_scenario_validated": False},
    )
    assert rec["type"] == "cross_scenario"

    rec_validated = _generate_recommendation(
        "plc_input_common_terminal",
        "PLC 输入公共端判断",
        "improving",
        70,
        65,
        80,
        90,
        0.2,
        {"cross_scenario_validated": True},
    )
    assert rec_validated["type"] == "scenario_practice"
    print("PASS: test_improving_without_cross_scenario_recommends_transfer_practice")


if __name__ == "__main__":
    test_all_abilities_have_complete_structure()
    test_blank_student_returns_unknown()
    test_scores_in_range()
    test_status_has_reason()
    test_single_ability_query()
    test_recommendation_has_type()
    test_improving_without_cross_scenario_recommends_transfer_practice()
    print("\nAll ability_state_engine tests PASSED")
