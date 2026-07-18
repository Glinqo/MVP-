"""
Conversation Runner - Phase 4.

Unified turn execution pipeline. Both /api/chat/stream and /api/chat/message
go through the same run_conversation_turn() function.
"""

from .conversation_state import (
    append_user_message,
    append_assistant_message,
    get_conversation_context,
)
from .conversation_slots import (
    extract_slots_from_message,
    resolve_pending_slot_answer,
    apply_slot_updates,
    merge_ui_context_into_slots,
    slots_to_assist_context,
    slots_summary,
)
from .conversation_task import (
    start_task,
    get_active_task,
    get_task_slots,
    set_task_slots,
    get_pending_slot,
    set_pending_slot,
    clear_pending_slot,
    looks_like_task_continuation,
    task_summary,
)
from .conversation_policy import decide_next_actions
from .conversation_tools import execute_tool
from .action_planner import plan_actions
from .response_composer import compose_response
from .conversation_events import (
    generate_turn_id, accepted, state_event, tool_start, tool_result,
    delta, cards_event, done_event, error_event, ConversationEvent,
)
from .intent import classify_intent
from .assist import assist
from .intent_handlers import handle_clarify, handle_graph, handle_knowledge_qa, handle_learning_path, handle_quiz
from .feedback import append_session_event
from .graph import build_student_ability_graph
from .learner_context import learner_context_pack
from .data_loader import primary_job_profile
from .safety import safety_notice


def run_conversation_turn(session_id, message, ui_context_delta=None):
    """Execute one conversation turn. Returns a generator of ConversationEvent.

    This is the single entry point for all chat processing.
    Both stream and non-stream endpoints use this function.
    """
    turn_id = generate_turn_id()
    ui_context_delta = ui_context_delta or {}

    # ---- 0. Accepted ----
    yield accepted(turn_id)

    # ---- 1. Record user message (exactly once) ----
    if session_id and message:
        append_user_message(session_id, message)
    yield state_event("processing", turn_id, task_type="analyzing")

    # ---- 2. Resolve pending slot ----
    pending_slot = get_pending_slot(session_id) if session_id else None
    if pending_slot and message:
        slot_name, slot_val = resolve_pending_slot_answer(pending_slot, message)
        if slot_name:
            task_slots = get_task_slots(session_id)
            task_slots = apply_slot_updates(task_slots, {slot_name: slot_val})
            set_task_slots(session_id, task_slots)
            clear_pending_slot(session_id)

    # ---- 3. Extract slots + merge UI context ----
    extracted_slots = extract_slots_from_message(message)
    active_task = get_active_task(session_id) if session_id else None

    if active_task and (extracted_slots or ui_context_delta):
        task_slots = get_task_slots(session_id)
        if extracted_slots:
            task_slots = apply_slot_updates(task_slots, extracted_slots)
        if ui_context_delta:
            task_slots = merge_ui_context_into_slots(task_slots, ui_context_delta)
        set_task_slots(session_id, task_slots)

    # ---- 4. Build effective context ----
    active_task = get_active_task(session_id) if session_id else None
    if active_task:
        effective_context = slots_to_assist_context(active_task.get("slots", {}))
        for k, v in ui_context_delta.items():
            if effective_context.get(k, "unknown") in ("unknown", "", None):
                effective_context[k] = v
    else:
        effective_context = dict(ui_context_delta)

    # ---- 5. Policy decision ----
    yield state_event("planning", turn_id)
    policy = decide_next_actions(message, session_id)

    # ---- 6. Execute tools (or fallback) ----
    actions = policy.get("actions", [])

    if policy.get("mode") == "defer_to_planner":
        yield state_event("planning_llm", turn_id)
        history = get_conversation_context(session_id, limit=8) if session_id else []
        planner_result = plan_actions(
            message,
            conversation_state={"slots": active_task.get("slots", {}) if active_task else {}},
            active_task=active_task,
            slots=active_task.get("slots", {}) if active_task else {},
            history=history,
        )
        if planner_result.get("actions"):
            actions = planner_result["actions"]
        else:
            # Legacy fallback
            intent_result = classify_intent(message)
            actions = _intent_to_actions(intent_result, message)

    # ---- 7. Run tools ----
    tool_results = []
    for action in actions:
        tool_name = action.get("tool", "")
        tool_args = dict(action.get("args", {}))
        if tool_name == "run_diagnosis":
            tool_args["active_task"] = active_task
        if tool_name in ("get_student_graph", "generate_quiz", "generate_learning_plan"):
            tool_args["session_id"] = session_id

        label = _tool_label(tool_name)
        yield tool_start(tool_name, label, turn_id)

        result = execute_tool(tool_name, **tool_args)
        tool_results.append(result)
        yield tool_result(
            tool_name,
            result.success,
            data=result.data if hasattr(result, "data") else {},
            refs=result.user_visible_refs if hasattr(result, "user_visible_refs") else [],
            turn_id=turn_id,
        )

    # ---- 8. Compose response ----
    yield state_event("composing", turn_id)
    composed = compose_response(message, tool_results, active_task=active_task)
    answer = composed.get("answer", "") if composed else ""

    # ---- 9. Stream answer as delta events ----
    # For now, send the full answer as one delta (future: true streaming)
    if answer:
        yield delta(answer, turn_id)

    # ---- 10. Cards event ----
    if composed:
        knowledge_refs = composed.get("knowledge_refs", [])
        highlighted = composed.get("highlighted_abilities", [])
        remediation = composed.get("remediation_cards", [])
        next_qs = composed.get("next_questions", [])
        if knowledge_refs or highlighted or remediation or next_qs:
            yield cards_event(
                knowledge_refs=knowledge_refs,
                ability_cards=highlighted,
                task_cards=remediation,
                tool_suggestions=next_qs,
                turn_id=turn_id,
            )

    # ---- 11. Track pending_slot for next turn ----
    if session_id and active_task:
        for tr in tool_results:
            if hasattr(tr, "data") and isinstance(tr.data, dict):
                questions = tr.data.get("clarifying_questions", [])
                if questions:
                    p = get_pending_slot(session_id)
                    if not p:
                        for q in questions:
                            field = q.get("field")
                            if field:
                                ts = active_task.get("slots", {})
                                sv = ts.get(field, {})
                                v = sv.get("value", "unknown") if isinstance(sv, dict) else str(sv)
                                if v in ("unknown", "", None):
                                    set_pending_slot(session_id, field)
                                    break

    # ---- 12. Finalize ----
    if session_id:
        append_assistant_message(session_id, answer)
        append_session_event(session_id, {
            "event_type": "chat_message",
            "message": message,
            "policy_source": policy.get("policy_source", "unknown"),
            "tools_used": [a.get("tool") for a in actions],
        })

    state_delta = {
        "active_task": task_summary(session_id) if session_id else None,
        "slots": slots_summary(active_task.get("slots", {}) if active_task else {}),
    }

    yield done_event(answer, turn_id, conversation_state_delta=state_delta)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tool_label(tool_name):
    labels = {
        "search_knowledge": "Searching knowledge base",
        "run_diagnosis": "Analyzing current state",
        "generate_quiz": "Generating quiz",
        "get_job_graph": "Loading job graph",
        "get_student_graph": "Loading student graph",
        "generate_learning_plan": "Generating learning plan",
    }
    return labels.get(tool_name, "Running " + tool_name)


def _intent_to_actions(intent_result, message):
    """Convert legacy intent to tool actions (fallback)."""
    intent = intent_result.get("intent", "diagnosis") if intent_result else "diagnosis"
    mapping = {
        "knowledge_qa": [{"tool": "search_knowledge", "args": {"query": message}}],
        "diagnosis": [{"tool": "run_diagnosis", "args": {}}],
        "quiz": [{"tool": "generate_quiz", "args": {"count": 3}}],
        "graph": [{"tool": "get_job_graph", "args": {}}],
        "learning_path": [{"tool": "generate_learning_plan", "args": {}}],
        "clarify": [{"tool": "run_diagnosis", "args": {}}],
    }
    return mapping.get(intent, [{"tool": "search_knowledge", "args": {"query": message}}])
