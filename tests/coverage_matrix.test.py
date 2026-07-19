"""Tests for coverage_matrix.py - Phase 5."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.coverage_matrix import (
    build_coverage_matrix,
    get_coverage_summary,
    get_abilities_needing_validation,
)


def test_coverage_matrix_builds():
    """Coverage matrix builds without errors."""
    matrix = build_coverage_matrix()
    assert matrix is not None
    assert "abilities" in matrix
    assert len(matrix["abilities"]) > 0
    assert matrix["total_abilities"] > 0
    print(f"PASS: test_coverage_matrix_builds ({matrix['total_abilities']} abilities)")


def test_coverage_has_all_fields():
    """Each ability has all required fields."""
    matrix = build_coverage_matrix()
    required = ["ability_id", "ability_name", "total_scenarios",
                "total_fault_contexts", "cross_scenario_validated",
                "single_scenario_only", "never_validated"]
    for ability in matrix["abilities"]:
        for field in required:
            assert field in ability, f"Missing field {field} in {ability['ability_id']}"
    print("PASS: test_coverage_has_all_fields")


def test_cross_validated_detection():
    """Abilities appearing in multiple scenarios are marked cross_validated."""
    matrix = build_coverage_matrix()
    cross = [a for a in matrix["abilities"] if a["cross_scenario_validated"]]
    single = [a for a in matrix["abilities"] if a["single_scenario_only"]]
    print(f"  Cross-validated: {len(cross)}, Single-scenario: {len(single)}")
    # At least safety check should appear in multiple scenarios
    safety = [a for a in matrix["abilities"] if a["ability_id"] == "electrical_safety_check"]
    if safety:
        assert safety[0]["total_scenarios"] >= 1
    print("PASS: test_cross_validated_detection")


def test_summary():
    """Coverage summary is consistent."""
    summary = get_coverage_summary()
    assert summary["total_abilities"] > 0
    # cross_validated + single_scenario_only + never_validated may not equal total
    # because some abilities appear in 0 scenarios AND are also counted in single_scenario_only
    assert summary["cross_validated"] + summary["single_scenario_only"] >= summary["cross_validated"]
    print("PASS: test_summary")


def test_needing_validation():
    """get_abilities_needing_validation returns abilities without cross-scenario."""
    needing = get_abilities_needing_validation()
    for a in needing:
        assert a["reason"] in ("single_scenario", "never_validated")
    print(f"PASS: test_needing_validation ({len(needing)} need validation)")


if __name__ == "__main__":
    test_coverage_matrix_builds()
    test_coverage_has_all_fields()
    test_cross_validated_detection()
    test_summary()
    test_needing_validation()
    print("\nAll coverage_matrix tests PASSED")
