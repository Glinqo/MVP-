"""Tests for transfer_engine.py - Phase 5."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.transfer_engine import compute_transfer_scores


def test_transfer_scores_returns_structure():
    """Transfer scores returns correct structure."""
    result = compute_transfer_scores("default")
    assert "session_id" in result
    assert "abilities" in result
    assert "summary" in result
    summary = result["summary"]
    for key in ["avg_knowledge", "avg_procedure", "avg_transfer", "avg_safety"]:
        assert key in summary
    print("PASS: test_transfer_scores_returns_structure")


def test_transfer_scores_per_ability():
    """Each ability has all four scores."""
    result = compute_transfer_scores("default")
    for ability in result["abilities"]:
        assert "knowledge_mastery" in ability
        assert "procedure_mastery" in ability
        assert "transfer_score" in ability
        assert "safety_score" in ability
        assert "cross_scenario_validated" in ability
        # All scores should be 0-100
        for key in ["knowledge_mastery", "procedure_mastery", "transfer_score", "safety_score"]:
            score = ability[key]
            assert 0 <= score <= 100, f"{key} for {ability['ability_id']} = {score}, expected 0-100"
    print("PASS: test_transfer_scores_per_ability")


def test_transfer_score_zero_no_history():
    """Transfer score should be 0 for abilities with no history."""
    result = compute_transfer_scores("default")
    for ability in result["abilities"]:
        if not ability["cross_scenario_validated"]:
            # Transfer should be low (0-30 max for single scenario)
            assert ability["transfer_score"] <= 30, \
                f"Transfer for {ability['ability_id']} = {ability['transfer_score']}, expected <= 30 without cross-scenario evidence"
    print("PASS: test_transfer_score_zero_no_history")


def test_summary_averages_valid():
    """Summary averages are within valid range."""
    result = compute_transfer_scores("default")
    summary = result["summary"]
    for key in ["avg_knowledge", "avg_procedure", "avg_transfer", "avg_safety"]:
        val = summary[key]
        assert 0 <= val <= 100, f"{key} = {val}, expected 0-100"
    print("PASS: test_summary_averages_valid")


def test_same_session_consistent():
    """Same session returns consistent results on repeated calls."""
    result1 = compute_transfer_scores("default")
    result2 = compute_transfer_scores("default")
    assert result1["summary"]["avg_knowledge"] == result2["summary"]["avg_knowledge"]
    assert result1["summary"]["avg_transfer"] == result2["summary"]["avg_transfer"]
    print("PASS: test_same_session_consistent")


if __name__ == "__main__":
    test_transfer_scores_returns_structure()
    test_transfer_scores_per_ability()
    test_transfer_score_zero_no_history()
    test_summary_averages_valid()
    test_same_session_consistent()
    print("\nAll transfer_engine tests PASSED")
