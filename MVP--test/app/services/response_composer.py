"""
Response Composer - Phase 5.

Composes unified natural-language responses with proper structure:
  1. Main answer (Markdown)
  2. Safety notice (leveled)
  3. Suggested questions (context-aware)
  4. Cards (collapsed refs)
  5. Debug info (hidden from users)
"""

from .llm_client import chat_completion, is_configured, LLMError
from .assist import assist


# ---------------------------------------------------------------------------
# Response mode detection
# ---------------------------------------------------------------------------

def _detect_response_mode(message, tool_results, active_task):
    """Detect which response mode to use based on tools executed."""
    tool_names = [r.tool_name if hasattr(r, "tool_name") else r.get("tool_name", "")
                  for r in tool_results]

    has_knowledge = "search_knowledge" in tool_names
    has_diagnosis = "run_diagnosis" in tool_names
    has_quiz = "generate_quiz" in tool_names
    has_plan = "generate_learning_plan" in tool_names

    if has_quiz:
        return "quiz_generation"
    if has_plan:
        return "learning_plan"
    if has_knowledge and has_diagnosis:
        return "mixed_knowledge_diagnosis"
    if has_diagnosis:
        diagnosis_data = _get_tool_data(tool_results, "run_diagnosis")
        if diagnosis_data.get("status") == "need_clarification":
            return "clarification"
        return "diagnosis_progress"
    if has_knowledge:
        return "knowledge_explanation"
    return "unsupported_question"


def _get_tool_data(tool_results, tool_name):
    for r in tool_results:
        data = r.data if hasattr(r, "data") else r.get("data", {})
        tn = r.tool_name if hasattr(r, "tool_name") else r.get("tool_name", "")
        if tn == tool_name:
            return data
    return {}


# ---------------------------------------------------------------------------
# Main compose function
# ---------------------------------------------------------------------------

def compose_response(message, tool_results, conversation_state=None, active_task=None, knowledge_refs=None):
    """Compose a unified response with proper structure."""
    results_list = [r.to_dict() if hasattr(r, "to_dict") else r for r in tool_results]
    mode = _detect_response_mode(message, tool_results, active_task)

    # ---- Build main answer by mode ----
    if mode == "knowledge_explanation":
        answer = _compose_knowledge(message, results_list, knowledge_refs=knowledge_refs)
    elif mode == "diagnosis_progress":
        answer = _compose_diagnosis(message, results_list, active_task)
    elif mode == "clarification":
        answer = _compose_clarification(message, results_list, active_task)
    elif mode == "mixed_knowledge_diagnosis":
        answer = _compose_mixed(message, results_list, active_task, knowledge_refs=knowledge_refs)
    elif mode == "quiz_generation":
        answer = _compose_quiz(results_list)
    elif mode == "learning_plan":
        answer = _compose_plan(results_list)
    else:
        answer = _compose_unsupported(message)

    # ---- Safety level ----
    safety = _compute_safety(message, results_list, active_task)

    # ---- Suggested questions ----
    suggested = _generate_suggested_questions(message, mode, results_list, active_task)

    # ---- Cards (foldable references) ----
    cards = _build_cards(results_list)

    # ---- Debug (internal only) ----
    debug = _build_debug(results_list, mode)

    result = {
        "answer": answer,
    }
    if safety:
        result["safety"] = safety
    if suggested:
        result["suggested_questions"] = suggested
    if cards:
        result["cards"] = cards
    result["_debug"] = debug

    return result


# ---------------------------------------------------------------------------
# Mode-specific composers
# ---------------------------------------------------------------------------

def _compose_knowledge(message, results_list, knowledge_refs=None):
    """knowledge_explanation: conclusion first, then explanation."""
    data = _get_kn_data(results_list)
    items = data.get("items", []) or []
    # Merge in external knowledge refs
    if knowledge_refs:
        seen = {i.get("id") or i.get("title") for i in items}
        for kr in knowledge_refs:
            kid = kr.get("id") or kr.get("title")
            if kid and kid not in seen:
                items.append(kr)
                seen.add(kid)

    if not items:
        return _compose_rag_miss(message)

    top = items[0]
    # Simple template: concise summary + key point
    content = top.get("content", "")
    title = top.get("title", "")

    # Build a structured answer
    lines = []
    if title:
        lines.append("**%s**" % title)
        lines.append("")
    # Take first 2-3 sentences as the core answer
    sentences = content.replace("\n", " ").split("?")
    core = "?".join(sentences[:3]) + "?" if len(sentences) > 3 else content[:400]
    lines.append(core)
    lines.append("")

    if len(items) > 1:
        ref_titles = [item.get("title", "") for item in items[1:4] if item.get("title")]
        if ref_titles:
            lines.append("---")
            lines.append("*References: %s*" % ", ".join(ref_titles))

    return "\n".join(lines)


def _compose_diagnosis(message, results_list, active_task):
    """diagnosis_progress: expand rule-based result into detailed 5-layer response via LLM."""
    data = _get_tool_data_s(results_list, "run_diagnosis")
    direct = data.get("direct_answer", "")
    pattern = data.get("matched_pattern", {})
    title = pattern.get("title", "") if isinstance(pattern, dict) else ""
    checks = data.get("first_checks", [])
    abilities = data.get("highlighted_abilities", [])
    gaps = data.get("knowledge_gaps", [])

    ctx_parts = []
    if active_task:
        slots = active_task.get("slots", {})
        known = []
        for k, v in slots.items():
            if isinstance(v, dict) and v.get("value", "unknown") != "unknown":
                known.append("- %s: %s" % (_slot_label(k), v["value"]))
        if known:
            ctx_parts.append("[Current Status]\n" + "\n".join(known))
    if title:
        ctx_parts.append("[Matched Pattern]\n%s" % title)
    if direct:
        ctx_parts.append("[Direct Answer from Rules]\n%s" % direct)
    if checks:
        ctx_parts.append("[First Checks]\n%s" % "; ".join(checks[:3]))
    if abilities:
        ctx_parts.append("[Highlighted Abilities]\n" + "; ".join(a.get("name", a.get("id", "")) for a in abilities[:5]))
    if gaps:
        ctx_parts.append("[Knowledge Gaps]\n" + "; ".join(g.get("topic", g.get("id", "")) for g in gaps[:5]))
    rule_context = "\n\n".join(ctx_parts)
    user_msg = ("Student asked: %s\n\n" % message) if message else ""
    user_msg += rule_context
    system_prompt = (
        "You are a mechatronics training AI assistant.\n\n"
        "FORMAT YOUR RESPONSE AS A DETAILED 5-LAYER STRUCTURED ANSWER:\n"
        "1) Direct Judgment: Clearly answer the core question with a definitive conclusion\n"
        "2) Diagnostic Analysis: Expand with inspection steps, possible causes, and reasoning\n"
        "3) Ability Mapping: Point out which job competency nodes and knowledge gaps are exposed\n"
        "4) Safety Reminder: Always remind safety first for wiring/power-up/equipment operations\n"
        "5) Next Steps: Give concrete, actionable training tasks or field verification directions\n\n"
        "End with 3-4 follow-up question suggestions.\n\n"
        "IMPORTANT: Your response MUST be detailed - at least 300 Chinese characters. "
        "Expand on the rule data, do not just repeat it. "
        "Write like an experienced vocational trainer teaching an apprentice."
    )
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
        llm_answer = chat_completion(messages, temperature=0.5)
        return llm_answer
    except (LLMError, Exception):
        lines = []
        if active_task:
            slots = active_task.get("slots", {})
            for k, v in slots.items():
                if isinstance(v, dict) and v.get("value", "unknown") != "unknown":
                    lines.append("- %s: %s" % (_slot_label(k), v["value"]))
        if direct:
            lines.append(direct)
        elif title:
            lines.append("This matches: **%s**" % title)
        if checks:
            lines.append("**Next step:** %s" % checks[0])
        return "\n".join(lines)


def _compose_clarification(message, results_list, active_task):
    """clarification: why needed + one question."""
    data = _get_tool_data_s(results_list, "run_diagnosis")
    questions = data.get("clarifying_questions", [])
    pattern = data.get("matched_pattern", {})
    title = pattern.get("title", "") if isinstance(pattern, dict) else ""

    lines = []
    if title:
        lines.append("I am looking at this as: **%s**." % title)
        lines.append("")

    if questions:
        q = questions[0]
        lines.append(q.get("question", "Can you provide more details?"))
    else:
        lines.append("Can you tell me more about the symptoms?")

    return "\n".join(lines)


def _compose_mixed(message, results_list, active_task, knowledge_refs=None):
    """mixed_knowledge_diagnosis: expand rule result + knowledge into detailed 5-layer response via LLM."""
    kn_data = _get_kn_data(results_list)
    dx_data = _get_tool_data_s(results_list, "run_diagnosis")
    items = kn_data.get("items", [])
    ctx_parts = []
    if items:
        top = items[0]
        ctx_parts.append("[Knowledge Base Entry]\n%s" % top.get("content", "")[:500])
    pattern = dx_data.get("matched_pattern", {})
    title = pattern.get("title", "") if isinstance(pattern, dict) else ""
    if title:
        ctx_parts.append("[Matched Pattern]\n%s" % title)
    direct = dx_data.get("direct_answer", "")
    if direct:
        ctx_parts.append("[Direct Answer]\n%s" % direct)
    checks = dx_data.get("first_checks", [])
    if checks:
        ctx_parts.append("[First Checks]\n%s" % "; ".join(checks[:3]))
    rule_context = "\n\n".join(ctx_parts)
    user_msg = ("Student asked: %s\n\n" % message) if message else ""
    user_msg += rule_context
    system_prompt = (
        "You are a mechatronics training AI assistant.\n\n"
        "FORMAT YOUR RESPONSE AS A DETAILED 5-LAYER STRUCTURED ANSWER:\n"
        "1) Direct Judgment: Clearly answer the core question with a definitive conclusion\n"
        "2) Diagnostic Analysis: Expand with inspection steps, possible causes, and reasoning\n"
        "3) Ability Mapping: Point out which job competency nodes and knowledge gaps are exposed\n"
        "4) Safety Reminder: Always remind safety first for wiring/power-up/equipment operations\n"
        "5) Next Steps: Give concrete, actionable training tasks or field verification directions\n\n"
        "End with 3-4 follow-up question suggestions.\n\n"
        "IMPORTANT: Your response MUST be detailed - at least 300 Chinese characters. "
        "Expand on the rule data, do not just repeat it. "
        "Write like an experienced vocational trainer teaching an apprentice."
    )
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
        return chat_completion(messages, temperature=0.5)
    except (LLMError, Exception):
        lines = []
        if items:
            top = items[0]
            lines.append(top.get("content", "")[:300])
        if active_task:
            lines.append("This relates to your current issue.")
            if checks:
                lines.append("**Next step:** %s" % checks[0])
        return "\n".join(lines)


def _compose_quiz(results_list):
    data = _get_kn_data(results_list)
    questions = data.get("questions", [])
    if questions:
        return "Here are %d quiz questions for you." % len(questions)
    return "I have prepared some questions for you."


def _compose_plan(results_list):
    data = _get_kn_data(results_list)
    cards = data.get("cards", [])
    if cards:
        return "Here is your personalized learning plan with %d items." % len(cards)
    return "I have generated a learning plan for you."


def _compose_unsupported(message):
    return "I understand you are asking about: %s. Let me try to help based on what I know." % (
        str(message)[:80])


def _compose_rag_miss(message):
    """RAG miss: provide a helpful fallback instead of just refusing."""
    return (
        "I do not have a specific entry for this in my knowledge base, but here is my understanding.\n\n"
        "If this involves specific equipment models or wiring parameters, please refer to the device manual."
    )


# ---------------------------------------------------------------------------
# Safety computation
# ---------------------------------------------------------------------------

def _compute_safety(message, results_list, active_task):
    """Compute safety level based on content and context."""
    text = str(message).lower() if message else ""

    # Check for high-risk keywords
    high_risk = ["rewire", "modify", "short", "bypass", "override"]
    medium_risk = ["connect", "wire", "power", "measure", "test", "check"]

    for kw in high_risk:
        if kw in text:
            return {
                "level": "warning",
                "text": "Warning: Before modifying wiring or circuits, disconnect power and confirm safety conditions."
            }

    for kw in medium_risk:
        if kw in text:
            return {
                "level": "notice",
                "text": "Safety notice: Ensure power is off before any wiring work. Confirm emergency stop and equipment status."
            }

    # If diagnosis tool was run, always include a notice
    tool_names = [r.tool_name if hasattr(r, "tool_name") else r.get("tool_name", "")
                  for r in (results_list if isinstance(results_list, list) else [])]
    if "run_diagnosis" in str(tool_names):
        return {
            "level": "notice",
            "text": "Safety notice: Power off before wiring. Confirm with instructor if unsure."
        }

    return None


# ---------------------------------------------------------------------------
# Suggested questions (context-aware)
# ---------------------------------------------------------------------------

def _generate_suggested_questions(message, mode, results_list, active_task):
    """Generate 2-3 context-relevant follow-up questions."""
    questions = []

    # Always include a task-continuation question if there is an active task
    if active_task:
        pending = active_task.get("pending_slot")
        if pending:
            questions.append("Continue with the current diagnosis")
        else:
            questions.append("Continue troubleshooting")

    # Mode-specific suggestions
    if mode == "knowledge_explanation":
        questions.append("How does this apply to my current setup?")
        questions.append("Can you give me a practical example?")
    elif mode in ("diagnosis_progress", "clarification"):
        questions.append("What should I check next?")
        questions.append("What if the symptom changes?")
    elif mode == "mixed_knowledge_diagnosis":
        questions.append("Continue with the diagnosis")
        questions.append("Explain this in more detail")

    # Deduplicate and limit to 3
    seen = set()
    unique = []
    for q in questions:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique[:3]


# ---------------------------------------------------------------------------
# Cards builder
# ---------------------------------------------------------------------------

def _build_cards(results_list):
    """Build collapsible reference cards from tool results."""
    cards = {}
    for r in results_list:
        data = r.get("data", {}) if isinstance(r, dict) else (r.data if hasattr(r, "data") else {})
        tn = r.get("tool_name", "") if isinstance(r, dict) else (r.tool_name if hasattr(r, "tool_name") else "")

        if tn == "search_knowledge":
            items = data.get("items", [])
            if items:
                cards["knowledge_refs"] = [
                    {"title": item.get("title", ""), "source": item.get("source", "")}
                    for item in items[:5] if item.get("title")
                ]
        elif tn == "run_diagnosis":
            abilities = data.get("highlighted_abilities", [])
            if abilities:
                cards["ability_hits"] = [
                    {"id": a.get("id", ""), "name": a.get("name", "")}
                    for a in abilities[:3]
                ]

    return cards if cards else None


# ---------------------------------------------------------------------------
# Debug info
# ---------------------------------------------------------------------------

def _build_debug(results_list, mode):
    """Build internal debug info (not shown to users)."""
    return {
        "mode": mode,
        "tool_count": len(results_list),
        "tools": [r.get("tool_name", "?") if isinstance(r, dict) else
                   (r.tool_name if hasattr(r, "tool_name") else "?")
                   for r in results_list],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_kn_data(results_list):
    for r in results_list:
        data = r.get("data", {}) if isinstance(r, dict) else (r.data if hasattr(r, "data") else {})
        tn = r.get("tool_name", "") if isinstance(r, dict) else (r.tool_name if hasattr(r, "tool_name") else "")
        if tn == "search_knowledge":
            return data
        # Also check quiz/plan results
        if tn in ("generate_quiz", "generate_learning_plan"):
            return data
    return {}


def _get_tool_data_s(results_list, tool_name):
    for r in results_list:
        tn = r.get("tool_name", "") if isinstance(r, dict) else (r.tool_name if hasattr(r, "tool_name") else "")
        if tn == tool_name:
            return r.get("data", {}) if isinstance(r, dict) else (r.data if hasattr(r, "data") else {})
    return {}


def _slot_label(slot_name):
    labels = {
        "sensor_led": "Sensor LED",
        "plc_input_led": "PLC input LED",
        "online_monitor": "Online monitor",
        "sensor_type": "Sensor type",
        "common_terminal": "Common terminal",
    }
    return labels.get(slot_name, slot_name)
