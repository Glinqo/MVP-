"""
Test 7: Process metrics calculation.

Validates all 5 process metrics produce reasonable values.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.process_metrics import (
    compute_safety_compliance,
    compute_evidence_quality,
    compute_fault_localization,
    compute_diagnostic_efficiency,
    compute_closure_verification,
    compute_all_metrics,
)


def test_safety_perfect():
    activities = [
        {"action_id": "CHECK_SAFETY", "classification": "optimal"},
        {"action_id": "CHECK_COMMON_TERMINAL", "classification": "optimal"},
        {"action_id": "VERIFY_TRIPLE_STATE", "classification": "optimal"},
    ]
    score = compute_safety_compliance(activities)
    assert score == 1.0, f"Expected 1.0, got {score}"
    print("  PASS: perfect safety -> 1.0")


def test_safety_skipped():
    activities = [
        {"action_id": "CHECK_COMMON_TERMINAL", "classification": "valid"},
        # Safety NOT done first
    ]
    score = compute_safety_compliance(activities)
    assert score <= 0.3, f"Expected <=0.3, got {score}"
    print(f"  PASS: skipped safety -> {score}")


def test_safety_unsafe():
    activities = [
        {"action_id": "REWIRE_WITHOUT_SAFETY", "classification": "unsafe"},
    ]
    score = compute_safety_compliance(activities)
    assert score == 0.0, f"Expected 0.0 for unsafe, got {score}"
    print("  PASS: unsafe action -> 0.0")


def test_evidence_quality():
    # Good: has evidence, no premature
    good = [
        {"action_id": "CHECK_SAFETY", "classification": "optimal"},
        {"action_id": "CHECK_COMMON_TERMINAL", "classification": "optimal"},
        {"action_id": "CHECK_WIRING", "classification": "valid"},
    ]
    score = compute_evidence_quality(good)
    assert score >= 0.5, f"Good evidence score {score} should be >= 0.5"
    print(f"  PASS: good evidence -> {score}")

    # Bad: premature program check
    bad = [
        {"action_id": "MODIFY_PROGRAM_PREMATURE", "classification": "premature"},
        {"action_id": "REPLACE_MODULE_NO_EVIDENCE", "classification": "unsupported_hypothesis"},
    ]
    score = compute_evidence_quality(bad)
    assert score < 0.5, f"Bad evidence score {score} should be < 0.5"
    print(f"  PASS: bad evidence -> {score}")


def test_fault_localization():
    optimal = [
        {"action_id": "CHECK_SAFETY", "classification": "optimal"},
        {"action_id": "CHECK_COMMON_TERMINAL", "classification": "optimal"},
        {"action_id": "CHECK_WIRING", "classification": "valid"},
        {"action_id": "VERIFY_TRIPLE_STATE", "classification": "optimal"},
    ]
    score = compute_fault_localization(optimal)
    assert score >= 0.5, f"Good localization {score} should be >= 0.5"
    print(f"  PASS: following signal chain -> {score}")

    jump = [
        {"action_id": "MODIFY_PROGRAM_PREMATURE", "classification": "premature"},
    ]
    score = compute_fault_localization(jump)
    assert score <= 0.5, f"Jump localization {score} should be <= 0.5"
    print(f"  PASS: program jump -> {score}")


def test_efficiency():
    optimal = [
        {"action_id": "CHECK_SAFETY", "classification": "optimal"},
        {"action_id": "CHECK_COMMON_TERMINAL", "classification": "optimal"},
        {"action_id": "VERIFY_TRIPLE_STATE", "classification": "optimal"},
    ]
    score = compute_diagnostic_efficiency(optimal)
    assert score >= 0.9, f"Optimal efficiency {score} should be >= 0.9"
    print(f"  PASS: optimal efficiency -> {score}")

    repeated = [
        {"action_id": "CHECK_SAFETY", "classification": "optimal"},
        {"action_id": "CHECK_SAFETY", "classification": "repeated_low_value"},
        {"action_id": "CHECK_SAFETY", "classification": "repeated_low_value"},
    ]
    score = compute_diagnostic_efficiency(repeated)
    assert score < 0.8, f"Repeated efficiency {score} should be < 0.8"
    print(f"  PASS: repeated actions -> {score}")


def test_closure():
    with_closure = [
        {"action_id": "CHECK_SAFETY", "classification": "optimal"},
        {"action_id": "CHECK_COMMON_TERMINAL", "classification": "optimal"},
        {"action_id": "VERIFY_TRIPLE_STATE", "classification": "optimal"},
    ]
    score = compute_closure_verification(with_closure)
    assert score >= 0.5, f"With closure {score} should be >= 0.5"
    print(f"  PASS: with closure -> {score}")

    without_closure = [
        {"action_id": "CHECK_SAFETY", "classification": "optimal"},
        {"action_id": "CHECK_COMMON_TERMINAL", "classification": "optimal"},
    ]
    score = compute_closure_verification(without_closure)
    assert score < 0.5, f"Without closure {score} should be < 0.5"
    print(f"  PASS: without closure -> {score}")


def test_all_metrics_range():
    """All metrics should be in 0.0-1.0 range."""
    activities = [
        {"action_id": "CHECK_SAFETY", "classification": "optimal"},
        {"action_id": "CHECK_COMMON_TERMINAL", "classification": "optimal"},
        {"action_id": "CHECK_WIRING", "classification": "valid"},
        {"action_id": "VERIFY_TRIPLE_STATE", "classification": "optimal"},
    ]
    scores = {
        "safety": compute_safety_compliance(activities),
        "evidence": compute_evidence_quality(activities),
        "localization": compute_fault_localization(activities),
        "efficiency": compute_diagnostic_efficiency(activities),
        "closure": compute_closure_verification(activities),
    }
    for name, score in scores.items():
        assert 0.0 <= score <= 1.0, f"{name} = {score} out of range"
    print(f"  PASS: all metrics in [0,1]: {scores}")


def main():
    print("=== Safety ===")
    test_safety_perfect()
    test_safety_skipped()
    test_safety_unsafe()

    print("\n=== Evidence quality ===")
    test_evidence_quality()

    print("\n=== Fault localization ===")
    test_fault_localization()

    print("\n=== Efficiency ===")
    test_efficiency()

    print("\n=== Closure ===")
    test_closure()

    print("\n=== Range check ===")
    test_all_metrics_range()

    print("\n=== ALL PROCESS METRICS TESTS PASSED ===")


if __name__ == "__main__":
    main()
