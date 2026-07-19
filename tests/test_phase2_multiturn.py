"""Phase 2 tests: ActiveTask + Slots + PendingSlot multi-turn task state."""

import sys, os, uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from app.services.chat import chat_message
from app.services.conversation_slots import (
    extract_slots_from_message,
    resolve_pending_slot_answer,
    PENDING_SLOT_ALIASES,
)
from app.services.conversation_task import (
    start_task,
    get_active_task,
    get_task_slots,
    set_task_slots,
    get_pending_slot,
    set_pending_slot,
    get_clarify_turns,
    increment_clarify_turn,
    looks_like_task_continuation,
    clear_active_task,
)
from app.services.conversation_state import clear_conversation_state


def fresh_id():
    return "test_p2_" + uuid.uuid4().hex[:8]


def test_1_full_text_extract_multiple_slots():
    """Complete sentence extracts multiple slots at once."""
    result = extract_slots_from_message("传感器灯亮，PLC输入灯不亮，在线监控没变化。")
    assert "sensor_led" in result, "sensor_led not extracted"
    assert result["sensor_led"]["value"] == "on", f"expected on, got {result['sensor_led']['value']}"
    assert result["plc_input_led"]["value"] == "off"
    assert result["online_monitor"]["value"] == "unchanged"
    print("  PASS test_1: full text multi-slot extraction")


def test_2_pending_slot_short_answer():
    """Pending slot resolves short answers correctly."""
    slot, val = resolve_pending_slot_answer("plc_input_led", "不亮")
    assert slot == "plc_input_led"
    assert val["value"] == "off", f"expected off, got {val['value']}"
    assert val["source"] == "pending_slot_answer"

    slot, val = resolve_pending_slot_answer("online_monitor", "没有")
    assert slot == "online_monitor"
    assert val["value"] == "unchanged", f"expected unchanged, got {val['value']}"

    print("  PASS test_2: pending slot short answer resolution")


def test_3_no_repeat_question():
    """System should not ask about already-known slots."""
    sid = fresh_id()
    start_task(sid, topic="test")
    set_task_slots(sid, {
        "sensor_type": {"value": "PNP", "source": "user_text", "confidence": 1.0, "updated_turn": 1}
    })

    from app.services.conversation_slots import get_missing_slots
    task = get_active_task(sid)
    missing = get_missing_slots(task.get("slots", {}))

    assert "sensor_type" not in missing, "Should not ask about known sensor_type"
    print("  PASS test_3: no repeat question on known slots")

    clear_conversation_state(sid)


def test_4_chat_and_ui_context_merge():
    """Chat slots and UI context merge correctly."""
    sid = fresh_id()
    start_task(sid, topic="test")
    set_task_slots(sid, {
        "sensor_led": {"value": "on", "source": "user_text", "confidence": 1.0, "updated_turn": 1}
    })

    from app.services.conversation_slots import merge_ui_context_into_slots
    task = get_active_task(sid)
    merged = merge_ui_context_into_slots(task.get("slots", {}), {
        "plc_input_led": "off",
        "sensor_led": "unknown",  # UI says unknown, but chat says on -> chat wins
    })

    assert merged["sensor_led"]["value"] == "on", "User text should override UI unknown"
    assert merged["plc_input_led"]["value"] == "off", "UI context should be added"

    print("  PASS test_4: chat and UI context merge")
    clear_conversation_state(sid)


def test_5_task_level_clarify_independent():
    """New task starts with clarify_turns=0."""
    sid = fresh_id()
    start_task(sid, topic="Task A")
    increment_clarify_turn(sid)
    increment_clarify_turn(sid)
    assert get_clarify_turns(sid) == 2

    # Start new task (overwrites old one in single-task model)
    start_task(sid, topic="Task B")
    assert get_clarify_turns(sid) == 0, "New task should start at clarify_turns=0"

    print("  PASS test_5: task-level clarify independent")
    clear_conversation_state(sid)


def test_6_clarify_max_turns():
    """3 clarify turns allowed; 4th triggers best effort."""
    # MAX_CLARIFY_TURNS = 3, so turns 1,2,3 are ok, round 4 triggers best effort
    from app.services.conversation_task import MAX_CLARIFY_TURNS
    assert MAX_CLARIFY_TURNS == 3
    print("  PASS test_6: MAX_CLARIFY_TURNS = 3")
    # The behavior is tested via _count_clarify_rounds in intent_handlers


def test_7_new_task_slot_isolation():
    """New task does not inherit old task slots (unless global device context)."""
    sid = fresh_id()
    start_task(sid, topic="Task A")
    set_task_slots(sid, {
        "sensor_type": {"value": "PNP", "source": "user_text", "confidence": 1.0, "updated_turn": 1}
    })

    # Start new task
    start_task(sid, topic="Task B")
    task = get_active_task(sid)
    slots = task.get("slots", {})
    assert slots == {}, f"New task should have empty slots, got {slots}"

    print("  PASS test_7: new task slot isolation")
    clear_conversation_state(sid)


def test_8_user_correction():
    """User can correct a previously set slot."""
    from app.services.conversation_slots import apply_slot_updates

    slots = {
        "sensor_type": {"value": "NPN", "source": "user_text", "confidence": 1.0, "updated_turn": 1}
    }
    corrected = apply_slot_updates(slots, {
        "sensor_type": {"value": "PNP", "source": "user_text", "confidence": 1.0, "updated_turn": 2}
    })
    assert corrected["sensor_type"]["value"] == "PNP", "Correction should override"
    print("  PASS test_8: user correction overwrites")


def test_9_short_answer_no_reroute():
    """Short answer with active task should be task_continuation, not new intent."""
    sid = fresh_id()
    start_task(sid, topic="test diagnosis", task_type="diagnosis")
    set_pending_slot(sid, "plc_input_led")

    result = chat_message({
        "session_id": sid,
        "message": "不亮",
        "context": {},
    })

    assert result.get("intent_source") == "task_continuation", \
        f"Expected task_continuation, got {result.get('intent_source')}"
    print("  PASS test_9: short answer does not re-route")
    clear_conversation_state(sid)


def test_10_session_isolation():
    """Different sessions have independent slots."""
    sid_a = fresh_id()
    sid_b = fresh_id()

    start_task(sid_a, topic="A")
    set_task_slots(sid_a, {
        "plc_input_led": {"value": "off", "source": "user_text", "confidence": 1.0, "updated_turn": 1}
    })

    start_task(sid_b, topic="B")
    task_b = get_active_task(sid_b)
    assert task_b.get("slots", {}) == {}, "Session B should start empty"

    print("  PASS test_10: session isolation")
    clear_conversation_state(sid_a)
    clear_conversation_state(sid_b)


if __name__ == "__main__":
    print("Running Phase 2 tests...")
    test_1_full_text_extract_multiple_slots()
    test_2_pending_slot_short_answer()
    test_3_no_repeat_question()
    test_4_chat_and_ui_context_merge()
    test_5_task_level_clarify_independent()
    test_6_clarify_max_turns()
    test_7_new_task_slot_isolation()
    test_8_user_correction()
    test_9_short_answer_no_reroute()
    test_10_session_isolation()
    print("ALL Phase 2 tests PASSED")
