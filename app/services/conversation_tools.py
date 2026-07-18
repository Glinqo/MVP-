"""
Conversation Tools ? Phase 3.

Unified tool registry. Each tool wraps an existing business capability
and returns a structured ToolResult. Tools do NOT generate final user-facing
answers ? that is the job of Response Composer.
"""

from .assist import assist
from .retrieval import search_knowledge as _search_knowledge
from .quiz import personalized_quiz
from .graph import build_job_ability_graph, build_student_ability_graph
from .personalized_plan import personalized_plan
from .conversation_slots import slots_to_assist_context
from .diagnosis_policy import select_next_best_check, get_candidate_causes, get_remaining_causes, init_diagnosis_progress, update_diagnosis_progress


# ---------------------------------------------------------------------------
# Tool Result schema
# ---------------------------------------------------------------------------

class ToolResult:
    """Standard tool result wrapper."""
    __slots__ = ("tool_name", "success", "data", "evidence", "user_visible_refs", "error")

    def __init__(self, tool_name, success=True, data=None, evidence=None,
                 user_visible_refs=None, error=None):
        self.tool_name = tool_name
        self.success = success
        self.data = data or {}
        self.evidence = evidence or []
        self.user_visible_refs = user_visible_refs or []
        self.error = error

    def to_dict(self):
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "data": self.data,
            "evidence": self.evidence,
            "user_visible_refs": self.user_visible_refs,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def search_knowledge_tool(query, limit=5):
    """Search the knowledge base for concept explanations, principles, wiring etc."""
    try:
        results = _search_knowledge(query, limit=limit)
        items = []
        refs = []
        for r in results:
            if isinstance(r, dict):
                items.append({
                    "title": r.get("title", ""),
                    "content": r.get("content", "")[:500],
                    "source": r.get("source", ""),
                })
                if r.get("title"):
                    refs.append(r.get("title"))
        return ToolResult(
            tool_name="search_knowledge",
            success=True,
            data={"query": query, "items": items, "count": len(items)},
            user_visible_refs=refs,
        )
    except Exception as e:
        return ToolResult(tool_name="search_knowledge", success=False, error=str(e))


def run_diagnosis_tool(conversation_state=None, active_task=None):
    """Phase 8: Run fault diagnosis with progress tracking and next-best-check."""
    try:
        active_task = active_task or {}
        context = {}
        if active_task.get("slots"):
            context = slots_to_assist_context(active_task["slots"])
        user_input = active_task.get("topic", "") if active_task else ""
        result = assist({"user_input": user_input, "context": context})
        pattern = result.get("matched_pattern", {})
        pattern_id = pattern.get("id", "") if pattern else ""

        # Phase 8: Diagnosis Progress
        progress = active_task.get("diagnosis_progress") if active_task else None
        if not progress:
            progress = init_diagnosis_progress()
        if pattern_id:
            progress = update_diagnosis_progress(progress, pattern_id, context)

        candidates = get_candidate_causes(pattern_id, context) if pattern_id else []
        remaining = get_remaining_causes(candidates) if candidates else []
        next_best = select_next_best_check(pattern_id, context, progress) if pattern_id else None

        data = {
            "status": result.get("status", "ok"),
            "matched_pattern": pattern,
            "safety_notice": result.get("safety_notice", ""),
            "first_checks": result.get("first_checks", []),
            "fault_candidates": result.get("fault_candidates", []),
            "highlighted_abilities": result.get("highlighted_abilities", []),
            "knowledge_gaps": result.get("knowledge_gaps", []),
            "remediation_cards": result.get("remediation_cards", []),
            "clarifying_questions": result.get("clarifying_questions", []),
            "direct_answer": result.get("direct_answer", ""),
            "candidate_causes": candidates,
            "remaining_causes": remaining,
            "next_best_action": next_best,
            "diagnosis_progress": {
                "phase": progress.get("phase", "collecting_info"),
                "stalled_count": progress.get("stalled_count", 0),
                "is_stalled": progress.get("stalled_count", 0) >= 2,
            },
        }
        return ToolResult(
            tool_name="run_diagnosis",
            success=True,
            data=data,
            user_visible_refs=[a.get("id", "") for a in result.get("highlighted_abilities", [])],
        )
    except Exception as e:
        import traceback
        return ToolResult(tool_name="run_diagnosis", success=False, error=str(e) + " | TRACE: " + str(traceback.format_exc())[:300])

def generate_quiz_tool(session_id=None, topic=None, count=3):
    """Generate personalized quiz questions."""
    try:
        payload = {"session_id": session_id}
        if topic:
            payload["topic"] = topic
        if count:
            payload["count"] = count
        result = personalized_quiz(payload)
        questions = result.get("questions", []) if isinstance(result, dict) else []
        return ToolResult(
            tool_name="generate_quiz",
            success=True,
            data={
                "questions": questions,
                "count": len(questions),
                "topic": topic,
            },
        )
    except Exception as e:
        return ToolResult(tool_name="generate_quiz", success=False, error=str(e))


def get_job_graph_tool(job_role=None):
    """Get the job ability graph."""
    try:
        graph_data = build_job_ability_graph(job_role)
        return ToolResult(
            tool_name="get_job_graph",
            success=True,
            data={"graph": graph_data},
        )
    except Exception as e:
        return ToolResult(tool_name="get_job_graph", success=False, error=str(e))


def get_student_graph_tool(session_id=None):
    """Get the student ability graph."""
    try:
        graph_data = build_student_ability_graph(session_id)
        return ToolResult(
            tool_name="get_student_graph",
            success=True,
            data={"graph": graph_data},
        )
    except Exception as e:
        return ToolResult(tool_name="get_student_graph", success=False, error=str(e))


def generate_learning_plan_tool(session_id=None):
    """Generate a personalized learning plan."""
    try:
        payload = {"session_id": session_id} if session_id else {}
        result = personalized_plan(payload)
        cards = result.get("cards", []) if isinstance(result, dict) else []
        return ToolResult(
            tool_name="generate_learning_plan",
            success=True,
            data={
                "cards": cards,
                "count": len(cards),
            },
        )
    except Exception as e:
        return ToolResult(tool_name="generate_learning_plan", success=False, error=str(e))


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    "search_knowledge": {
        "name": "search_knowledge",
        "description": "???????????????????????",
        "parameters": {"query": "string", "limit": "int (optional, default 5)"},
        "requires_active_task": False,
        "function": search_knowledge_tool,
    },
    "run_diagnosis": {
        "name": "run_diagnosis",
        "description": "???? ActiveTask slots ???????????",
        "parameters": {},
        "requires_active_task": True,
        "function": run_diagnosis_tool,
    },
    "generate_quiz": {
        "name": "generate_quiz",
        "description": "?????????",
        "parameters": {"session_id": "string (optional)", "topic": "string (optional)", "count": "int (optional)"},
        "requires_active_task": False,
        "function": generate_quiz_tool,
    },
    "get_job_graph": {
        "name": "get_job_graph",
        "description": "????????",
        "parameters": {"job_role": "string (optional)"},
        "requires_active_task": False,
        "function": get_job_graph_tool,
    },
    "get_student_graph": {
        "name": "get_student_graph",
        "description": "??????????",
        "parameters": {"session_id": "string (optional)"},
        "requires_active_task": False,
        "function": get_student_graph_tool,
    },
    "generate_learning_plan": {
        "name": "generate_learning_plan",
        "description": "?????????/????",
        "parameters": {"session_id": "string (optional)"},
        "requires_active_task": False,
        "function": generate_learning_plan_tool,
    },
}

AVAILABLE_TOOLS = set(TOOL_REGISTRY.keys())
MAX_TOOL_ACTIONS_PER_TURN = 3


def execute_tool(tool_name, **kwargs):
    """Execute a tool by name. Returns ToolResult.
    
    Validates tool_name against whitelist before execution.
    """
    if tool_name not in TOOL_REGISTRY:
        return ToolResult(tool_name=tool_name, success=False,
                          error=f"Unknown tool: {tool_name}")

    tool_def = TOOL_REGISTRY[tool_name]
    fn = tool_def["function"]

    try:
        return fn(**kwargs)
    except TypeError as e:
        return ToolResult(tool_name=tool_name, success=False, error=str(e))
    except Exception as e:
        return ToolResult(tool_name=tool_name, success=False, error=str(e))


def get_available_tools_for_state(active_task=None):
    """Return list of tool names available given the current state."""
    available = []
    for name, defn in TOOL_REGISTRY.items():
        if defn.get("requires_active_task") and not active_task:
            continue
        available.append(name)
    return available
