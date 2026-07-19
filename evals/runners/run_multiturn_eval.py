# -*- coding: utf-8 -*-
"""L3 Multi-turn Eval Runner."""
import json, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.conversation_state import (
    get_or_create_conversation_state, append_user_message, append_assistant_message,
    get_conversation_context, clear_conversation_state
)
from app.services.conversation_slots import extract_slots_from_message
from app.services.conversation_task import get_task_slots, set_task_slots
from evals.scorers.answer_scorer import detect_repeated_questions, detect_message_duplication

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

def run_multiturn_case(case):
    """Run a multi-turn case and check continuity."""
    session_id = f"eval-multi-{case['id']}"
    clear_conversation_state(session_id)
    get_or_create_conversation_state(session_id)

    messages = []
    for turn in case.get("turns", []):
        user_msg = turn.get("user", "")
        asst_msg = turn.get("assistant", "")
        if user_msg:
            append_user_message(session_id, user_msg)
            messages.append({"role": "user", "content": user_msg})
            slots = extract_slots_from_message(user_msg)
            if slots:
                ts = get_task_slots(session_id)
                ts.update(slots)
                set_task_slots(session_id, ts)
        if asst_msg:
            append_assistant_message(session_id, asst_msg)
            messages.append({"role": "assistant", "content": asst_msg})

    # Check repeated questions in history
    history = get_conversation_context(session_id, limit=20)
    repeat_result = detect_repeated_questions(history)
    dupe_result = detect_message_duplication(messages)

    # Check context retention
    expected = case.get("expect", {})
    passed = []
    failed = []

    if expected.get("repeated_question") is True:
        if repeat_result["repeated_question"]:
            passed.append("repeated_question_detected")
        else:
            failed.append("repeated_question_not_detected")

    if expected.get("no_lost_context"):
        ts = get_task_slots(session_id)
        for key in expected.get("context_retained", []):
            if key in ts:
                passed.append(f"context_retained:{key}")
            else:
                failed.append(f"context_lost:{key}")

    total = len(passed) + len(failed)
    return {
        "case_id": case["id"],
        "category": case.get("category", ""),
        "passed": passed,
        "failed": failed,
        "score": len(passed) / max(total, 1),
        "total": total,
        "repeated_questions": repeat_result["count"],
        "has_duplicates": dupe_result["has_duplicates"],
    }

def run_all_multiturn_evals():
    cases = load_cases("multiturn.jsonl")
    results = []
    start_time = time.time()

    for case in cases:
        result = run_multiturn_case(case)
        results.append(result)

    elapsed = time.time() - start_time
    total = len(results)
    passed = sum(1 for r in results if not r.get("failed"))

    return {
        "layer": "L3",
        "name": "Multi-turn Continuity",
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "elapsed_ms": elapsed * 1000,
        "cases": results,
    }

if __name__ == "__main__":
    report = run_all_multiturn_evals()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["failed_cases"] > 0:
        print(f"\nFAIL: {report['failed_cases']} multiturn cases failed", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nPASS: all {report['total_cases']} multiturn cases passed")

