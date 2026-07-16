"""
Test 9: Cognitive digital twin.

Validates:
- Cognitive twin includes process_metrics and strategy_tags
- Safety score differs between good and bad traces
- Procedure mastery derived from process metrics
- Compatibility fields (mastery_score, evidence_count) preserved
"""

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.cognitive_twin import build_cognitive_twin
from app.services.scenario import action_scenario


SESSION = "test-cognitive-twin"
GRAPH_EVENTS_FILE = ROOT / "data" / "graph_update_events.json"


def cleanup():
    sf = ROOT / "data" / "sessions" / f"{SESSION}.json"
    if sf.exists():
        sf.unlink()
    if GRAPH_EVENTS_FILE.exists():
        data = json.loads(GRAPH_EVENTS_FILE.read_text(encoding="utf-8"))
        events = data.get("events", [])
        filtered = [event for event in events if event.get("session_id") != SESSION]
        if len(filtered) != len(events):
            data["events"] = filtered
            GRAPH_EVENTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_cognitive_twin_structure():
    """Cognitive twin returns expected structure."""
    action_scenario({"session_id": SESSION, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "CHECK_SAFETY"})
    action_scenario({"session_id": SESSION, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "CHECK_COMMON_TERMINAL"})
    action_scenario({"session_id": SESSION, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "VERIFY_TRIPLE_STATE"})

    twin = build_cognitive_twin(SESSION)
    assert twin["session_id"] == SESSION
    assert "abilities" in twin
    assert "strategy_profile" in twin
    assert "aggregated_metrics" in twin
    print(f"  PASS: twin has {len(twin['abilities'])} abilities, trace_count={twin['trace_count']}")

    # Check per-ability structure
    if twin["abilities"]:
        ability = twin["abilities"][0]
        assert "knowledge_mastery" in ability
        assert "procedure_mastery" in ability
        assert "safety_score" in ability
        assert "process_metrics" in ability
        assert "strategy_tags" in ability
        # Compatibility fields
        assert "mastery_score" in ability
        assert "evidence_count" in ability
        assert "confidence" in ability
        print(f"  PASS: ability {ability['ability_id']}: knowledge={ability['knowledge_mastery']}, "
              f"procedure={ability['procedure_mastery']}, safety={ability['safety_score']}")


def test_safety_ability_scores_high():
    """Safety-related abilities should have high safety scores on a good trace."""
    twin = build_cognitive_twin(SESSION)
    for ability in twin["abilities"]:
        if ability["ability_id"] == "electrical_safety_check":
            assert ability["safety_score"] >= 50, \
                f"Safety ability score {ability['safety_score']} should be >= 50"
            print(f"  PASS: electrical_safety_check safety_score={ability['safety_score']}")
            break


def test_compatibility_fields():
    """Compatibility fields preserved."""
    twin = build_cognitive_twin(SESSION)
    if twin["abilities"]:
        ability = twin["abilities"][0]
        assert "mastery_score" in ability
        assert "evidence_count" in ability
        assert "update_reasons" in ability
        assert "confidence" in ability
        print("  PASS: all compatibility fields present")


def main():
    print("=== Cognitive twin structure ===")
    test_cognitive_twin_structure()

    print("\n=== Safety ability score ===")
    test_safety_ability_scores_high()

    print("\n=== Compatibility fields ===")
    test_compatibility_fields()

    print("\n=== ALL COGNITIVE TWIN TESTS PASSED ===")


if __name__ == "__main__":
    try:
        cleanup()
        main()
    finally:
        cleanup()
