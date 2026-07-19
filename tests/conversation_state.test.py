"""
Tests for conversation_state.py — Phase 1: ConversationState

Tests:
  1. Current message not duplicated in LLM context
  2. Server history correct across rounds
  3. No history in request, server finds context
  4. Different sessions fully isolated
  5. Page refresh restores from server (simulated)
  6. Stream writes only once
  7. Old features compatible (knowledge QA, diagnosis, clarify, quiz, learning_path)
"""

import sys, os, json, uuid, copy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from app.services.conversation_state import (
    load_conversation_state,
    save_conversation_state,
    get_or_create_conversation_state,
    append_user_message,
    append_assistant_message,
    get_recent_messages,
    get_all_messages,
    clear_conversation_state,
    get_conversation_context,
)


def fresh_session_id():
    return f"test_conv_{uuid.uuid4().hex[:8]}"


def test_1_no_duplicate_in_context():
    """Current message should not appear in LLM context when retrieved."""
    sid = fresh_session_id()
    append_user_message(sid, "My PLC input light is off")
    append_assistant_message(sid, "Check the common terminal wiring.")
    # Now send a new user message
    append_user_message(sid, "I checked, common terminal is fine.")

    # Get context with limit=2 — should get the last 2 messages
    ctx = get_conversation_context(sid, limit=2)
    assert len(ctx) == 2, f"Expected 2 context messages, got {len(ctx)}"
    # The last message should be the new user message
    assert ctx[-1]["role"] == "user", "Last should be user"
    assert "common terminal is fine" in ctx[-1]["content"]
    # The previous should be assistant
    assert ctx[-2]["role"] == "assistant", "Second last should be assistant"

    # Full history should have 3 messages
    all_msgs = get_all_messages(sid)
    assert len(all_msgs) == 3, f"Expected 3 total messages, got {len(all_msgs)}"

    clear_conversation_state(sid)
    print("  PASS test_1: no duplicate in context")


def test_2_history_across_rounds():
    """Server history correctly accumulates across multiple conversation rounds."""
    sid = fresh_session_id()

    # Round 1
    append_user_message(sid, "What is NPN sensor wiring?")
    append_assistant_message(sid, "NPN wiring explanation...")

    # Round 2
    append_user_message(sid, "How to test it with PLC?")
    append_assistant_message(sid, "PLC testing explanation...")

    all_msgs = get_all_messages(sid)
    assert len(all_msgs) == 4, f"Expected 4 messages, got {len(all_msgs)}"
    assert all_msgs[0]["role"] == "user"
    assert all_msgs[0]["content"] == "What is NPN sensor wiring?"
    assert all_msgs[2]["role"] == "user"
    assert all_msgs[2]["content"] == "How to test it with PLC?"

    # Context should return most recent
    ctx = get_conversation_context(sid, limit=2)
    assert len(ctx) == 2
    # Most recent 2: user then assistant
    assert ctx[0]["role"] == "user"
    assert ctx[1]["role"] == "assistant"
    assert "PLC testing" in ctx[1]["content"]

    clear_conversation_state(sid)
    print("  PASS test_2: history across rounds")


def test_3_no_history_in_request():
    """Even when client sends no history, server still has context."""
    sid = fresh_session_id()

    # Pre-populate with some server-side messages
    append_user_message(sid, "Explain PLC wiring")
    append_assistant_message(sid, "PLC wiring basics...")

    # Simulate a new request with no history field
    ctx = get_conversation_context(sid, limit=2)
    assert len(ctx) == 2
    assert ctx[0]["role"] == "user"

    clear_conversation_state(sid)
    print("  PASS test_3: no history in request, server has context")


def test_4_session_isolation():
    """Different sessions must be fully isolated."""
    sid1 = fresh_session_id()
    sid2 = fresh_session_id()

    append_user_message(sid1, "Session 1 message")
    append_user_message(sid2, "Session 2 message")

    msgs1 = get_all_messages(sid1)
    msgs2 = get_all_messages(sid2)

    assert len(msgs1) == 1
    assert len(msgs2) == 1
    assert msgs1[0]["content"] == "Session 1 message"
    assert msgs2[0]["content"] == "Session 2 message"

    # Modify session 1, session 2 should be unaffected
    append_assistant_message(sid1, "Session 1 reply")
    msgs2_after = get_all_messages(sid2)
    assert len(msgs2_after) == 1, "Session 2 should still have 1 message"

    clear_conversation_state(sid1)
    clear_conversation_state(sid2)
    print("  PASS test_4: session isolation")


def test_5_restore_from_server():
    """Page refresh scenario: get_all_messages returns full history."""
    sid = fresh_session_id()

    append_user_message(sid, "Question 1")
    append_assistant_message(sid, "Answer 1")
    append_user_message(sid, "Question 2")
    append_assistant_message(sid, "Answer 2")

    # Simulate page refresh: get all messages
    restored = get_all_messages(sid)
    assert len(restored) == 4, f"Expected 4 restored messages, got {len(restored)}"

    # Verify ordering
    assert restored[0]["content"] == "Question 1"
    assert restored[3]["content"] == "Answer 2"

    clear_conversation_state(sid)
    print("  PASS test_5: page refresh restores from server")


def test_6_stream_writes_once():
    """Each append_user_message / append_assistant_message writes exactly once."""
    sid = fresh_session_id()

    append_user_message(sid, "Stream test")
    msgs1 = get_all_messages(sid)
    assert len(msgs1) == 1

    # Second call should not overwrite, should append
    append_assistant_message(sid, "Stream response")
    msgs2 = get_all_messages(sid)
    assert len(msgs2) == 2

    # Verify no duplication
    roles = [m["role"] for m in msgs2]
    assert roles == ["user", "assistant"], f"Unexpected roles: {roles}"

    clear_conversation_state(sid)
    print("  PASS test_6: stream writes exactly once")


def test_7_feature_compatibility():
    """Old features (knowledge QA, diagnosis, clarify, quiz, learning_path)
    should be compatible with new conversation state."""
    sid = fresh_session_id()

    # Simulate knowledge QA flow
    append_user_message(sid, "What is PLC scan cycle?")
    append_assistant_message(sid, "PLC scan cycle explanation...")
    ctx = get_conversation_context(sid, limit=4)
    assert len(ctx) == 2

    # Simulate diagnosis flow
    append_user_message(sid, "Diagnose sensor signal loss")
    append_assistant_message(sid, "Diagnosis steps...")
    ctx = get_conversation_context(sid, limit=4)
    assert len(ctx) == 4

    # Simulate clarify: the context should include clarifying exchanges
    append_user_message(sid, "What do you mean by common terminal?")
    append_assistant_message(sid, "Clarification about common terminal...")
    ctx = get_conversation_context(sid, limit=2)
    assert len(ctx) == 2
    # Most recent 2: [user("What do you mean..."), assistant("Clarification...")]
    assert "Clarification" in ctx[1]["content"]

    # Simulate quiz response
    append_user_message(sid, "Quiz answer: B")
    append_assistant_message(sid, "Correct! Explanation...")
    ctx = get_conversation_context(sid, limit=2)
    assert len(ctx) == 2
    assert ctx[-1]["role"] == "assistant"

    # Simulate learning path query
    append_user_message(sid, "What should I study next?")
    append_assistant_message(sid, "Learning path recommendation...")
    msgs = get_all_messages(sid)
    assert len(msgs) == 10, f"Expected 10 messages total, got {len(msgs)}"

    clear_conversation_state(sid)
    print("  PASS test_7: feature compatibility (QA, diagnosis, clarify, quiz, learning_path)")


def test_edge_cases():
    """Additional edge case coverage."""
    sid = fresh_session_id()

    # Empty session should return empty
    ctx = get_conversation_context(sid, limit=8)
    assert ctx == [], f"Expected empty context, got {ctx}"

    # limit=0 should return empty
    append_user_message(sid, "test")
    ctx_zero = get_conversation_context(sid, limit=0)
    assert ctx_zero == []

    # clear should work
    clear_conversation_state(sid)
    assert get_all_messages(sid) == []

    # Timestamp should be present
    append_user_message(sid, "timestamp test")
    msgs = get_all_messages(sid)
    assert "created_at" in msgs[0]
    assert msgs[0]["role"] == "user"

    clear_conversation_state(sid)
    print("  PASS edge cases: empty, limit=0, clear, timestamps")


if __name__ == "__main__":
    print("Running conversation_state tests...")
    test_1_no_duplicate_in_context()
    test_2_history_across_rounds()
    test_3_no_history_in_request()
    test_4_session_isolation()
    test_5_restore_from_server()
    test_6_stream_writes_once()
    test_7_feature_compatibility()
    test_edge_cases()
    print("ALL conversation_state tests PASSED")
