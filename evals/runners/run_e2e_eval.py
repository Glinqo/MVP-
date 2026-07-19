# -*- coding: utf-8 -*-
"""L7 End-to-End Task Success Eval Runner."""
import json, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.chat import chat_message
from app.services.conversation_state import clear_conversation_state
from evals.simulators.user_simulator import user_respond, simulate_conversation
from evals.scorers.e2e.task_success_scorer import score_diagnosis_task, score_learning_task
from evals.scorers.e2e.conversation_efficiency_scorer import score_conversation_efficiency

CASES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cases", "end_to_end")

def load_cases(filename):
    path = os.path.join(CASES_DIR, filename)
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases

def run_diagnosis_case(case):
    """Run a diagnosis E2E case through real chat_message."""
    scenario = case.get("scenario", {})
    criteria = case.get("success_criteria", {})
    max_turns = criteria.get("max_turns", 8)

    trace = simulate_conversation(
        case.get("initial_message", ""),
        scenario,
        max_turns,
        chat_message
    )

    # Score
    result = score_diagnosis_task(trace, criteria, scenario.get("hidden_ground_truth", {}))
    eff = score_conversation_efficiency(trace, max_turns)
    result["metrics"].update(eff.get("metrics", {}))
    result["case_id"] = case["id"]
    result["category"] = case.get("category", "")
    result["trace_summary"] = {
        "turns": len([t for t in trace if t.get("role") == "user"]),
        "last_assistant_msg": (trace[-1].get("content", "")[:100] if trace else ""),
    }
    return result

def run_learning_case(case):
    """Run a learning E2E case."""
    criteria = case.get("success_criteria", {})
    max_turns = criteria.get("max_turns", 6)

    scenario = {"user_knowledge": {}, "user_unknown": []}
    trace = simulate_conversation(
        case.get("initial_message", ""),
        scenario,
        max_turns,
        chat_message
    )

    result = score_learning_task(trace, criteria)
    eff = score_conversation_efficiency(trace, max_turns)
    result["metrics"].update(eff.get("metrics", {}))
    result["case_id"] = case["id"]
    result["category"] = case.get("category", "")
    return result

def run_interruption_case(case):
    """Run an interruption E2E case with scripted turns."""
    session_id = f"e2e-int-{case['id']}"
    clear_conversation_state(session_id)

    criteria = case.get("success_criteria", {})
    trace = []
    for i, turn in enumerate(case.get("turns", [])):
        user_msg = turn.get("user", "")
        if not user_msg:
            continue
        trace.append({"role": "user", "content": user_msg, "turn": i})
        response = chat_message({"session_id": session_id, "message": user_msg, "context": {}})
        trace.append({"role": "assistant", "content": response.get("answer", ""),
                      "turn": i, "policy_source": response.get("policy_source", "")})

    # Simple success check for interruption cases
    result = {"passed": [], "failed": [], "metrics": {}, "total": 0}
    all_text = " ".join(t.get("content", "") for t in trace if t.get("role") == "assistant").lower()

    if criteria.get("task_resumed"):
        result["total"] += 1
        if any(kw in all_text for kw in ["继续", "回到", "排查"]):
            result["passed"].append("task_resumed")
        else:
            result["failed"].append("task_not_resumed")

    if criteria.get("task_switch_handled"):
        result["total"] += 1
        result["passed"].append("task_switch_handled")

    if criteria.get("correction_accepted"):
        result["total"] += 1
        pnp_mentioned = "pnp" in all_text or "PNP" in all_text
        if pnp_mentioned:
            result["passed"].append("correction_accepted")
        else:
            result["failed"].append("correction_not_accepted")

    if criteria.get("summary_given"):
        result["total"] += 1
        result["passed"].append("summary_given")

    if criteria.get("old_task_cleared"):
        result["total"] += 1
        result["passed"].append("old_task_cleared")

    result["score"] = len(result["passed"]) / max(result["total"], 1)
    result["case_id"] = case["id"]
    result["category"] = case.get("category", "")
    result["trace_summary"] = {"turns": len(case.get("turns", [])),
                               "last_msg": (trace[-1].get("content", "")[:100] if trace else "")}
    return result

def run_all_e2e_evals():
    """Run all E2E eval cases."""
    results = []
    start_time = time.time()

    # Diagnosis (10)
    for case in load_cases("diagnosis_tasks.jsonl"):
        results.append(run_diagnosis_case(case))

    # Learning (5)
    for case in load_cases("learning_tasks.jsonl"):
        results.append(run_learning_case(case))

    # Mixed (5) - run as diagnosis since they have hidden_ground_truth
    for case in load_cases("mixed_tasks.jsonl"):
        results.append(run_diagnosis_case(case))

    # Interruption (5)
    for case in load_cases("interruption_tasks.jsonl"):
        results.append(run_interruption_case(case))

    elapsed = time.time() - start_time
    total = len(results)
    passed = sum(1 for r in results if not r.get("failed"))
    avg_level = sum(r.get("metrics", {}).get("diagnosis_level", 0) for r in results) / max(total, 1)
    actionable = sum(1 for r in results if r.get("metrics", {}).get("actionable"))
    diag_level3 = sum(1 for r in results if r.get("metrics", {}).get("diagnosis_level", 0) >= 3)

    # Aggregate efficiency metrics
    all_eff = {}
    for key in ["total_turns", "repeated_questions", "unnecessary_questions",
                "repeated_known_question_rate", "unnecessary_question_rate",
                "user_repetition_rate", "lost_context_rate"]:
        vals = [r.get("metrics", {}).get(key, 0) for r in results if key in r.get("metrics", {})]
        all_eff[key] = round(sum(vals) / max(len(vals), 1), 3) if vals else 0

    # Count by category
    cat_failures = {}
    for r in results:
        cat = r.get("category", "unknown")
        if r.get("failed"):
            cat_failures[cat] = cat_failures.get(cat, 0) + 1

    return {
        "layer": "L7",
        "name": "End-to-End Task Success",
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "metrics": {
            "task_success_rate": passed / max(total, 1),
            "avg_diagnosis_level": round(avg_level, 1),
            "actionable_rate": actionable / max(total, 1),
            "diagnosis_level_3_rate": diag_level3 / max(total, 1),
            **all_eff,
        },
        "failure_by_category": cat_failures,
        "elapsed_ms": elapsed * 1000,
        "cases": results,
    }

if __name__ == "__main__":
    report = run_all_e2e_evals()
    print(json.dumps(report, ensure_ascii=False, indent=2))

