



_DIAGNOSIS_KW = [
    "故障",
    "不亮",
    "不动",
    "没输入",
    "不变",
    "排查",
    "检查",
    "排故",
    "测量",
    "接线问题",
    "不正常",
    "没反应",
    "不输出",
]

_CLARIFY_KW = [
    "帮帮我",
    "不懂",
    "不明白",
    "怎么办",
    "怎么弄",
    "问个问题",
    "有问题",
]

def _is_diagnosis_request(message):
    """Check if message looks like a fault diagnosis request."""
    text = str(message).strip() if message else ""
    if not text or len(text) < 3:
        return False
    for kw in _DIAGNOSIS_KW:
        if kw in text:
            return True
    return False

def _is_clarify_request(message):
    """Check if message is a general help/clarify request."""
    text = str(message).strip() if message else ""
    if not text or len(text) < 3:
        return False
    for kw in _CLARIFY_KW:
        if kw in text:
            return True
    return False

"""
Conversation Policy - Phase 3.
The policy engine decides what actions to take each turn.
"""

import re
from .conversation_task import get_pending_slot, looks_like_task_continuation
from .conversation_tools import TOOL_REGISTRY, AVAILABLE_TOOLS


def _c(*codepoints):
    """Build a Chinese string from Unicode codepoints."""
    return "".join(chr(cp) for cp in codepoints)


# Build Chinese keyword lists at import time (avoids source encoding issues)
_QUIZ_KW = [
    _c(0x51fa, 0x9898),
    _c(0x81ea, 0x6d4b),
    _c(0x6d4b, 0x8bd5, 0x4e00, 0x4e0b),
    _c(0x6765, 0x70b9, 0x9898),
    _c(0x505a, 0x70b9, 0x9898),
    _c(0x7ed9, 0x6211, 0x51fa),
    _c(0x751f, 0x6210, 0x9898),
    _c(0x9898, 0x76ee),
    _c(0x81ea, 0x6d4b, 0x9898),
    _c(0x6d4b, 0x8bd5, 0x9898),
]

_LEARNING_KW = [
    _c(0x5b66, 0x4e60, 0x8ba1, 0x5212),
    _c(0x57f9, 0x517b, 0x65b9, 0x6848),
    _c(0x5b66, 0x4e60, 0x8def, 0x5f84),
    _c(0x5b66, 0x4e60, 0x8def, 0x7ebf),
    _c(0x5e2e, 0x6211, 0x89c4, 0x5212),
    _c(0x4e0b, 0x4e00, 0x6b65, 0x5b66),
    _c(0x4e0b, 0x4e00, 0x6b65, 0x7ec3),
    _c(0x8be5, 0x5b66, 0x4ec0, 0x4e48),
]

_GRAPH_KW = [
    _c(0x80fd, 0x529b, 0x56fe, 0x8c31),
    _c(0x5c97, 0x4f4d, 0x56fe, 0x8c31),
    _c(0x4e2a, 0x4eba, 0x56fe, 0x8c31),
    _c(0x6211, 0x7684, 0x80fd, 0x529b),
    _c(0x6211, 0x7684, 0x8584, 0x5f31),
    _c(0x80fd, 0x529b, 0x96f7, 0x8fbe),
    _c(0x67e5, 0x770b, 0x56fe, 0x8c31),
    _c(0x6253, 0x5f00, 0x56fe, 0x8c31),
]

_STUDENT_GRAPH_KW = [
    _c(0x5b66, 0x751f, 0x56fe, 0x8c31),
    _c(0x6211, 0x7684, 0x56fe, 0x8c31),
]

_KNOWLEDGE_KW = [
    _c(0x4ec0, 0x4e48, 0x662f),
    _c(0x4ec0, 0x4e48, 0x53eb),
    _c(0x89e3, 0x91ca),
    _c(0x8bf4, 0x660e, 0x4e00, 0x4e0b),
    _c(0x8bb2, 0x4e00, 0x4e0b),
    _c(0x4ecb, 0x7ecd, 0x4e00, 0x4e0b),
    _c(0x67e5, 0x4e00, 0x4e0b),
    _c(0x641c, 0x7d22),
]

_KNOWLEDGE_QUESTION_KW = [
    _c(0x4e3a, 0x4ec0, 0x4e48),
    _c(0x600e, 0x4e48, 0x56de),
    _c(0x600e, 0x4e48, 0x4f1a),
    _c(0x5982, 0x4f55),
    _c(0x662f, 0x4ec0, 0x4e48),
    _c(0x4ec0, 0x4e48, 0x610f, 0x601d),
    _c(0x533a, 0x522b),
    _c(0x539f, 0x7406),
    _c(0x63a5, 0x7ebf),
    "PNP", "NPN", "PLC",
    _c(0x4f20, 0x611f, 0x5668),
    _c(0x7ee7, 0x7535, 0x5668),
    _c(0x6c14, 0x7f38),
    _c(0x53d8, 0x9891, 0x5668),
]


def match_explicit_action(message):
    """Match explicit user commands to tool calls."""
    text = str(message).strip() if message else ""
    if not text:
        return None, None

    for kw in _QUIZ_KW:
        if kw in text:
            return "generate_quiz", {"count": 3}

    for kw in _LEARNING_KW:
        if kw in text:
            return "generate_learning_plan", {}

    for kw in _STUDENT_GRAPH_KW:
        if kw in text:
            return "get_student_graph", {}

    for kw in _GRAPH_KW:
        if kw in text:
            return "get_job_graph", {}

    for kw in _KNOWLEDGE_KW:
        if kw in text:
            return "search_knowledge", {"query": text}

    return None, None


def is_simple_knowledge_question(message):
    """Detect simple knowledge questions (no active task needed)."""
    text = str(message).strip() if message else ""
    if not text or len(text) < 3:
        return False
    for kw in _KNOWLEDGE_QUESTION_KW:
        if kw in text:
            return True
    return False


def decide_next_actions(message, session_id=None):
    """Main policy decision function."""
    from .conversation_task import get_active_task

    active_task = get_active_task(session_id) if session_id else None

    # Priority 1: pending_slot answer
    pending_slot = get_pending_slot(session_id) if session_id else None
    if pending_slot and message:
        return {
            "mode": "continue_task",
            "actions": [{"tool": "run_diagnosis", "args": {}}],
            "preserve_active_task": True,
            "reason": "Resolving pending slot: " + str(pending_slot),
            "policy_source": "pending_slot",
            "llm_calls": 0,
        }

    # Priority 1.5: mixed intent (knowledge + diagnosis)
    # When pure diagnosis symptoms are present, diagnosis handles knowledge internally.
    if is_simple_knowledge_question(message) and _is_diagnosis_request(message):
        diag_only_kw = ["不亮", "没输入", "不动", "没反应", "不变"]
        is_pure_diag = any(kw in str(message) for kw in diag_only_kw)
        if is_pure_diag:
            return {
                "mode": "tool_actions",
                "actions": [{"tool": "run_diagnosis", "args": {}}],
                "preserve_active_task": False,
                "reason": "Diagnosis request with knowledge aspects",
                "policy_source": "diagnosis_rule",
                "llm_calls": 0,
            }
        return {
            "mode": "tool_actions",
            "actions": [
                {"tool": "search_knowledge", "args": {"query": str(message)}},
                {"tool": "run_diagnosis", "args": {}},
            ],
            "preserve_active_task": False,
            "reason": "Mixed knowledge + diagnosis request detected",
            "policy_source": "mixed_rule",
            "llm_calls": 0,
        }

    # Priority 2: explicit local command
    tool_name, tool_args = match_explicit_action(message)
    if tool_name:
        preserve = bool(active_task and tool_name == "search_knowledge")
        return {
            "mode": "tool_actions",
            "actions": [{"tool": tool_name, "args": tool_args}],
            "preserve_active_task": preserve,
            "reason": "Explicit command matched: " + tool_name,
            "policy_source": "explicit_command",
            "llm_calls": 0,
        }


    # Priority 3a: side question during active task (deterministic)
    if active_task and is_simple_knowledge_question(message):
        return {
            "mode": "side_question",
            "actions": [{"tool": "search_knowledge", "args": {"query": str(message)}}],
            "preserve_active_task": True,
            "reason": "Knowledge side question while preserving active task",
            "policy_source": "side_question_rule",
            "llm_calls": 0,
        }

    # Priority 3b: active_task continuation
    if active_task and looks_like_task_continuation(message, True):
        return {
            "mode": "continue_task",
            "actions": [{"tool": "run_diagnosis", "args": {}}],
            "preserve_active_task": True,
            "reason": "Continuing active diagnosis task",
            "policy_source": "task_continuation",
            "llm_calls": 0,
        }

    # Priority 4: diagnosis request (deterministic, no LLM needed)
    if _is_diagnosis_request(message):
        return {
            "mode": "tool_actions",
            "actions": [{"tool": "run_diagnosis", "args": {}}],
            "preserve_active_task": False,
            "reason": "Fault diagnosis keywords detected",
            "policy_source": "diagnosis_rule",
            "llm_calls": 0,
        }

    # Priority 5: simple knowledge question (no active task)
    if is_simple_knowledge_question(message):
        return {
            "mode": "tool_actions",
            "actions": [{"tool": "search_knowledge", "args": {"query": str(message)}}],
            "preserve_active_task": False,
            "reason": "Simple knowledge question detected",
            "policy_source": "knowledge_rule",
            "llm_calls": 0,
        }

    # Priority 6: clarify request
    if _is_clarify_request(message):
        return {
            "mode": "tool_actions",
            "actions": [{"tool": "search_knowledge", "args": {"query": str(message)}}],
            "preserve_active_task": bool(active_task),
            "reason": "Clarify/help request, routing to knowledge search",
            "policy_source": "clarify_rule",
            "llm_calls": 0,
        }

    # Priority 6.5: safety-related messages
    safety_kw = ["带电", "不关电源", "短接", "跳过安全"]
    if any(kw in str(message) for kw in safety_kw):
        return {
            "mode": "tool_actions",
            "actions": [{"tool": "search_knowledge", "args": {"query": str(message)}}],
            "preserve_active_task": bool(active_task),
            "reason": "Safety-related message - routing to knowledge search",
            "policy_source": "safety_rule",
            "llm_calls": 0,
        }

    # Priority 7: no-LLM deterministic fallback
    return {
        "mode": "fallback_search",
        "actions": [{"tool": "search_knowledge", "args": {"query": str(message)}}],
        "preserve_active_task": bool(active_task),
        "reason": "No explicit match; falling back to knowledge search (no LLM available)",
        "policy_source": "fallback_rule",
        "llm_calls": 0,
    }
