# -*- coding: utf-8 -*-
"""L2 Policy Eval Runner - executes policy cases against ConversationPolicy."""
import json, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.conversation_policy import decide_next_actions
from app.services.conversation_state import (
    get_or_create_conversation_state, append_user_message, clear_conversation_state
)
from app.services.conversation_task import get_active_task, start_task, clear_active_task
from evals.scorers.policy_scorer import score_policy, compute_policy_metrics

CASES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cases")

def load_cases(filename):
    path = os.path.join(CASES_DIR, filename)
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases

def run_policy_case(case):
    """Run a single policy eval case."""
    session_id = f"eval-policy-{case['id']}"
    clear_conversation_state(session_id)
    get_or_create_conversation_state(session_id)

    # Setup state if provided
    state = case.get("state", {})
    if state.get("active_task"):
        at = state["active_task"]
        start_task(session_id, at.get("type", "diagnosis"), at.get("topic", ""))

    message = case.get("message", "")
    append_user_message(session_id, message)

    # Get policy decision
    policy = decide_next_actions(message, session_id)
    actions = policy.get("actions", [])
    tools = [a.get("tool", "") for a in actions]
    preserve_task = policy.get("preserve_active_task", True)

    actual = {
        "tools": tools,
        "preserve_active_task": preserve_task,
        "mode": policy.get("mode", ""),
    }

    result = score_policy(case.get("expect", {}), actual)
    result["case_id"] = case["id"]
    result["category"] = case.get("category", "")
    result["actual_tools"] = tools
    result["policy_mode"] = policy.get("mode", "")

    clear_conversation_state(session_id)
    return result

def run_all_policy_evals():
    """Run all policy eval cases."""
    cases = load_cases("policy.jsonl")
    results = []
    start_time = time.time()

    for case in cases:
        result = run_policy_case(case)
        results.append(result)

    elapsed = time.time() - start_time
    metrics = compute_policy_metrics(results)

    report = {
        "layer": "L2",
        "name": "Conversation Policy",
        "total_cases": len(results),
        "elapsed_ms": elapsed * 1000,
        "metrics": metrics,
        "cases": results,
    }
    return report

if __name__ == "__main__":
    report = run_all_policy_evals()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    m = report["metrics"]
    if m["failed"] > 0:
        print(f"\nFAIL: {m['failed']} policy cases failed", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nPASS: all {m['total_cases']} policy cases passed")

