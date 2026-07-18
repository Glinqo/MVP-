# -*- coding: utf-8 -*-
"""L1 State Eval Runner - executes state test cases against ConversationState."""
import json, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.conversation_state import (
    get_or_create_conversation_state, append_user_message, append_assistant_message,
    get_conversation_context, clear_conversation_state
)
from app.services.conversation_slots import extract_slots_from_message
from app.services.conversation_task import get_pending_slot
from app.services.conversation_slots import resolve_pending_slot_answer
from app.services.conversation_task import (
    get_active_task, start_task, clear_active_task,
    get_pending_slot, set_pending_slot, get_task_slots, set_task_slots
)
from evals.scorers.state_scorer import score_state, score_slot_accuracy

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

def run_state_case(case):
    """Run a single state eval case through ConversationState."""
    session_id = f"eval-state-{case['id']}"
    clear_conversation_state(session_id)
    get_or_create_conversation_state(session_id)

    actual = {"slots": {}, "pending_slot": None, "active_task_changed": False}
    prev_task = None

    pending_slot_name = None
    for turn in case.get("turns", []):
        role = turn.get("role", "user")
        content = turn.get("user") or turn.get("assistant") or ""
        if not content:
            continue

        # Track pending slot from assistant questions
        if role == "assistant" or "assistant" in turn:
            # Detect which slot the AI is asking about
            for sn in ["online_monitor", "sensor_led", "plc_input_led", "sensor_type", "common_terminal"]:
                slot_label = {"online_monitor": "监控", "sensor_led": "传感器灯", "plc_input_led": "PLC输入", "sensor_type": "类型", "common_terminal": "公共端"}.get(sn, "")
                if slot_label and slot_label in content:
                    pending_slot_name = sn
                    set_pending_slot(session_id, sn)
                    break
            append_assistant_message(session_id, content)
            continue

        if role == "user" or "user" in turn:
            append_user_message(session_id, content)
            # Extract slots from message (full text patterns)
            extracted = extract_slots_from_message(content)
            if extracted:
                task_slots = get_task_slots(session_id)
                task_slots.update(extracted)
                set_task_slots(session_id, task_slots)
                actual["slots"].update(extracted)

            # For short answers, try pending_slot resolution with tracked slot
            if len(content.strip()) < 10 and not extracted and pending_slot_name:
                slot_val, slot_data = resolve_pending_slot_answer(pending_slot_name, content)
                if slot_val:
                    task_slots = get_task_slots(session_id)
                    task_slots[pending_slot_name] = slot_data
                    set_task_slots(session_id, task_slots)
                    actual["slots"][pending_slot_name] = slot_data

            # Check if this is a topic switch
            if "换个" in content and "问题" in content:
                actual["active_task_changed"] = True
                clear_active_task(session_id)
                continue

            # Start task if none active
            task = get_active_task(session_id)
            if not task:
                start_task(session_id, "diagnosis", content[:40])
        else:
            append_assistant_message(session_id, content)

    # Collect final state
    task = get_active_task(session_id)
    if task:
        actual["slots"].update(task.get("slots", {}))
    actual["pending_slot"] = get_pending_slot(session_id)

    # Score
    expected = case.get("expect", {})
    result = score_state(expected, actual)
    result["case_id"] = case["id"]
    result["category"] = case.get("category", "")

    # Cleanup
    clear_conversation_state(session_id)
    return result

def run_all_state_evals():
    """Run all state eval cases."""
    cases = load_cases("state.jsonl")
    results = []
    start_time = time.time()

    for case in cases:
        result = run_state_case(case)
        results.append(result)

    elapsed = time.time() - start_time

    # Aggregate
    total = len(results)
    passed_count = sum(1 for r in results if not r.get("failed"))
    total_checks = sum(r.get("total", 0) for r in results)
    passed_checks = sum(len(r.get("passed", [])) for r in results)

    report = {
        "layer": "L1",
        "name": "State Correctness",
        "total_cases": total,
        "passed_cases": passed_count,
        "failed_cases": total - passed_count,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "accuracy": passed_checks / max(total_checks, 1),
        "elapsed_ms": elapsed * 1000,
        "cases": results,
    }
    return report

if __name__ == "__main__":
    report = run_all_state_evals()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # Exit code based on hard gate
    if report["failed_cases"] > 0:
        print(f"\nFAIL: {report['failed_cases']} state cases failed", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nPASS: all {report['total_cases']} state cases passed")

