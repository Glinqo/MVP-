"""Tests for scenario_composer.py - Phase 5."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.scenario_composer import (
    compose_scenario,
    validate_scenario_instance,
    list_all_variants,
    get_neighbor_counterexample_pairs,
    list_variants_for_scenario,
)


def test_same_seed_same_instance():
    """Same seed + same scenario + same variant = identical instance."""
    inst1 = compose_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF", variant_id="V_COMMON_TERMINAL_OPEN", difficulty="beginner", seed=42)
    inst2 = compose_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF", variant_id="V_COMMON_TERMINAL_OPEN", difficulty="beginner", seed=42)
    assert inst1["scenario_instance_id"] == inst2["scenario_instance_id"], "Same seed should produce same instance_id"
    assert inst1["visible_facts"] == inst2["visible_facts"], "Same seed should produce same visible_facts"
    assert inst1["hidden_facts"] == inst2["hidden_facts"], "Same seed should produce same hidden_facts"
    print("PASS: test_same_seed_same_instance")


def test_different_seed_no_illegal_state():
    """Different seeds should not produce illegal states."""
    for seed in [1, 2, 3, 42, 99]:
        inst = compose_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF", difficulty="beginner", seed=seed)
        errors = validate_scenario_instance(inst)
        assert not errors, f"Seed {seed} produced errors: {errors}"
        assert inst["base_scenario_id"] == "SCN_SENSOR_LED_ON_PLC_LED_OFF"
        assert inst["difficulty"] == "beginner"
        assert inst["seed"] == seed
    print("PASS: test_different_seed_no_illegal_state")


def test_all_instances_pass_validation():
    """All generated instances pass schema validation."""
    variants_map = list_all_variants()
    for sid, variants in variants_map.items():
        for v in variants[:2]:  # Test first 2 variants each
            for diff in ["beginner", "intermediate", "advanced"]:
                inst = compose_scenario(sid, variant_id=v["id"], difficulty=diff, seed=100)
                errors = validate_scenario_instance(inst)
                assert not errors, f"Validation failed for {sid}/{v['id']}/{diff}: {errors}"
    print("PASS: test_all_instances_pass_validation")


def test_no_contradiction():
    """No contradiction between fault cause and visible facts."""
    inst = compose_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF", variant_id="V_COMMON_TERMINAL_OPEN", difficulty="advanced", seed=42)
    # The root cause should be in possible_hypotheses
    root_causes = [h for h in inst["possible_hypotheses"] if h["is_root_cause"]]
    assert len(root_causes) == 1
    assert root_causes[0]["id"] == "HYP_COMMON_TERMINAL_OPEN"
    # Initial symptom must be in visible facts
    assert inst["visible_facts"]["sensor_led"] == "on"
    assert inst["visible_facts"]["plc_input_led"] == "off"
    print("PASS: test_no_contradiction")


def test_beginner_more_visible_evidence():
    """Beginner difficulty should reveal more evidence than advanced."""
    inst_beginner = compose_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF", variant_id="V_COMMON_TERMINAL_OPEN", difficulty="beginner", seed=42)
    inst_advanced = compose_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF", variant_id="V_COMMON_TERMINAL_OPEN", difficulty="advanced", seed=42)
    assert inst_beginner["count_visible_facts"] >= inst_advanced["count_visible_facts"], \
        f"Beginner ({inst_beginner['count_visible_facts']}) should have >= visible facts than advanced ({inst_advanced['count_visible_facts']})"
    print("PASS: test_beginner_more_visible_evidence")


def test_beginner_no_unsafe_actions():
    """Beginner difficulty should not include unsafe actions."""
    inst = compose_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF", difficulty="beginner", seed=42)
    unsafe_in_allowed = []
    for a in inst["diagnostic_actions"]:
        if a.get("category") in ("unsafe", "invalid") and a["id"] in inst["allowed_actions"]:
            unsafe_in_allowed.append(a["id"])
    assert not unsafe_in_allowed, f"Unsafe actions in beginner: {unsafe_in_allowed}"
    print("PASS: test_beginner_no_unsafe_actions")


def test_neighbor_pairs_config():
    """Neighbor counterexample pairs are properly configured."""
    pairs = get_neighbor_counterexample_pairs()
    assert len(pairs) >= 2, f"Expected at least 2 neighbor pairs, got {len(pairs)}"
    for pair in pairs:
        assert "scenario_a" in pair
        assert "scenario_b" in pair
        assert pair["scenario_a"]["scenario_id"] != pair["scenario_b"]["scenario_id"]
        assert "target_strategy_test" in pair
    print("PASS: test_neighbor_pairs_config")


def test_variant_auto_select():
    """When no variant_id is given, auto-select based on seed."""
    inst = compose_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF", difficulty="intermediate", seed=42)
    assert inst["variant_id"] is not None
    assert inst["variant_id"] in ["V_COMMON_TERMINAL_OPEN", "V_SENSOR_WIRING_WRONG", "V_SENSOR_TYPE_MISMATCH"]
    print("PASS: test_variant_auto_select")


def test_list_variants():
    """list_variants_for_scenario returns correct variants."""
    variants = list_variants_for_scenario("SCN_PLC_LED_ON_MONITOR_OFF")
    assert len(variants) >= 2
    ids = {v["id"] for v in variants}
    assert "V_IO_MAPPING_ERROR" in ids
    assert "V_VARIABLE_MISMATCH" in ids
    print("PASS: test_list_variants")


if __name__ == "__main__":
    test_same_seed_same_instance()
    test_different_seed_no_illegal_state()
    test_all_instances_pass_validation()
    test_no_contradiction()
    test_beginner_more_visible_evidence()
    test_beginner_no_unsafe_actions()
    test_neighbor_pairs_config()
    test_variant_auto_select()
    test_list_variants()
    print("\nAll scenario_composer tests PASSED")
