"""
Intent handlers — one handler per non‑diagnosis intent.

Each handler receives the raw chat payload plus the intent result,
calls the appropriate service modules, and returns a response dict
that follows the same shape as chat_message() for frontend consistency.
"""

import json
import logging
from pathlib import Path

from .assist import assist
from .data_loader import load_data, primary_job_profile
from .feedback import load_session_record
from .graph import build_ability_graph, build_student_ability_graph
from .learner_context import learner_context_pack
from .llm_client import LLMError, chat_completion, is_configured
from .personalized_plan import personalized_plan
from .quiz import personalized_quiz
from .retrieval import search_knowledge
from .safety import safety_notice


ROOT = Path(__file__).resolve().parents[2]
CLARIFY_PROMPT_PATH = ROOT / "prompts" / "clarify_prompt.md"
MAX_CLARIFY_ROUNDS = 3


# ── helpers ───────────────────────────────────────────────────────

def _base_result(payload, intent_result):
    """Build the common fields every handler should return."""
    session_id = payload.get("session_id")
    profile = primary_job_profile()
    learner = learner_context_pack(session_id)
    return {
        "session_id": learner.get("session_id") or session_id,
        "safety_notice": "",
        "learner_context": learner,
        "evidence_used": [],
        "reasoning_steps": [],
        "knowledge_refs": [],
        "ability_hits": [],
        "highlighted_abilities": [],
        "knowledge_gaps": [],
        "remediation_cards": [],
        "ability_knowledge_view": {},
        "matched_pattern": None,
        "fallback_used": True,
        "llm_configured": is_configured(),
        "llm_error": "",
        "intent": intent_result.get("intent"),
        "intent_source": intent_result.get("source"),
        "tool_suggestions": [
            {"id": "dashboard", "label": "查看学习驾驶舱"},
        ],
        "suggested_questions": [],
        "next_questions": [],
    }


logger = logging.getLogger(__name__)


def _llm_answer(system_content, user_content, temperature=0.3):
    """Attempt LLM call; return (answer, error_str)."""
    if not is_configured():
        logger.warning("LLM 未配置：请检查 .env 中 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 是否已设置")
        return None, "LLM 未配置"
    try:
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]
        answer = chat_completion(messages, temperature=temperature)
        if not answer or not answer.strip():
            logger.warning("LLM 返回了空内容")
            return None, "LLM 返回空内容"
        return answer, ""
    except LLMError as exc:
        logger.error("LLM 调用失败: %s", exc)
        return None, str(exc)


# ── clarification helpers ──────────────────────────────────────────

def _load_clarify_prompt():
    if CLARIFY_PROMPT_PATH.exists():
        return CLARIFY_PROMPT_PATH.read_text(encoding="utf-8")
    return ""


def _count_clarify_rounds(session_id):
    """Count how many clarification events exist in the current session."""
    if not session_id:
        return 0
    record = load_session_record(session_id)
    return sum(
        1 for event in record.get("events", [])
        if event.get("event_type") in {"clarify", "chat_message"}
        and event.get("intent") == "clarify"
    )


def _known_slots_from_context(context, assist_result):
    """Extract what the student has already told us from context and pattern."""
    slots = {}
    labels = {
        "sensor_led": "传感器动作灯",
        "plc_input_led": "PLC 输入指示灯",
        "online_monitor": "PLC 在线监控",
        "sensor_type": "传感器类型",
        "common_terminal": "PLC 输入公共端",
    }
    for key, label in labels.items():
        value = (context or {}).get(key)
        if value and str(value).lower() not in {"unknown", "", "未确认"}:
            slots[label] = value

    pattern = assist_result.get("matched_pattern") or {}
    missing_fields = set()
    for field in pattern.get("required_context", []):
        value = (context or {}).get(field)
        if not value or str(value).lower() in {"unknown", "", "未确认"}:
            missing_fields.add(field)

    return slots, list(missing_fields)


def generate_clarify_questions(message, assist_result, context, clarify_round=1, history=None):
    """
    Generate natural follow-up questions via LLM.
    Returns (questions_list, safety_notice, fallback_used).
    """
    if not is_configured():
        # Fall back to static questions from assist
        static = assist_result.get("clarifying_questions", [])
        questions = [
            {
                "id": f"C{clarify_round:02d}{i + 1}",
                "question": item.get("question", ""),
                "target_ability_id": item.get("field", ""),
                "why_needed": "",
            }
            for i, item in enumerate(static[:3])
        ]
        return questions, assist_result.get("safety_notice", ""), True

    prompt = _load_clarify_prompt()
    known_slots, missing_fields = _known_slots_from_context(context, assist_result)
    pattern = assist_result.get("matched_pattern") or {}

    abilities = [
        {"id": item.get("id"), "name": item.get("name")}
        for item in assist_result.get("highlighted_abilities", [])[:6]
    ]

    system = (
        f"{prompt}\n\n"
        "重要：你只输出 JSON，不要输出任何解释、markdown 或额外文字。"
        f"这是第 {clarify_round} 轮追问" + ("（最多 3 轮）。" if clarify_round >= 2 else "。")
    )
    # Build conversation history summary
    history_text = ""
    if history:
        recent = history[-4:]
        history_text = "\n".join(
            f"{item.get('role', 'user')}: {item.get('content', '')[:150]}"
            for item in recent
        )

    user = json.dumps(
        {
            "user_input": message,
            "recent_conversation": history_text or "（无历史对话）",
            "matched_pattern": {
                "title": pattern.get("title", ""),
                "typical_symptom": pattern.get("typical_symptom", ""),
            },
            "known_slots": known_slots,
            "missing_fields": missing_fields,
            "ability_nodes": abilities,
            "clarify_round": clarify_round,
            "instruction": (
                "请基于以上信息生成 1-3 个追问。"
                "注意：recent_conversation 包含了前几轮问答，学生可能已经回答了部分问题。"
                "只追问仍然未知的信息，不要重复问已经回答过的。"
                "追问要口语化、具体、像实训师傅在带教。"
                "每个追问说明为什么需要这些信息（对应什么能力点）。"
                f"{'如果学生已经回答了部分信息但仍然不够，请针对仍然缺失的信息追问，不要重复前几轮的问题。' if clarify_round > 1 else ''}"
                f"{'这是最后一轮追问，之后将给出诊断。问最关键的那个问题。' if clarify_round >= 2 else ''}"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )

    try:
        raw = chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.3,
            timeout=20,
        )
        # Parse JSON from LLM response
        text = str(raw or "").strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        parsed = json.loads(text)
        questions = parsed.get("questions", [])
        safety = parsed.get("safety_notice", "")
        if not questions:
            raise ValueError("empty questions")
        # Normalize question format
        normalized = [
            {
                "id": q.get("id", f"C{clarify_round:02d}{i + 1}"),
                "question": q.get("question", str(q)),
                "target_ability_id": q.get("target_ability_id", ""),
                "why_needed": q.get("why_needed", ""),
            }
            for i, q in enumerate(questions[:3])
        ]
        return normalized, safety, False
    except (LLMError, ValueError, json.JSONDecodeError, OSError):
        # Fall back to static questions
        static = assist_result.get("clarifying_questions", [])
        questions = [
            {
                "id": f"C{clarify_round:02d}{i + 1}",
                "question": item.get("question", ""),
                "target_ability_id": item.get("field", ""),
                "why_needed": "",
            }
            for i, item in enumerate(static[:3])
        ]
        return questions, assist_result.get("safety_notice", ""), True


def _best_effort_from_clarify(message, assist_result, context, payload, intent_result):
    """After max clarify rounds, give a best-effort diagnosis."""
    result = _base_result(payload, intent_result)
    pattern = assist_result.get("matched_pattern") or {}

    if pattern.get("direct_answer"):
        answer = (
            f"我已经问了 {MAX_CLARIFY_ROUNDS} 轮，先根据现有信息给你一个参考判断。\n\n"
            f"**可能方向**：{pattern.get('direct_answer', '')}\n\n"
        )
    else:
        answer = (
            f"我已经问了 {MAX_CLARIFY_ROUNDS} 轮，但信息还不够完整。\n\n"
            "建议你先确认以下几点，然后重新描述问题：\n"
        )

    first_checks = assist_result.get("first_checks", [])
    if first_checks:
        answer += "\n".join(f"- {check}" for check in first_checks[:3])

    answer += "\n\n你也可以在右侧面板的「现场状态」中填写传感器的灯、PLC 输入灯和在线监控的状态，我会给出更准确的判断。"

    result["answer"] = answer
    result["safety_notice"] = assist_result.get("safety_notice", "")
    result["evidence_used"] = [
        {"label": "匹配现象", "value": pattern.get("typical_symptom", ""), "source": pattern.get("source", "")}
    ]
    result["highlighted_abilities"] = assist_result.get("highlighted_abilities", [])
    result["knowledge_gaps"] = assist_result.get("knowledge_gaps", [])
    result["remediation_cards"] = assist_result.get("remediation_cards", [])
    result["ability_knowledge_view"] = assist_result.get("ability_knowledge_view", {})
    result["reasoning_steps"] = [
        f"已进行 {MAX_CLARIFY_ROUNDS} 轮澄清追问",
        f"匹配现象：{pattern.get('title', '输入信号排查')}",
        "证据有限，输出参考判断而非确定诊断",
    ]
    result["tool_suggestions"] = [
        {"id": "dashboard", "label": "查看学习驾驶舱"},
        {"id": "scenario", "label": "进入排故角色扮演"},
        {"id": "quiz", "label": "做自测验证"},
    ]
    result["suggested_questions"] = [
        "我先去确认一下，然后再来问你",
        "能在排故角色扮演中练这个问题吗？",
    ]
    result["next_questions"] = result["suggested_questions"]
    result["fallback_used"] = not is_configured()
    return result


# ── handlers ──────────────────────────────────────────────────────

def handle_clarify(payload, intent_result):
    """
    Handle vague/insufficient input with natural follow-up questions.

    1. Run assist() to understand what's known vs missing
    2. Generate natural follow-up questions via LLM (clarify_prompt.md)
    3. Fall back to static questions if LLM unavailable
    4. Track clarification rounds; after MAX_CLARIFY_ROUNDS, give best-effort diagnosis
    """
    message = payload.get("message") or payload.get("user_input") or ""
    context = payload.get("context", {}) or {}
    session_id = payload.get("session_id")
    result = _base_result(payload, intent_result)

    assist_result = assist({"user_input": message, "context": context})

    # Count previous rounds + 1 for this round
    clarify_round = _count_clarify_rounds(session_id) + 1

    # After max rounds, give best-effort diagnosis
    if clarify_round >= MAX_CLARIFY_ROUNDS:
        return _best_effort_from_clarify(message, assist_result, context, payload, intent_result)

    # Generate questions (LLM or static fallback)
    questions, safety, fallback = generate_clarify_questions(
        message, assist_result, context, clarify_round,
        history=payload.get("history", [])[-4:]
    )

    # Build natural response
    pattern = assist_result.get("matched_pattern") or {}
    pattern_title = pattern.get("title", "输入信号排查")

    if clarify_round == 1:
        intro = f"我先按「{pattern_title}」的情况来理解。目前信息还不够完整，想先确认几个关键信息：\n"
    else:
        intro = f"好的，我再确认一下（第 {clarify_round} 轮）。还需要搞清楚：\n"

    question_text = "\n".join(
        f"{i + 1}. **{q.get('question', '')}**"
        + (f"\n   > 为什么需要：{q.get('why_needed', '')}" if q.get("why_needed") else "")
        for i, q in enumerate(questions)
    )

    answer = intro + "\n" + question_text
    answer += "\n\n你也可以在右侧「现场状态」面板直接选择对应状态，我会更准确地判断。"

    result["answer"] = answer
    result["safety_notice"] = safety or assist_result.get("safety_notice", "")
    result["fallback_used"] = fallback
    result["reasoning_steps"] = [
        f"匹配现象：{pattern_title}",
        f"追问生成：{'LLM 动态生成' if not fallback else '规则模板'}",
    ]
    result["evidence_used"] = [
        {"label": "匹配现象", "value": pattern.get("typical_symptom", ""), "source": pattern.get("source", "")}
    ] if pattern else []
    result["highlighted_abilities"] = assist_result.get("highlighted_abilities", [])
    result["ability_knowledge_view"] = assist_result.get("ability_knowledge_view", {})
    result["tool_suggestions"] = [
        {"id": "dashboard", "label": "查看学习驾驶舱"},
        {"id": "scenario", "label": "进入排故角色扮演"},
    ]
    result["suggested_questions"] = [q.get("question", "") for q in questions if q.get("question")]
    result["next_questions"] = result["suggested_questions"]
    result["clarify_round"] = clarify_round

    return result



# ── 元问题检测：用户问知识库本身有什么内容 ──────────────────────────

_META_KEYWORDS = [
    "知识库都有哪些", "知识库包含什么", "知识库有什么", "你懂哪些",
    "你能做什么", "你可以帮我什么", "你能帮我什么", "你会什么",
    "有哪些内容", "有什么内容", "包含哪些", "涵盖哪些", "涉及哪些",
    "知识库的内容", "知识库内容", "知识库介绍", "介绍一下知识库",
    "能力图谱有哪些", "有哪些能力", "有哪些知识点",
    "你能干什么", "你能干嘛", "你可以做什么",
]


def _is_meta_question(message: str) -> bool:
    """检测是否在问系统/知识库本身的元问题。"""
    text = str(message or "")
    return any(kw in text for kw in _META_KEYWORDS)


def _build_knowledge_overview():
    """生成知识库内容概览。"""
    data = load_data()
    # 按能力域聚合
    from collections import OrderedDict
    domains = OrderedDict()
    for item in data["knowledge"]:
        aid = item.get("ability_node_id", "")
        ability = data["ability_by_id"].get(aid, {})
        domain_name = ability.get("name", aid) or "其他"
        if domain_name not in domains:
            domains[domain_name] = []
        domains[domain_name].append(f"{item.get('topic', '')}")

    lines = [
        f"知识库目前包含 **{len(data['knowledge'])} 条** 知识条目，覆盖 **{len(domains)} 个** 能力领域：\n"
    ]
    for domain, topics in domains.items():
        sample = "、".join(topics[:2])
        more = f" 等 {len(topics)} 条" if len(topics) > 2 else f"（{len(topics)} 条）"
        lines.append(f"- **{domain}**：{sample}{more}")

    lines.append(f"\n你可以直接问我具体知识，比如「NPN传感器怎么接线」「气缸不动了怎么排查」等。")
    return "\n".join(lines)


def handle_knowledge_qa(payload, intent_result):
    """
    Handle knowledge/concept questions.
    1. Search knowledge base
    2. Generate answer with sources (LLM) or return search results (fallback)
    """
    message = payload.get("message") or payload.get("user_input") or ""
    result = _base_result(payload, intent_result)

    # 元问题直接返回知识库概览
    if _is_meta_question(message):
        result["answer"] = _build_knowledge_overview()
        result["reasoning_steps"] = ["检测到元问题，返回知识库内容概览"]
        result["fallback_used"] = True
        return result

    knowledge_items = search_knowledge(message, limit=5)

    result["knowledge_refs"] = knowledge_items

    # Build evidence from search results
    result["evidence_used"] = [
        {
            "label": f"知识匹配: {item.get('id', '')} {item.get('topic', '')}",
            "value": item.get("content", "")[:120],
            "source": item.get("source", ""),
        }
        for item in knowledge_items[:4]
    ]
    result["reasoning_steps"] = [
        f"在知识库中检索到 {len(knowledge_items)} 条相关内容",
    ]

    if knowledge_items:
        knowledge_text = "\n\n".join(
            f"[{item.get('id')}] {item.get('topic', '')}\n{item.get('content', '')}\n来源: {item.get('source', '')}"
            for item in knowledge_items[:4]
        )
        system = (
            "你是机电一体化岗位培训 AI。请基于以下知识库内容回答学生的问题。"
            "回答要准确、简洁、有依据。"
            "涉及接线、通电、设备操作时，先提醒安全。"
        )
        user = f"学生问题：{message}\n\n可参考的知识库内容：\n{knowledge_text}"
    else:
        # 检索为空时，让 LLM 用自身知识自由回答，开头注明知识库暂无相关条目
        system = (
            "你是机电一体化岗位培训 AI。"
            "当前知识库中没有直接匹配的内容，但你可以用自己的专业知识回答学生的问题。"
            "回答要准确、简洁、有依据。"
            "涉及接线、通电、设备操作时，必须优先提醒安全规范。"
        )
        user = (
            f"学生问题：{message}\n\n"
            "注意：知识库中暂未检索到相关内容，请基于你的专业知识直接回答。"
            "在回答开头用一句话简要说明「知识库暂无相关条目，以下为通用知识参考」。"
        )

    answer, error = _llm_answer(system, user)
    if answer:
        result["fallback_used"] = False
        result["answer"] = answer
    else:
        result["llm_error"] = error
        if knowledge_items:
            top = knowledge_items[0]
            result["answer"] = (
                f"关于「{message}」，知识库中最相关的内容是：\n\n"
                f"**{top.get('topic', '')}**\n{top.get('content', '')}\n\n"
                f"来源：{top.get('source', '')}"
            )
        else:
            result["answer"] = f"抱歉，知识库中暂时没有找到关于「{message}」的相关内容。你可以换个关键词试试，或者描述一下具体的实训场景。"

    result["suggested_questions"] = [
        f"能再详细讲讲「{item.get('topic', '')}」吗？"
        for item in knowledge_items[:3] if item.get("topic")
    ] or ["这个知识点对应什么岗位能力？"]
    result["next_questions"] = result["suggested_questions"]

    return result


def handle_quiz(payload, intent_result):
    """
    Handle quiz/test generation requests.
    Generates personalized quiz based on session context.
    """
    message = payload.get("message") or payload.get("user_input") or ""
    session_id = payload.get("session_id")
    result = _base_result(payload, intent_result)

    quiz_data = personalized_quiz({
        "session_id": session_id,
        "user_input": message,
        "limit": 4,
    })

    questions = quiz_data.get("questions", [])
    if questions:
        question_lines = []
        for i, q in enumerate(questions, 1):
            question_lines.append(
                f"**{i}. {q.get('question', '')}**\n"
                + "\n".join(
                    f"  {opt.get('id', '')}. {opt.get('text', '')}"
                    for opt in (q.get("options") or [])
                )
                + f"\n\n<details><summary>查看答案</summary>\n"
                + f"正确答案：{q.get('correct_answer', '')}\n"
                + f"{q.get('explanation', '')}\n"
                + f"知识点：{q.get('knowledge_id', '')} {q.get('knowledge_topic', '')}\n"
                + "</details>\n"
            )
        result["answer"] = (
            f"根据你的学习情况，生成了 {len(questions)} 道练习题：\n\n"
            + "\n---\n".join(question_lines)
            + "\n完成题目后可以告诉我答案，我来帮你分析薄弱点。"
        )
    else:
        result["answer"] = "暂时无法根据你的学习记录生成个性化练习题。建议先进行一次对话或自测，系统会根据薄弱点出题。"

    result["reasoning_steps"] = [
        quiz_data.get("generation_mode", "knowledge_rule_template"),
        f"生成了 {len(questions)} 道个性化练习题",
    ]
    result["tool_suggestions"] = [
        {"id": "quiz", "label": "做预设评分题验证"},
        {"id": "dashboard", "label": "查看学习驾驶舱"},
        {"id": "plan", "label": "生成个人培养方案"},
    ]
    result["suggested_questions"] = [
        "帮我评判我的答题结果",
        "这道题的原理能详细讲讲吗？",
        "再做一道更难的同类型题",
    ]
    result["next_questions"] = result["suggested_questions"]
    return result


def handle_graph(payload, intent_result):
    """
    Handle competency graph / job ability queries.
    Returns the job ability graph and student ability graph.
    """
    session_id = payload.get("session_id")
    result = _base_result(payload, intent_result)

    job_graph = build_ability_graph()
    student_graph = build_student_ability_graph(session_id) if session_id else None

    result["ability_knowledge_view"] = {"graph": job_graph}

    node_names = [n.get("label", "") for n in job_graph.get("nodes", [])[:6]]
    result["answer"] = (
        "以下是「自动化生产线装调与运维技术员」岗位的能力图谱：\n\n"
        + "\n".join(f"- {name}" for name in node_names if name)
        + "\n\n你可以在右侧面板查看完整的岗位能力图谱和个人能力图谱。"
        + "点击任意能力节点可以查看详情和训练建议。"
    )

    result["reasoning_steps"] = [
        f"岗位图谱包含 {len(job_graph.get('nodes', []))} 个能力节点",
        "节点按岗位核心/行业高频/常规/薄弱等状态着色",
    ]
    result["tool_suggestions"] = [
        {"id": "job_graph", "label": "查看岗位能力图谱"},
        {"id": "student_graph", "label": "查看个人能力图谱"},
        {"id": "dashboard", "label": "学习驾驶舱"},
    ]
    result["suggested_questions"] = [
        f"「{name}」这个能力具体怎么训练？" for name in node_names[:2] if name
    ] + ["我的薄弱点在哪里？"]
    result["next_questions"] = result["suggested_questions"]

    if session_id:
        result["student_graph"] = student_graph

    return result


def handle_learning_path(payload, intent_result):
    """
    Handle learning path / training plan requests.
    Generates a personalized training plan.
    """
    session_id = payload.get("session_id")
    result = _base_result(payload, intent_result)

    plan = personalized_plan({
        "session_id": session_id,
        "plan_mode": "staged",
    })

    today = plan.get("today_training_sheet") or {}
    stages = plan.get("learning_plan") or []

    lines = ["根据你的学习记录和薄弱点，以下是**个人培养方案**：\n"]

    if today:
        lines.append(f"### 今日训练单：{today.get('title', '')}")
        lines.append(f"目标：{today.get('objective', '')}")
        lines.append("")
        for step in (today.get("steps") or [])[:4]:
            lines.append(f"- **{step.get('title', '')}**（{step.get('minutes', '-')} 分钟）：{step.get('action', '')}")

    if stages:
        lines.append("\n### 阶段方案")
        for stage in stages[:3]:
            lines.append(
                f"- **{stage.get('stage_title', '')}**"
                f"（掌握度 {stage.get('mastery_score', '-')}）：{stage.get('text_explanation', '')}"
            )

    lines.append(f"\n{plan.get('next_review', '')}")

    result["answer"] = "\n".join(lines)
    result["reasoning_steps"] = [
        f"方案模式：{plan.get('plan_mode', 'staged')}",
        f"依据来源：{plan.get('source', 'student_graph')}",
        f"包含 {len(stages)} 个阶段，今日训练 {len(today.get('steps', []))} 步",
    ]
    result["safety_notice"] = plan.get("safety_notice", "")
    result["tool_suggestions"] = [
        {"id": "plan", "label": "查看完整培养方案"},
        {"id": "tasks", "label": "查看实训任务"},
        {"id": "quiz", "label": "做自测验证"},
    ]
    result["suggested_questions"] = [
        "我想先做今天的训练单",
        "第一个阶段的知识点能详细讲讲吗？",
        "完成训练后怎么反馈？",
    ]
    result["next_questions"] = result["suggested_questions"]
    return result
