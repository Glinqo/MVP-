# -*- coding: utf-8 -*-
"""L2 Policy Scorer - tool selection accuracy."""
import json

def score_policy(expected, actual):
    """Score policy tool selection.
    Returns exact match, recall, forbidden tool rate, task preservation.
    """
    results = {"passed": [], "failed": [], "metrics": {}}

    exp_tools = set(expected.get("tools", []))
    act_tools = set(actual.get("tools", []))
    forbidden_tools = set(expected.get("forbidden_tools", []))

    # Exact tool match
    if exp_tools == act_tools:
        results["passed"].append("exact_tool_match")
    else:
        results["failed"].append(f"tool_mismatch: expected={exp_tools} got={act_tools}")

    # Required tool recall
    if exp_tools:
        recall = len(exp_tools & act_tools) / len(exp_tools)
        results["metrics"]["required_tool_recall"] = recall
        if recall == 1.0:
            results["passed"].append("full_tool_recall")
        else:
            missing = exp_tools - act_tools
            results["failed"].append(f"missing_tools: {missing}")
    else:
        results["metrics"]["required_tool_recall"] = 1.0

    # Forbidden tool rate
    forbidden_hit = forbidden_tools & act_tools
    results["metrics"]["forbidden_tool_rate"] = len(forbidden_hit) / max(len(forbidden_tools), 1)
    if forbidden_hit:
        results["failed"].append(f"forbidden_tools_used: {forbidden_hit}")
    else:
        results["passed"].append("no_forbidden_tools")

    # ActiveTask preservation
    if "preserve_active_task" in expected:
        act_preserve = actual.get("preserve_active_task", True)
        results["metrics"]["task_preservation"] = 1.0 if act_preserve == expected["preserve_active_task"] else 0.0
        if act_preserve == expected["preserve_active_task"]:
            results["passed"].append(f"task_preserved={act_preserve}")
        else:
            results["failed"].append(f"task_preservation expected={expected['preserve_active_task']} got={act_preserve}")

    # Tools include safety
    if expected.get("tools_include_safety"):
        has_safety = any("safety" in t.lower() for t in act_tools)
        results["metrics"]["tools_include_safety"] = 1.0 if has_safety else 0.0
        if has_safety:
            results["passed"].append("safety_tool_included")
        else:
            results["failed"].append("safety_tool_missing")

    # Compute overall score
    total = len(results["passed"]) + len(results["failed"])
    results["score"] = len(results["passed"]) / max(total, 1)
    return results


def compute_policy_metrics(all_results):
    """Aggregate metrics across all policy eval cases."""
    agg = {"total_cases": len(all_results), "passed": 0, "failed": 0,
           "exact_tool_match": 0, "tool_recall_sum": 0.0,
           "forbidden_tool_rate_sum": 0.0, "task_preservation_sum": 0.0}
    for r in all_results:
        if r.get("failed"):
            agg["failed"] += 1
        else:
            agg["passed"] += 1
        m = r.get("metrics", {})
        agg["tool_recall_sum"] += m.get("required_tool_recall", 1.0)
        agg["forbidden_tool_rate_sum"] += m.get("forbidden_tool_rate", 0.0)
        agg["task_preservation_sum"] += m.get("task_preservation", 1.0)
        if m.get("required_tool_recall", 1.0) >= 1.0:
            agg["exact_tool_match"] += 1
    n = max(agg["total_cases"], 1)
    agg["avg_tool_recall"] = agg["tool_recall_sum"] / n
    agg["avg_forbidden_rate"] = agg["forbidden_tool_rate_sum"] / n
    agg["avg_task_preservation"] = agg["task_preservation_sum"] / n
    agg["exact_tool_match_rate"] = agg["exact_tool_match"] / n
    return agg

