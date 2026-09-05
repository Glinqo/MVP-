"""Phase 3 tests: Conversation Policy + Tools + Action Planner."""

import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from app.services.conversation_policy import (
    match_explicit_action, decide_next_actions, is_simple_knowledge_question,
    _c,
)
from app.services.conversation_tools import (
    execute_tool, TOOL_REGISTRY, AVAILABLE_TOOLS, MAX_TOOL_ACTIONS_PER_TURN, ToolResult,
)
from app.services.conversation_task import (
    start_task, get_active_task, set_pending_slot, clear_active_task,
)
from app.services.conversation_state import clear_conversation_state
from app.services.chat import chat_message


def fresh_id():
    return "test_p3_" + uuid.uuid4().hex[:8]


def test_1_tool_registry():
    """All tools are registered and executable."""
    for name in ["search_knowledge", "run_diagnosis", "generate_quiz",
                 "get_job_graph", "get_student_graph", "generate_learning_plan"]:
        assert name in TOOL_REGISTRY, "Missing tool: " + name
        assert callable(TOOL_REGISTRY[name]["function"]), "Not callable: " + name
    print("  PASS test_1: tool registry complete")


def test_2_search_knowledge_tool():
    """search_knowledge returns structured result."""
    result = execute_tool("search_knowledge", query="PLC wiring")
    assert isinstance(result, ToolResult)
    assert result.success
    assert len(result.data.get("items", [])) > 0
    print("  PASS test_2: search_knowledge works")


def test_3_run_diagnosis_tool():
    """run_diagnosis returns structured result."""
    sid = fresh_id()
    start_task(sid, topic="PLC input LED off", task_type="diagnosis")
    task = get_active_task(sid)
    result = execute_tool("run_diagnosis", active_task=task)
    assert isinstance(result, ToolResult)
    assert result.success
    assert "status" in result.data
    print("  PASS test_3: run_diagnosis works")
    clear_conversation_state(sid)


def test_4_explicit_command_routing():
    """Explicit commands route to correct tools."""
    tests = [
        (_c(0x7ed9, 0x6211, 0x51fa) + "3" + _c(0x9898), "generate_quiz"),
        (_c(0x5b66, 0x4e60, 0x8ba1, 0x5212), "generate_learning_plan"),
        (_c(0x80fd, 0x529b, 0x56fe, 0x8c31), "get_job_graph"),
        (_c(0x4ec0, 0x4e48, 0x662f) + "PLC", "search_knowledge"),
    ]
    for msg, expected_tool in tests:
        tool, args = match_explicit_action(msg)
        assert tool == expected_tool, "%s -> expected %s, got %s" % (msg, expected_tool, tool)
    print("  PASS test_4: explicit command routing")


def test_5_knowledge_question_detection():
    """Simple knowledge questions detected without active task."""
    tests = [
        (_c(0x4e3a, 0x4ec0, 0x4e48) + "PNP" + _c(0x8981, 0x8fd9, 0x4e48, 0x63a5), True),
        (_c(0x5982, 0x4f55) + _c(0x63a5, 0x7ebf), True),
        ("hello", False),
        ("", False),
    ]
    for msg, expected in tests:
        result = is_simple_knowledge_question(msg)
        assert result == expected, "%s -> expected %s, got %s" % (msg, expected, result)
    print("  PASS test_5: knowledge question detection")


def test_6_policy_priority_order():
    """Policy respects priority: explicit > continuation > knowledge."""
    # Without session: explicit command
    msg = _c(0x51fa, 0x9898)  # ??
    r = decide_next_actions(msg)
    assert r["policy_source"] == "explicit_command"

    # Without session: explicit knowledge command (has keyword match)
    msg = _c(0x4ec0, 0x4e48, 0x662f) + "PLC"  # ???PLC
    r = decide_next_actions(msg)
    # This matches explicit command for search_knowledge
    assert r["policy_source"] == "explicit_command"

    print("  PASS test_6: policy priority order")

def test_7_tool_result_schema():
    """ToolResult follows standard schema."""
    tr = ToolResult(tool_name="test", success=True, data={"key": "val"}, evidence=["e1"])
    d = tr.to_dict()
    assert d["tool_name"] == "test"
    assert d["success"] is True
    assert d["data"]["key"] == "val"
    assert "e1" in d["evidence"]
    print("  PASS test_7: ToolResult schema")


def test_8_unknown_tool_rejected():
    """Unknown tool names are rejected."""
    result = execute_tool("nonexistent_tool", arg="val")
    assert not result.success
    assert result.error is not None
    print("  PASS test_8: unknown tool rejected")


def test_9_max_tool_actions():
    """MAX_TOOL_ACTIONS_PER_TURN is configured."""
    assert MAX_TOOL_ACTIONS_PER_TURN == 3
    print("  PASS test_9: MAX_TOOL_ACTIONS_PER_TURN = 3")


def test_10_chat_message_uses_policy():
    """chat_message uses the new policy pipeline."""
    sid = fresh_id()
    result = chat_message({
        "session_id": sid,
        "message": _c(0x4ec0, 0x4e48, 0x662f) + "PLC",  # ???PLC
        "context": {},
    })
    # Should have policy_source in result
    assert "policy_source" in result, "Missing policy_source in response"
    assert result["policy_source"] in ("knowledge_rule", "explicit_command", "defer_to_planner", "pending_slot", "task_continuation"), \
        "Unexpected policy_source: " + str(result.get("policy_source"))
    print("  PASS test_10: chat_message uses policy pipeline (source=%s)" % result["policy_source"])
    clear_conversation_state(sid)


if __name__ == "__main__":
    print("Running Phase 3 tests...")
    test_1_tool_registry()
    test_2_search_knowledge_tool()
    test_3_run_diagnosis_tool()
    test_4_explicit_command_routing()
    test_5_knowledge_question_detection()
    test_6_policy_priority_order()
    test_7_tool_result_schema()
    test_8_unknown_tool_rejected()
    test_9_max_tool_actions()
    test_10_chat_message_uses_policy()
    print("ALL Phase 3 tests PASSED")
