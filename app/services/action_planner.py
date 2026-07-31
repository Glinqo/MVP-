"""
Action Planner - Phase 3.

LLM-based action planner for complex/ambiguous messages that
the Conversation Policy cannot handle with local rules.
Outputs structured JSON only; does NOT generate a user-facing answer.
"""

import json
from .llm_client import chat_completion, is_configured, LLMError
from .conversation_tools import TOOL_REGISTRY, AVAILABLE_TOOLS, MAX_TOOL_ACTIONS_PER_TURN


_ACTION_PLANNER_SYSTEM = """You are an action planner for an industrial training AI.
Based on the user message and current conversation context, decide which tools to execute.

Available tools:
- search_knowledge: Search the knowledge base for concepts, principles, wiring etc.
- run_diagnosis: Run fault diagnosis based on current task state.
- generate_quiz: Generate personalized quiz questions.
- get_job_graph: Get the job ability graph.
- get_student_graph: Get the student ability graph.
- generate_learning_plan: Generate a personalized learning plan.

Rules:
1. Output ONLY a JSON object, no other text.
2. You may select 1-3 tools maximum.
3. If the user is asking a knowledge question, use search_knowledge.
4. If there is an active diagnosis task and the message is about troubleshooting, use run_diagnosis.
5. If the user asks for both explanation AND diagnosis, include both tools.
6. Set preserve_active_task to true when the current task should continue.
7. Tool names MUST be from the available tools list exactly.

Output format:
{
  "actions": [
    {"tool": "search_knowledge", "args": {"query": "..."}},
    {"tool": "run_diagnosis", "args": {}}
  ],
  "preserve_active_task": true,
  "confidence": 0.9
}
"""


def plan_actions(message, conversation_state=None, active_task=None, slots=None, history=None):
    """Use LLM to plan actions for complex messages.
    
    Returns a dict with actions list, or a fallback for errors.
    """
    if not is_configured():
        return _fallback_plan(message, active_task)

    # Build context summary
    context_lines = []
    if active_task:
        context_lines.append("Active task: " + str(active_task.get("type", "unknown")))
        context_lines.append("Task topic: " + str(active_task.get("topic", "")))
        context_lines.append("Task status: " + str(active_task.get("status", "unknown")))
    if slots:
        known = {k: v.get("value", v) if isinstance(v, dict) else v
                 for k, v in slots.items()
                 if (isinstance(v, dict) and v.get("value", "unknown") != "unknown") or
                    (not isinstance(v, dict) and v and v != "unknown")}
        if known:
            context_lines.append("Known slots: " + json.dumps(known, ensure_ascii=False))
    
    context_summary = "\n".join(context_lines) if context_lines else "No active task or slots."

    user_content = f"""User message: {message}

Current state:
{context_summary}

Recent history (last 4 messages):
{_format_history(history)}

Plan the next actions."""

    messages = [
        {"role": "system", "content": _ACTION_PLANNER_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    try:
        raw = chat_completion(messages, temperature=0.0, timeout=15)
        parsed = _parse_plan(raw)
        if parsed and parsed.get("actions"):
            return _validate_plan(parsed)
    except (LLMError, json.JSONDecodeError, ValueError):
        pass

    return _fallback_plan(message, active_task)


def _format_history(history):
    if not history:
        return "(none)"
    lines = []
    for item in history[-4:]:
        role = item.get("role", "?")
        content = str(item.get("content", ""))[:100]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _parse_plan(raw):
    """Parse LLM response into JSON."""
    text = raw.strip()
    # Try to extract JSON from response
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    return None


def _validate_plan(plan):
    """Validate and sanitize the plan."""
    actions = plan.get("actions", [])
    valid_actions = []
    for action in actions[:MAX_TOOL_ACTIONS_PER_TURN]:
        tool = action.get("tool", "")
        if tool in AVAILABLE_TOOLS:
            valid_actions.append({
                "tool": tool,
                "args": action.get("args", {}),
            })
    return {
        "actions": valid_actions,
        "preserve_active_task": bool(plan.get("preserve_active_task", True)),
        "confidence": float(plan.get("confidence", 0.5)),
        "mode": "tool_actions" if valid_actions else "defer_to_planner",
    }


def _fallback_plan(message, active_task):
    """Fallback when LLM is unavailable."""
    if active_task:
        return {
            "actions": [{"tool": "run_diagnosis", "args": {}}],
            "preserve_active_task": True,
            "confidence": 0.5,
            "mode": "continue_task",
        }
    # Default: search knowledge
    return {
        "actions": [{"tool": "search_knowledge", "args": {"query": str(message)}}],
        "preserve_active_task": False,
        "confidence": 0.3,
        "mode": "tool_actions",
    }


def plan_initial_learning(assessment_result):
    """Generate a learning plan based on assessment results. Stage 3."""
    ability_scores = assessment_result.get("ability_scores", {})
    weak = assessment_result.get("weak_abilities", [])
    strong = assessment_result.get("strong_abilities", [])

    stages = []
    if weak:
        stages.append({
            "title": "基础巩固",
            "description": "针对薄弱环节的系统学习",
            "abilities": weak,
            "duration_days": len(weak) * 2,
            "actions": [{"type": "learn", "ability_id": a, "priority": 3} for a in weak],
        })
    if strong:
        stages.append({
            "title": "能力拓展",
            "description": "基于强项的进阶训练",
            "abilities": strong,
            "duration_days": len(strong) * 1,
            "actions": [{"type": "practice", "ability_id": a, "priority": 1} for a in strong],
        })
    middle = [a for a in ability_scores if a not in weak and a not in strong]
    if middle:
        stages.append({
            "title": "常规训练",
            "description": "巩固中等掌握度能力",
            "abilities": middle,
            "duration_days": len(middle),
            "actions": [{"type": "review", "ability_id": a, "priority": 2} for a in middle],
        })

    priority = weak + [a for a in ability_scores if a not in weak and a not in strong] + strong
    return {
        "session_id": assessment_result.get("session_id", ""),
        "job_role": assessment_result.get("job_role", ""),
        "total_score": assessment_result.get("total_score", 0),
        "weak_abilities": weak,
        "strong_abilities": strong,
        "priority_abilities": priority,
        "stages": stages,
        "total_days": sum(s.get("duration_days", 0) for s in stages),
    }
