"""Tests for learning_event_normalizer and learning_event_store - Phase 1."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.learning_event_normalizer import normalize_event, normalize_events
from app.services.learning_event_store import get_events, get_event_timeline, get_ability_events, append_normalized_event


def test_all_event_types_normalize():
    """All known event types normalize correctly."""
    cases = [
        ("chat_message", "chat_question", "knowledge"),
        ("score", "quiz_answered", "knowledge"),
        ("question_explained", "question_explained", "knowledge"),
        ("scenario_started", "scenario_started", "procedure"),
        ("scenario_step_completed", "diagnostic_action", "procedure"),
        ("scenario_step_mistake", "diagnostic_action", "procedure"),
        ("diagnostic_action", "diagnostic_action", "procedure"),
        ("feedback", "feedback_submitted", "meta"),
        ("device_state_recorded", "device_state_recorded", "evidence"),
    ]
    for raw_type, expected_type, expected_cat in cases:
        norm = normalize_event({"event_type": raw_type, "session_id": "test"})
        assert norm is not None, f"Failed to normalize {raw_type}"
        assert norm["event_type"] == expected_type, f"{raw_type} -> {norm['event_type']}, expected {expected_type}"
        assert norm["category"] == expected_cat, f"{raw_type} category={norm['category']}, expected {expected_cat}"
    print("PASS: test_all_event_types_normalize")


def test_polarity_detection():
    """Polarity correctly detected from outcomes."""
    positive = normalize_event({"event_type": "scenario_step_completed", "session_id": "t", "outcome": "optimal"})
    assert positive["polarity"] == "positive"

    negative = normalize_event({"event_type": "scenario_step_mistake", "session_id": "t", "classification": "premature"})
    assert negative["polarity"] == "negative"

    neutral = normalize_event({"event_type": "feedback", "session_id": "t", "feedback": "ok"})
    assert neutral["polarity"] == "neutral"
    print("PASS: test_polarity_detection")


def test_ability_id_extraction():
    """Ability IDs extracted from various formats."""
    e1 = normalize_event({"event_type": "score", "session_id": "t", "ability_ids": ["a1", "a2"]})
    assert e1["ability_ids"] == ["a1", "a2"]

    e2 = normalize_event({"event_type": "scenario_started", "session_id": "t",
                          "ability_hits": [{"id": "elec", "name": "elec"}, {"id": "sensor"}]})
    assert e2["ability_ids"] == ["elec", "sensor"]

    e3 = normalize_event({"event_type": "chat_message", "session_id": "t", "note": "hello"})
    assert e3["ability_ids"] == []
    print("PASS: test_ability_id_extraction")


def test_evidence_weight():
    """Evidence weights vary by source and outcome."""
    e1 = normalize_event({"event_type": "scenario_step_completed", "session_id": "t", "outcome": "optimal"})
    e2 = normalize_event({"event_type": "scenario_step_mistake", "session_id": "t", "classification": "unsafe"})
    assert e1["evidence_weight"] >= e2["evidence_weight"], "Positive should have >= weight than unsafe"
    print("PASS: test_evidence_weight")


def test_event_store_query():
    """Event store can append and query events."""
    sid = "test_phase1_normalizer"
    # Append a few events
    r1 = append_normalized_event(sid, {"event_type": "scenario_step_completed", "session_id": sid,
                                        "ability_ids": ["plc_input_common_terminal"], "outcome": "optimal",
                                        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF"})
    assert r1["saved"]

    r2 = append_normalized_event(sid, {"event_type": "scenario_step_mistake", "session_id": sid,
                                        "ability_ids": ["sensor_wiring_judgement"], "classification": "premature",
                                        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF"})
    assert r2["saved"]

    # Query by ability
    result = get_events(sid, ability_id="plc_input_common_terminal")
    assert result["total"] >= 1

    # Query by scenario
    result = get_events(sid, scenario_id="SCN_SENSOR_LED_ON_PLC_LED_OFF")
    assert result["total"] >= 2

    # Timeline
    timeline = get_event_timeline(sid)
    assert timeline["total_events"] >= 2
    assert "by_type" in timeline["stats"]

    print("PASS: test_event_store_query")


def test_ability_evidence():
    """Ability evidence returns events with score effects."""
    sid = "test_phase1_ability_evidence"
    append_normalized_event(sid, {"event_type": "score", "session_id": sid,
                                   "ability_ids": ["plc_input_common_terminal"], "is_correct": True})
    append_normalized_event(sid, {"event_type": "score", "session_id": sid,
                                   "ability_ids": ["plc_input_common_terminal"], "is_correct": False})

    evidence = get_ability_events(sid, "plc_input_common_terminal")
    assert evidence["event_count"] >= 2
    # Should have both positive and negative effects
    effects = [e["score_effect"] for e in evidence["events"]]
    assert any(e > 0 for e in effects), "Should have positive score effect"
    assert any(e < 0 for e in effects), "Should have negative score effect"
    print("PASS: test_ability_evidence")


def test_idempotent_event_id():
    """Same event content produces same event_id."""
    event = {"event_type": "scenario_step_completed", "session_id": "s1",
             "ability_ids": ["plc_input_common_terminal"], "outcome": "optimal",
             "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "created_at": "2026-07-15T10:00:00"}
    e1 = normalize_event(event)
    e2 = normalize_event(event)
    assert e1["event_id"] == e2["event_id"], "Same input should produce same event_id"
    print("PASS: test_idempotent_event_id")


def test_unknown_event_type():
    """Completely unknown event types return None."""
    norm = normalize_event({"event_type": "completely_unknown_xyz", "session_id": "t"})
    assert norm is None
    print("PASS: test_unknown_event_type")


if __name__ == "__main__":
    test_all_event_types_normalize()
    test_polarity_detection()
    test_ability_id_extraction()
    test_evidence_weight()
    test_event_store_query()
    test_ability_evidence()
    test_idempotent_event_id()
    test_unknown_event_type()
    print("\nAll learning_event_normalizer tests PASSED")
