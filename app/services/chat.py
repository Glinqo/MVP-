import json

from .assist import assist
from .data_loader import primary_job_profile
from .feedback import append_session_event
from .graph import build_student_ability_graph
from .learner_context import format_context_for_prompt, learner_context_pack
from .llm_client import LLMError, chat_completion, is_configured
from .retrieval import search_knowledge
from .safety import safety_notice


TOOLS = [
    {"id": "dashboard", "label": "学习驾驶舱"},
    {"id": "job_graph", "label": "岗位能力图谱"},
    {"id": "student_graph", "label": "个人能力图谱"},
    {"id": "graph", "label": "当前问题图谱"},
    {"id": "knowledge", "label": "知识缺口"},
    {"id": "tasks", "label": "实训任务"},
    {"id": "quiz", "label": "自测"},
    {"id": "scenario", "label": "排故角色扮演"},
    {"id": "plan", "label": "个人培养方案"},
    {"id": "teacher", "label": "教师摘要"},
]


def welcome_questions():
    return [
        "传感器动作灯亮但 PLC 没输入，应该先查哪里？",
        "我怎么判断 NPN/PNP 和 PLC 公共端是否匹配？",
        "PLC 输入灯亮但在线监控不变，可能是什么问题？",
        "我适合先补哪几个岗位能力？",
    ]


def chat_start(payload=None):
    payload = payload or {}
    profile = primary_job_profile()
    role_name = profile.get("role_name", "自动化生产线装调与运维技术员")
    learner_stage = profile.get("learner_stage", "职业新人")
    focus_task = profile.get("mvp_focus_task", "传感器 NPN/PNP 接线与 PLC 输入信号排查")
    context_pack = learner_context_pack(payload.get("session_id"))
    return {
        "session_id": context_pack.get("session_id"),
        "job_profile": profile,
        "learner_context": context_pack,
        "welcome": (
            f"你好，我会按“{role_name} / {learner_stage}”的岗位要求来回答。"
            f"当前重点训练任务是：{focus_task}。你可以直接描述问题；"
            "如果涉及接线、通电监控或设备动作，我会先提醒安全，再帮你定位能力和知识缺口。"
        ),
        "suggested_questions": welcome_questions(),
        "tool_suggestions": TOOLS,
        "llm_configured": is_configured(),
    }


def compact_for_prompt(items, limit=6):
    return items[:limit] if isinstance(items, list) else []


def build_system_prompt(profile):
    return (
        "你是面向职业新人的机电一体化岗位培训 AI。"
        "你服务的默认岗位是自动化生产线装调与运维技术员，场景聚焦传感器 NPN/PNP 接线与 PLC 输入信号排查。"
        "你的目标不是简单回答问题，而是帮助学生完成问题诊断、"
        "能力提升和学习路径规划。"
        "回答必须先直接回应用户问题，再指出需要补充的现场证据或下一步检查。"
        "涉及接线、通电、PLC 监控、传感器调试、气缸动作、设备排故时，必须先提醒安全。"
        "不要指导绕过安全回路、短接保护或带电冒险操作。"
        "专业结论优先依据给定知识条目、能力节点和问题模式；不要编造来源、设备型号或教材页码。"
        "你可以解释评分结果，但不得自由评分，也不得覆盖规则评分。"
        "回答末尾用简短列表给出 2 到 4 个更有价值的追问建议。"
        f"\n岗位画像：{json.dumps(profile, ensure_ascii=False)}"
    )


def build_user_prompt(message, assist_result, learner_context=None):
    context = {
        "matched_pattern": assist_result.get("matched_pattern"),
        "safety_notice": assist_result.get("safety_notice"),
        "clarifying_questions": assist_result.get("clarifying_questions"),
        "direct_answer_from_rules": assist_result.get("direct_answer"),
        "first_checks": assist_result.get("first_checks"),
        "fault_candidates": assist_result.get("fault_candidates"),
        "highlighted_abilities": compact_for_prompt(assist_result.get("highlighted_abilities")),
        "knowledge_gaps": compact_for_prompt(assist_result.get("knowledge_gaps")),
        "remediation_cards": compact_for_prompt(assist_result.get("remediation_cards")),
    }
    return (
        f"用户问题：{message}\n"
        f"学习者上下文：\n{format_context_for_prompt(learner_context)}\n"
        "以下是本地规则和知识库分析结果，请基于它回答，允许用更自然的语言组织，但不要推翻规则结果：\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def fallback_answer(assist_result):
    if assist_result.get("status") == "need_clarification":
        questions = [item.get("question", "") for item in assist_result.get("clarifying_questions", [])]
        question_text = "；".join(q for q in questions if q)
        return (
            f"我先按“{assist_result.get('matched_pattern', {}).get('title', '输入信号排查')}”理解。"
            "目前信息还不够完整，但可以先从安全检查和三联状态对照入手。"
            f"请补充：{question_text}"
        )

    first_checks = assist_result.get("first_checks", [])
    checks = "；".join(first_checks[:3])
    return f"{assist_result.get('direct_answer', '')} 先检查：{checks}"


def suggested_questions_from_assist(assist_result):
    if assist_result.get("status") == "need_clarification":
        return [item.get("question") for item in assist_result.get("clarifying_questions", []) if item.get("question")][:3]

    ability_questions = []
    for ability in assist_result.get("highlighted_abilities", [])[:3]:
        name = ability.get("name") or ability.get("id")
        ability_questions.append(f"我该怎么补上“{name}”？")
    base = [
        "这个问题最可能出在接线、公共端还是程序地址？",
        "我下一步实训应该做哪一个任务？",
    ]
    return (ability_questions + base)[:4]


def tool_suggestions_from_assist(assist_result):
    suggestions = [
        {"id": "dashboard", "label": "查看学习驾驶舱"},
        {"id": "graph", "label": "查看当前问题图谱"},
        {"id": "student_graph", "label": "更新个人能力图谱"},
    ]
    if assist_result.get("knowledge_gaps"):
        suggestions.append({"id": "knowledge", "label": "查看知识缺口"})
    if assist_result.get("remediation_cards"):
        suggestions.append({"id": "tasks", "label": "生成实训任务卡"})
    suggestions.append({"id": "scenario", "label": "进入排故角色扮演"})
    suggestions.append({"id": "quiz", "label": "做自测验证"})
    suggestions.append({"id": "plan", "label": "生成个人培养方案"})
    return suggestions[:5]


def evidence_from_context(context):
    labels = {
        "sensor_led": "传感器动作灯",
        "plc_input_led": "PLC 输入灯",
        "online_monitor": "PLC 在线监控",
        "sensor_type": "传感器类型",
        "common_terminal": "PLC 输入公共端",
    }
    evidence = []
    for key, label in labels.items():
        value = (context or {}).get(key)
        if value and str(value).lower() != "unknown":
            evidence.append({"label": label, "value": value, "source": "student_context"})
    return evidence


def evidence_used_from_assist(assist_result, context):
    pattern = assist_result.get("matched_pattern") or {}
    evidence = []
    if pattern.get("typical_symptom"):
        evidence.append(
            {
                "label": "匹配现象",
                "value": pattern.get("typical_symptom"),
                "source": pattern.get("source"),
            }
        )
    evidence.extend(evidence_from_context(context))
    for ability in assist_result.get("highlighted_abilities", [])[:3]:
        evidence.append(
            {
                "label": f"命中能力: {ability.get('name', ability.get('id'))}",
                "value": ability.get("reason", ""),
                "source": ability.get("source"),
            }
        )
    for item in assist_result.get("knowledge_gaps", [])[:3]:
        evidence.append(
            {
                "label": f"知识引用: {item.get('id')}",
                "value": item.get("topic") or item.get("content"),
                "source": item.get("source"),
            }
        )
    return evidence[:8]


def reasoning_steps_from_assist(assist_result):
    steps = []
    if assist_result.get("safety_notice"):
        steps.append("先确认安全边界：接线、拆线和通电监控前必须完成断电、急停、气源和教师确认。")
    pattern = assist_result.get("matched_pattern") or {}
    if pattern.get("title"):
        steps.append(f"把学生输入归入典型现象：{pattern.get('title')}。")
    if assist_result.get("status") == "need_clarification":
        questions = [item.get("question", "") for item in assist_result.get("clarifying_questions", [])]
        steps.append(f"当前证据不足，优先补充：{'；'.join(q for q in questions if q)}。")
    else:
        first_checks = assist_result.get("first_checks", [])
        if first_checks:
            steps.append(f"按先易后难排查：{first_checks[0]}")
        if len(first_checks) > 1:
            steps.append(f"再验证关键匹配关系：{first_checks[1]}")
        if assist_result.get("fault_candidates"):
            steps.append(f"候选原因优先级：{'；'.join(assist_result.get('fault_candidates', [])[:3])}。")
    return steps[:5]


def knowledge_refs_from_assist(message, assist_result):
    refs = list(assist_result.get("knowledge_gaps", []) or [])
    seen = {item.get("id") for item in refs}
    for item in search_knowledge(message, limit=4):
        if item.get("id") not in seen:
            refs.append(item)
            seen.add(item.get("id"))
    return refs[:6]


def chat_message(payload):
    payload = payload or {}
    message = payload.get("message") or payload.get("user_input") or ""
    context = payload.get("context", {}) or {}
    session_id = payload.get("session_id")
    profile = primary_job_profile()
    learner_context = learner_context_pack(session_id)
    assist_result = assist({"user_input": message, "context": context})
    evidence_used = evidence_used_from_assist(assist_result, context)
    reasoning_steps = reasoning_steps_from_assist(assist_result)
    knowledge_refs = knowledge_refs_from_assist(message, assist_result)
    next_questions = suggested_questions_from_assist(assist_result)

    fallback_used = True
    llm_error = ""
    answer = fallback_answer(assist_result)

    if is_configured():
        history = payload.get("history", [])[-8:]
        messages = [{"role": "system", "content": build_system_prompt(profile)}]
        for item in history:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": str(content)})
        messages.append({"role": "user", "content": build_user_prompt(message, assist_result, learner_context)})
        try:
            answer = chat_completion(messages)
            fallback_used = False
        except LLMError as exc:
            llm_error = str(exc)

    notice = assist_result.get("safety_notice") or safety_notice(message)
    result = {
        "session_id": learner_context.get("session_id") or payload.get("session_id"),
        "answer": answer,
        "safety_notice": notice,
        "learner_context": learner_context,
        "evidence_used": evidence_used,
        "reasoning_steps": reasoning_steps,
        "knowledge_refs": knowledge_refs,
        "ability_hits": assist_result.get("highlighted_abilities", []),
        "next_questions": next_questions,
        "suggested_questions": next_questions,
        "tool_suggestions": tool_suggestions_from_assist(assist_result),
        "highlighted_abilities": assist_result.get("highlighted_abilities", []),
        "knowledge_gaps": assist_result.get("knowledge_gaps", []),
        "remediation_cards": assist_result.get("remediation_cards", []),
        "ability_knowledge_view": assist_result.get("ability_knowledge_view", {}),
        "matched_pattern": assist_result.get("matched_pattern"),
        "fallback_used": fallback_used,
        "llm_configured": is_configured(),
        "llm_error": llm_error,
    }

    if session_id:
        append_session_event(
            session_id,
            {
                "event_type": "chat_message",
                "message": message,
                "matched_pattern": assist_result.get("matched_pattern"),
                "highlighted_abilities": assist_result.get("highlighted_abilities", []),
                "knowledge_gaps": assist_result.get("knowledge_gaps", []),
                "remediation_cards": assist_result.get("remediation_cards", []),
                "recommended_path": [item.get("title") for item in assist_result.get("remediation_cards", []) if item.get("title")],
            },
        )
        result["student_graph"] = build_student_ability_graph(session_id)
        result["learner_context"] = learner_context_pack(session_id)

    return result
