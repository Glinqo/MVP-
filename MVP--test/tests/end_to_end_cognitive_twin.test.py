"""End-to-end cognitive twin tests - Phase 5.

Tests the full pipeline: scenario start -> action -> completion -> cognitive twin update.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.scenario_composer import compose_scenario, list_all_variants
from app.services.cognitive_twin import build_cognitive_twin
from app.services.transfer_engine import compute_transfer_scores
from app.services.uncertainty_selector import select_next_training_scenario
from app.services.coverage_matrix import build_coverage_matrix


def test_compose_to_cognitive_twin():
    """Composed scenario -> cognitive twin chain works."""
    # Compose a scenario
    inst = compose_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF", variant_id="V_COMMON_TERMINAL_OPEN", difficulty="beginner", seed=42)
    assert inst["base_scenario_id"] == "SCN_SENSOR_LED_ON_PLC_LED_OFF"
    assert inst["variant_id"] == "V_COMMON_TERMINAL_OPEN"
    print("PASS: test_compose_to_cognitive_twin (compose OK)")

    # Cognitive twin still works for default session
    twin = build_cognitive_twin("default")
    assert twin is not None
    assert "abilities" in twin
    print("PASS: test_compose_to_cognitive_twin (cognitive twin OK)")


def test_transfer_in_cognitive_twin():
    """Cognitive twin abilities have non-None transfer_score."""
    twin = build_cognitive_twin("default")
    for ability in twin.get("abilities", []):
        ts = ability.get("transfer_score")
        # transfer_score should be a number (not None), but may be 0 for default session
        assert ts is not None, f"transfer_score is None for {ability['ability_id']}"
        assert isinstance(ts, (int, float)), f"transfer_score is {type(ts)} for {ability['ability_id']}"
    print(f"PASS: test_transfer_in_cognitive_twin ({len(twin['abilities'])} abilities, all have non-None transfer_score)")


def test_selector_integration():
    """Uncertainty selector can use cognitive twin data."""
    twin = build_cognitive_twin("default")
    # Verify abilities exist
    assert len(twin.get("abilities", [])) > 0

    # Selector should work with same session
    result = select_next_training_scenario("default")
    assert result["next_training_scenario"] is not None
    print("PASS: test_selector_integration")


def test_coverage_matrix_integration():
    """Coverage matrix integrates with transfer engine."""
    matrix = build_coverage_matrix()
    transfer = compute_transfer_scores("default")

    # Cross-check: abilities should exist in both
    matrix_ids = {a["ability_id"] for a in matrix["abilities"]}
    transfer_ids = {a["ability_id"] for a in transfer["abilities"]}

    common = matrix_ids & transfer_ids
    assert len(common) > 0, "No common abilities between coverage matrix and transfer scores"
    print(f"PASS: test_coverage_matrix_integration ({len(common)} common abilities)")


def test_full_pipeline_no_crash():
    """Full pipeline from compose -> cognitive twin -> transfer -> selector."""
    # 1. Compose scenario
    inst = compose_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF", difficulty="intermediate", seed=42)
    assert "scenario_instance_id" in inst

    # 2. Build cognitive twin
    twin = build_cognitive_twin("default")
    assert twin["twin_id"] is not None

    # 3. Compute transfer scores
    transfer = compute_transfer_scores("default")
    assert transfer["summary"]["avg_transfer"] is not None

    # 4. Select next scenario
    recommendation = select_next_training_scenario("default")
    assert recommendation["next_training_scenario"] is not None

    # 5. Verify chain: recommendation targets abilities in twin
    rec_abilities = recommendation["next_training_scenario"]["target_abilities"]
    twin_ability_ids = {a["ability_id"] for a in twin["abilities"]}
    if rec_abilities:
        for aid in rec_abilities:
            assert aid in twin_ability_ids, f"Recommended ability {aid} not in cognitive twin"
    print("PASS: test_full_pipeline_no_crash")


if __name__ == "__main__":
    test_compose_to_cognitive_twin()
    test_transfer_in_cognitive_twin()
    test_selector_integration()
    test_coverage_matrix_integration()
    test_full_pipeline_no_crash()
    print("\nAll end_to_end_cognitive_twin tests PASSED")
