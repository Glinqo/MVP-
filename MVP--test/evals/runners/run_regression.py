# -*- coding: utf-8 -*-
"""Regression Runner - runs all eval layers and produces unified report."""
import json, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from evals.runners.run_state_eval import run_all_state_evals
from evals.runners.run_policy_eval import run_all_policy_evals
from evals.runners.run_multiturn_eval import run_all_multiturn_evals
from evals.runners.run_grounding_eval import run_all_grounding_evals
from evals.runners.run_latency_eval import run_latency_benchmark
from evals.runners.run_e2e_eval import run_all_e2e_evals

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

# Hard regression gates: failures in these layers block merge
HARD_GATES = {
    "L1": {"max_failed_cases": 0},   # State must be perfect
    "L2": {"max_failed_cases": 2},   # Policy allows up to 2 failures
    "L3": {"max_failed_cases": 1},   # Multi-turn allows 1 failure
}

def run_full():
    """Run all eval layers and produce report."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    print("=" * 60)
    print("Phase 6 Full Eval Suite")
    print("=" * 60)

    layers = {}
    total_start = time.time()

    # L1: State
    print("\n[L1] State Correctness...")
    layers["L1"] = run_all_state_evals()
    _print_layer(layers["L1"])

    # L2: Policy
    print("\n[L2] Conversation Policy...")
    layers["L2"] = run_all_policy_evals()
    _print_layer(layers["L2"])

    # L3: Multi-turn
    print("\n[L3] Multi-turn Continuity...")
    layers["L3"] = run_all_multiturn_evals()
    _print_layer(layers["L3"])

    # L5: Grounding + Safety
    print("\n[L5] Grounding & Safety...")
    layers["L5"] = run_all_grounding_evals()
    _print_layer(layers["L5"])

    # L6: Performance
    print("\n[L6] Performance Baseline...")
    layers["L6"] = run_latency_benchmark()
    for cat, perf in layers["L6"].get("results", {}).items():
        print(f"  {cat}: {perf['avg_ms']}ms avg, {perf['avg_llm_calls']} LLM calls")

    # L7: End-to-End Task Success
    print("\n[L7] End-to-End Task Success...")
    layers["L7"] = run_all_e2e_evals()
    _print_layer(layers["L7"])
    m7 = layers["L7"].get("metrics", {})
    print(f"  Task Success: {m7.get('task_success_rate',0):.1%}, Avg Diag Level: {m7.get('avg_diagnosis_level',0)}, Actionable: {m7.get('actionable_rate',0):.1%}")

    total_elapsed = time.time() - total_start

    # Check hard gates
    gate_failures = []
    for layer, gate in HARD_GATES.items():
        if layer in layers:
            if "min_task_success_rate" in gate:
                tsr = layers.get(layer, {}).get("metrics", {}).get("task_success_rate", 0)
                if tsr < gate["min_task_success_rate"]:
                    gate_failures.append(f"{layer}: {tsr:.1%} < {gate['min_task_success_rate']:.1%}")
                continue
            if "max_avg_ms_per_turn" in gate:
                max_ms = 0
                for cat, perf in layers.get(layer, {}).get("results", {}).items():
                    max_ms = max(max_ms, perf.get("avg_ms", 0))
                if max_ms > gate["max_avg_ms_per_turn"]:
                    gate_failures.append(f"{layer}: {max_ms}ms > {gate['max_avg_ms_per_turn']}ms")
                continue
            failed = layers[layer].get("failed_cases", 0)
            if failed > gate["max_failed_cases"]:
                gate_failures.append(f"{layer}: {failed} > {gate['max_failed_cases']}")

    # Build final report
    report = {
        "title": "Phase 6 Eval Report",
        "timestamp": timestamp,
        "total_elapsed_ms": total_elapsed * 1000,
        "layers": layers,
        "hard_gates": {
            "passed": len(gate_failures) == 0,
            "failures": gate_failures,
        },
        "summary": {
            "total_cases": sum(l.get("total_cases", 0) for l in layers.values()),
            "total_passed": sum(l.get("passed_cases", 0) for l in layers.values()),
            "total_failed": sum(l.get("failed_cases", 0) for l in layers.values()),
        },
    }

    # Write report
    report_path = os.path.join(REPORTS_DIR, f"eval_{timestamp}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Also write latest symlink-style marker
    latest_path = os.path.join(REPORTS_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"Report saved: {report_path}")
    print(f"Summary: {report['summary']['total_passed']}/{report['summary']['total_cases']} passed")
    print(f"Hard gates: {'PASS' if report['hard_gates']['passed'] else 'FAIL'}")
    if gate_failures:
        for gf in gate_failures:
            print(f"  GATE FAILURE: {gf}")
    print("=" * 60)

    return report, gate_failures

def _print_layer(layer):
    print(f"  Cases: {layer.get('total_cases',0)}, Passed: {layer.get('passed_cases',0)}, Failed: {layer.get('failed_cases',0)}")
    if "metrics" in layer:
        m = layer["metrics"]
        print(f"  Recall: {m.get('avg_tool_recall',0):.1%}, Forbidden: {m.get('avg_forbidden_rate',0):.1%}, TaskPreserve: {m.get('avg_task_preservation',0):.1%}")
    if layer.get("accuracy"):
        print(f"  Accuracy: {layer['accuracy']:.1%}")

def run_quick():
    """Quick eval: L1 only (fast path for pre-commit)."""
    print("[QUICK] L1 State Correctness only")
    report = run_all_state_evals()
    print(f"  {report['passed_cases']}/{report['total_cases']} passed")
    return report

def compare_baseline(current, baseline_path):
    """Compare current results against a stored baseline."""
    if not os.path.exists(baseline_path):
        return {"error": "Baseline not found: " + baseline_path}
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)
    
    changes = []
    for layer in ["L1", "L2", "L3"]:
        if layer in current.get("layers", {}) and layer in baseline.get("layers", {}):
            cur = current["layers"][layer]
            base = baseline["layers"][layer]
            cur_pass = cur.get("passed_cases", 0)
            base_pass = base.get("passed_cases", 0)
            cur_total = cur.get("total_cases", 1)
            base_total = base.get("total_cases", 1)
            
            if cur_total != base_total:
                changes.append(f"{layer}: cases {base_total} -> {cur_total}")
            if cur_pass != base_pass:
                direction = "UP" if cur_pass > base_pass else "DOWN"
                changes.append(f"{layer}: passed {base_pass} -> {cur_pass} ({direction})")
            
            # Check metrics
            if "metrics" in cur and "metrics" in base:
                for mk in ["avg_tool_recall", "avg_task_preservation"]:
                    if abs(cur["metrics"].get(mk, 0) - base["metrics"].get(mk, 0)) > 0.001:
                        changes.append(f"{layer}.{mk}: {base['metrics'].get(mk,0):.1%} -> {cur['metrics'].get(mk,0):.1%}")
    
    return {"baseline_version": baseline.get("version", "unknown"), "changes": changes, "regression_detected": any("DOWN" in c for c in changes)}

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true", help="Quick eval (L1 only)")
    p.add_argument("--baseline", type=str, help="Path to baseline JSON for comparison")
    args = p.parse_args()

    if args.quick:
        report = run_quick()
        if report.get("failed_cases", 0) > 0:
            sys.exit(1)
    else:
        report, gate_failures = run_full()
        if args.baseline:
            comp = compare_baseline(report, args.baseline)
            print("\nBaseline comparison (" + comp.get("baseline_version", "?") + "):")
            for c in comp.get("changes", []):
                print("  " + c)
            if comp.get("regression_detected"):
                print("REGRESSION DETECTED!")
        if gate_failures:
            sys.exit(1)

