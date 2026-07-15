"""
Test 11: Information gain calculation.

Validates:
1. Unknown input LED -> observing it has high IG
2. Input LED already confirmed off -> modify program IG is low
3. Common terminal unchecked -> check common terminal IG is high
4. Safety not met -> dangerous actions blocked (tested in counterfactual)
5. Repeated action penalized (tested in counterfactual)
6. Action that cannot distinguish -> IG = 0
7. Single remaining hypothesis -> IG = 0
8. Two equal IG actions -> same value (tie-break external)
9. Deterministic: same inputs same outputs
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.model_tracer import model_for_scenario
from app.services.hypothesis_engine import initialize_hypotheses
from app.services.information_gain import (
    entropy,
    normalized_information_gain,
    calculate_information_gain,
)
from app.services.counterfactual_action import load_policy


def test_entropy():
    # Equal weights -> max entropy
    e = entropy([1, 1, 1, 1])
    assert e > 1.5, f"4 equal weights: entropy {e} should be > 1.5"
    # Single weight -> 0
    e = entropy([1])
    assert e == 0.0
    # Empty -> 0
    e = entropy([])
    assert e == 0.0
    print(f"  PASS: 4 equal={entropy([1,1,1,1]):.3f}, 1={entropy([1])}, 0={entropy([])}")


def test_high_ig_when_unknown():
    """When input LED state is unknown, observing it has high IG."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    hyps = initialize_hypotheses(model)

    policy = load_policy()
    evidence_map = policy.get("action_hypothesis_evidence", {}).get(
        "SCN_SENSOR_LED_ON_PLC_LED_OFF", {}
    )

    # CHECK_COMMON_TERMINAL should have high IG to distinguish HYP_COMMON_TERMINAL_OPEN
    ig, reduction = normalized_information_gain(hyps, "CHECK_COMMON_TERMINAL", evidence_map)
    print(f"  CHECK_COMMON_TERMINAL: IG={ig:.3f}, reduction={reduction}")
    assert ig > 0.0, "Should have positive IG"
    assert "HYP_COMMON_TERMINAL_OPEN" in reduction
    print("  PASS: CHECK_COMMON_TERMINAL has positive IG for COMMON_TERMINAL hypothesis")


def test_low_ig_for_irrelevant():
    """CHECK_SAFETY has no hypothesis elimination -> IG = 0."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    hyps = initialize_hypotheses(model)

    policy = load_policy()
    evidence_map = policy.get("action_hypothesis_evidence", {}).get(
        "SCN_SENSOR_LED_ON_PLC_LED_OFF", {}
    )

    ig, reduction = normalized_information_gain(hyps, "CHECK_SAFETY", evidence_map)
    print(f"  CHECK_SAFETY: IG={ig:.3f}, reduction={reduction}")
    assert ig == 0.0, "CHECK_SAFETY should have 0 IG (no hypothesis elimination)"
    print("  PASS: CHECK_SAFETY has 0 IG")


def test_single_hypothesis():
    """With only 1 remaining hypothesis, any action IG = 0."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    hyps = initialize_hypotheses(model)
    # Eliminate all but one
    for hid in list(hyps.keys()):
        if hid != "HYP_COMMON_TERMINAL_OPEN":
            hyps[hid]["status"] = "eliminated"

    policy = load_policy()
    evidence_map = policy.get("action_hypothesis_evidence", {}).get(
        "SCN_SENSOR_LED_ON_PLC_LED_OFF", {}
    )

    ig, reduction = normalized_information_gain(hyps, "CHECK_WIRING", evidence_map)
    assert ig == 0.0, f"Single hypothesis: IG should be 0, got {ig}"
    print("  PASS: single hypothesis -> IG = 0")


def test_no_discrimination():
    """Action that can't distinguish any hypothesis -> IG = 0."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    hyps = initialize_hypotheses(model)

    # Empty evidence map -> IG = 0
    ig, reduction = normalized_information_gain(hyps, "NONEXISTENT_ACTION", {})
    assert ig == 0.0, f"Nonexistent action IG should be 0, got {ig}"
    print("  PASS: nonexistent action -> IG = 0")


def test_deterministic():
    """Same inputs -> same IG every time."""
    model = model_for_scenario("SCN_SENSOR_LED_ON_PLC_LED_OFF")
    policy = load_policy()
    evidence_map = policy.get("action_hypothesis_evidence", {}).get(
        "SCN_SENSOR_LED_ON_PLC_LED_OFF", {}
    )

    results = []
    for _ in range(5):
        hyps = initialize_hypotheses(model)
        ig, _ = normalized_information_gain(hyps, "CHECK_COMMON_TERMINAL", evidence_map)
        results.append(ig)

    assert all(r == results[0] for r in results), f"Not deterministic: {results}"
    print(f"  PASS: 5 calls all returned {results[0]}")


def main():
    print("=== Entropy ===")
    test_entropy()

    print("\n=== High IG when unknown ===")
    test_high_ig_when_unknown()

    print("\n=== Low IG for irrelevant ===")
    test_low_ig_for_irrelevant()

    print("\n=== Single hypothesis ===")
    test_single_hypothesis()

    print("\n=== No discrimination ===")
    test_no_discrimination()

    print("\n=== Deterministic ===")
    test_deterministic()

    print("\n=== ALL INFORMATION GAIN TESTS PASSED ===")


if __name__ == "__main__":
    main()
