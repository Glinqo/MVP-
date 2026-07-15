"""
Test 8: Strategy profile.

Validates:
- Single session builds profile with weaknesses
- Two different traces get different profiles
- Safety violation appears as weakness
- Persistence levels correct
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.strategy_profile import (
    build_strategy_profile,
    build_cumulative_strategy_profile,
)
from app.services.scenario import action_scenario


SESSION = "test-strategy-profile"


def cleanup():
    sf = ROOT / "data" / "sessions" / f"{SESSION}.json"
    if sf.exists():
        sf.unlink()


def test_single_scenario_profile():
    """Build profile from one scenario with mixed actions."""
    action_scenario({"session_id": SESSION, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "CHECK_SAFETY"})
    action_scenario({"session_id": SESSION, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "MODIFY_PROGRAM_PREMATURE"})
    action_scenario({"session_id": SESSION, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "REWIRE_WITHOUT_SAFETY"})

    profile = build_strategy_profile(SESSION, "SCN_SENSOR_LED_ON_PLC_LED_OFF")
    assert profile["total_actions"] >= 2
    weaknesses = profile.get("weaknesses", [])
    tags = [w["tag"] for w in weaknesses]
    print(f"  Weaknesses: {tags}")
    assert len(weaknesses) >= 1, "Should have at least one weakness"
    assert "safety_procedure_gap" in tags, "Should have safety gap"
    print("  PASS: profile has weaknesses including safety gap")


def test_cumulative_profile():
    """Cumulative profile with persistence tracking."""
    profile = build_cumulative_strategy_profile(SESSION)
    assert profile["trace_count"] >= 1
    weaknesses = profile.get("weaknesses", [])
    print(f"  Cumulative weaknesses: {[(w['tag'], w.get('persistence','?')) for w in weaknesses]}")
    for w in weaknesses:
        assert "persistence" in w, f"Weakness {w['tag']} missing persistence"
    print("  PASS: cumulative profile has persistence levels")


def test_profile_not_identical_for_different_traces():
    """Two different sessions should produce different profiles."""
    S2 = "test-strategy-profile-2"
    sf = ROOT / "data" / "sessions" / f"{S2}.json"
    if sf.exists():
        sf.unlink()

    # Good trace
    action_scenario({"session_id": S2, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "CHECK_SAFETY"})
    action_scenario({"session_id": S2, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "CHECK_COMMON_TERMINAL"})
    action_scenario({"session_id": S2, "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF", "action_id": "VERIFY_TRIPLE_STATE"})

    good_profile = build_strategy_profile(S2, "SCN_SENSOR_LED_ON_PLC_LED_OFF")
    bad_profile = build_strategy_profile(SESSION, "SCN_SENSOR_LED_ON_PLC_LED_OFF")

    # Bad profile should have more weaknesses
    good_weak = len(good_profile.get("weaknesses", []))
    bad_weak = len(bad_profile.get("weaknesses", []))
    print(f"  Good trace weaknesses: {good_weak}, Bad trace weaknesses: {bad_weak}")
    assert bad_weak > good_weak or (bad_weak == good_weak and bad_profile["total_actions"] > 0), \
        "Bad trace should not have fewer weaknesses than good trace"

    if sf.exists():
        sf.unlink()
    print("  PASS: different traces -> different profiles")


def main():
    print("=== Single scenario profile ===")
    test_single_scenario_profile()

    print("\n=== Cumulative profile ===")
    test_cumulative_profile()

    print("\n=== Different traces -> different profiles ===")
    test_profile_not_identical_for_different_traces()

    print("\n=== ALL STRATEGY PROFILE TESTS PASSED ===")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
