# -*- coding: utf-8 -*-
"""Conversation Efficiency Scorer."""

def score_conversation_efficiency(trace, max_turns):
    """Score conversation efficiency metrics."""
    metrics = {}

    user_turns = [t for t in trace if t.get("role") == "user"]
    asst_turns = [t for t in trace if t.get("role") == "assistant"]

    metrics["total_turns"] = len(user_turns)
    metrics["max_turns"] = max_turns
    metrics["efficiency_ratio"] = len(user_turns) / max(max_turns, 1)

    # Check for repeated questions (system asking same thing twice)
    seen_questions = set()
    repeats = 0
    for t in asst_turns:
        content = t.get("content", "")[:80]
        if content in seen_questions:
            repeats += 1
        seen_questions.add(content)
    metrics["repeated_questions"] = repeats
    metrics["repeated_known_question_rate"] = repeats / max(len(asst_turns), 1)

    # Check for unnecessary questions (asking about known info)
    # Detect if system keeps asking clarification after user already answered
    user_responses = [t.get("content", "") for t in user_turns]
    unnecessary = 0
    clarification_phrases = ["what is", "tell me", "\u662f\u4ec0\u4e48", "\u544a\u8bc9\u6211", "\u77e5\u9053\u5417"]
    for i, t in enumerate(asst_turns):
        content = t.get("content", "").lower()
        if any(ph in content for ph in clarification_phrases):
            # Check if user already answered this in a previous turn
            if i > 0 and len(user_responses) > 0:
                # Simple heuristic: if the system asks a question and it's the 4th+ turn
                if i >= 3:
                    unnecessary += 1
    metrics["unnecessary_questions"] = unnecessary
    metrics["unnecessary_question_rate"] = unnecessary / max(len(asst_turns), 1)

    # User repetition rate: how often user repeats themselves
    user_repeats = 0
    for i in range(1, len(user_turns)):
        prev = user_turns[i-1].get("content", "")[:50] if i-1 < len(user_turns) else ""
        curr = user_turns[i].get("content", "")[:50]
        if prev and curr and prev == curr:
            user_repeats += 1
    metrics["user_repetition_rate"] = user_repeats / max(len(user_turns), 1)

    # Lost context: system asks about something already discussed
    # Simple check: are there clarifying questions after turn 4?
    lost_context = 0
    for i, t in enumerate(asst_turns):
        content = t.get("content", "").lower()
        asking_patterns = ["what is", "\u662f\u4ec0\u4e48", "\u544a\u8bc9\u6211", "\u786e\u8ba4", "\u8bf7\u95ee"]
        if any(pat in content for pat in asking_patterns) and i >= 3:
            lost_context += 1
    metrics["lost_context_rate"] = lost_context / max(len(asst_turns), 1)

    return {"metrics": metrics, "passed": [], "failed": [],
            "score": 1.0 if repeats == 0 and unnecessary <= 1 else 0.5, "total": 1}

