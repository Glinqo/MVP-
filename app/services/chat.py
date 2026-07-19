import json

from .assist import assist
from .data_loader import primary_job_profile, job_profile_by_id
from .feedback import append_session_event
from .graph import build_student_ability_graph
from .intent import classify_intent
from .intent_handlers import (
    handle_clarify,
    handle_graph,
    handle_knowledge_qa,
    handle_learning_path,
    handle_quiz,
    generate_clarify_questions,
)
from .learner_context import format_context_for_prompt, learner_context_pack
from .llm_client import LLMError, chat_completion, is_configured
from .retrieval import search_knowledge
from .safety import safety_notice
from .conversation_state import (
    get_conversation_context,
    append_user_message,
    append_assistant_message,
    get_all_messages,
    load_conversation_state,
)
from .conversation_slots import (
    extract_slots_from_message,
    resolve_pending_slot_answer,
    apply_slot_updates,
    get_missing_slots,
    merge_ui_context_into_slots,
    slots_to_assist_context,
    slots_summary,
)
from .conversation_policy import decide_next_actions
from .conversation_tools import execute_tool
from .action_planner import plan_actions
from .response_composer import compose_response
from .conversation_task import (
    start_task,
    get_active_task,
    get_task_slots,
    set_task_slots,
    get_pending_slot,
    set_pending_slot,
    clear_pending_slot,
    looks_like_task_continuation,
    task_summary,
)


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


def welcome_questions(job_role=None):
    from .retrieval import search_knowledge
    from .data_loader import job_profile_by_id, primary_job_profile
    profile = job_profile_by_id(job_role) if job_role else primary_job_profile()
    job_name = profile.get("role_name", "当前岗位")
    abilities = profile.get("core_abilities", [])[:3]
    questions = [
        f"{job_name}岗位的核心安全规范有哪些？",
        "我该如何理解本岗位的技术图纸和工艺文件？",
    ]
    if abilities:
        questions.append(f"{job_name}岗位中{abilities[0]}需要掌握哪些知识？")
    return questions[:3]

def chat_start(payload=None):
    payload = payload or {}
    job_role = payload.get("job_role")
    profile = job_profile_by_id(job_role) if job_role else primary_job_profile()
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
        "suggested_questions": welcome_questions(job_role),
        "tool_suggestions": TOOLS,
        "llm_configured": is_configured(),
        "conversation_messages": get_all_messages(context_pack.get("session_id")) if context_pack.get("session_id") else [],
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


def suggested_questions_from_assist(assist_result, job_role=None):
    if assist_result.get("status") == "need_clarification":
        return [item.get("question") for item in assist_result.get("clarifying_questions", []) if item.get("question")][:3]
    ability_questions = []
    for ability in assist_result.get("highlighted_abilities", [])[:3]:
        name = ability.get("name") or ability.get("id")
        ability_questions.append(f"我该怎么补上“{name}”？")
    base = [
        "这个问题最可能出在哪里？",
        "我下一步实训应该做哪个任务？",
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


def knowledge_refs_from_assist(message, assist_result, job_role=None):
    refs = list(assist_result.get("knowledge_gaps", []) or [])
    seen = {item.get("id") for item in refs}
    for item in search_knowledge(message, limit=4, job_role=job_role):
        if item.get("id") not in seen:
            refs.append(item)
            seen.add(item.get("id"))
    return refs[:6]


def chat_message(payload):

    payload = payload or {}
    message = payload.get("message") or payload.get("user_input") or ""
    context = payload.get("context", {}) or {}
    session_id = payload.get("session_id")
    job_role = payload.get("job_role")
    profile = job_profile_by_id(job_role) if job_role else primary_job_profile()
    learner_context = learner_context_pack(session_id)

    # ---- Phase 2 Step 0: Record user message ----
    if session_id and message:
        append_user_message(session_id, message)

    # ---- Phase 2 Step 1: Resolve pending slot (highest priority) ----
    pending_slot = get_pending_slot(session_id) if session_id else None
    if pending_slot and message:
        slot_name, slot_val = resolve_pending_slot_answer(pending_slot, message)
        if slot_name:
            task_slots = get_task_slots(session_id)
            task_slots = apply_slot_updates(task_slots, {slot_name: slot_val})
            set_task_slots(session_id, task_slots)
            clear_pending_slot(session_id)

    # ---- Phase 2 Step 2: Build initial effective context ----
    active_task = get_active_task(session_id) if session_id else None
    effective_context = context

    # ---- Phase 2 Step 3: Task-first routing ----
    history = get_conversation_context(session_id, limit=8) if session_id else []
    intent_result = None
    intent = "diagnosis"

    if active_task and looks_like_task_continuation(message, True):
        intent = active_task.get("type", "diagnosis")
        intent_result = {"intent": intent, "source": "task_continuation"}
    else:
        intent_result = classify_intent(message, history=history, context=effective_context)
        intent = intent_result.get("intent", "diagnosis")

    # ---- Phase 2 Step 4: Start new task for new diagnosis ----
    if intent == "diagnosis" and not active_task:
        pattern = {}
        if intent_result and intent_result.get("source") != "task_continuation":
            pre = assist({"user_input": message, "context": effective_context})
            pattern = pre.get("matched_pattern", {})
        start_task(
            session_id,
            task_type="diagnosis",
            topic=pattern.get("title", message[:40]) if pattern else message[:40],
            matched_pattern_id=pattern.get("id") if pattern else None,
        )
        active_task = get_active_task(session_id)

    # ---- Phase 2 Step 5: Extract slots from message (after task exists) ----
    extracted_slots = extract_slots_from_message(message)
    if extracted_slots and session_id and active_task:
        task_slots = get_task_slots(session_id)
        task_slots = apply_slot_updates(task_slots, extracted_slots)
        set_task_slots(session_id, task_slots)

    # ---- Phase 2 Step 6: Merge UI context into task slots ----
    if session_id and context and active_task:
        task_slots = get_task_slots(session_id)
        task_slots = merge_ui_context_into_slots(task_slots, context)
        set_task_slots(session_id, task_slots)

    # ---- Phase 2 Step 7: Rebuild effective context with updated slots ----
    if active_task:
        effective_context = slots_to_assist_context(active_task.get("slots", {}))
        if context:
            for k, v in context.items():
                if effective_context.get(k, "unknown") in ("unknown", "", None):
                    effective_context[k] = v

    # ---- Phase 3: Policy-based routing (replaces single-intent dispatch) ----
    policy = decide_next_actions(message, session_id)
    policy_source = policy.get("policy_source", "unknown")
    actions = policy.get("actions", [])

    # If policy deferred to planner, use LLM action planner
    if policy.get("mode") == "defer_to_planner":
        intent_result = classify_intent(message, history=history, context=effective_context)
        planner_result = plan_actions(
            message,
            conversation_state={"slots": active_task.get("slots", {}) if active_task else {}},
            active_task=active_task,
            slots=active_task.get("slots", {}) if active_task else {},
            history=history,
        )
        if planner_result.get("actions"):
            actions = planner_result["actions"]
            policy["preserve_active_task"] = planner_result.get("preserve_active_task", True)
            policy_source = "action_planner"
        else:
            # Planner fallback: use intent-based routing as last resort
            intent = intent_result.get("intent", "diagnosis")
            return _route_by_intent(intent, payload, intent_result, session_id, active_task, effective_context, history, profile, learner_context, message)

    # ---- Execute tools ----
    tool_results = []
    for action in actions:
        tool_name = action.get("tool", "")
        tool_args = action.get("args", {})
        if tool_name == "run_diagnosis":
            tool_args["active_task"] = active_task
        if tool_name in ("get_student_graph", "generate_quiz", "generate_learning_plan"):
            tool_args["session_id"] = session_id
        result = execute_tool(tool_name, **tool_args)
        tool_results.append(result)

    # ---- Search knowledge BEFORE composing response ----
    knowledge_refs_raw = None
    try:
        knowledge_refs_raw = search_knowledge(message, limit=5, job_role=payload.get("job_role"))
    except Exception:
        pass

    # ---- Compose response ----
    composed = compose_response(message, tool_results, active_task=active_task, knowledge_refs=knowledge_refs_raw)
    answer = composed.get("answer", "") if composed else fallback_answer({"status": "ok"})

    # ---- Build result ----
    notice = ""
    if tool_results:
        first = tool_results[0]
        if hasattr(first, "data") and isinstance(first.data, dict):
            notice = first.data.get("safety_notice", "")

    result = {
        "session_id": learner_context.get("session_id") or payload.get("session_id"),
        "answer": answer,
        "safety_notice": notice or safety_notice(message),
        "learner_context": learner_context,
        "tool_results": [r.to_dict() if hasattr(r, "to_dict") else r for r in tool_results],
        "policy_source": policy_source,
        "llm_configured": is_configured(),
        "intent": "policy_routed",
        "intent_source": policy_source,
        "conversation_state": {
            "active_task": task_summary(session_id) if session_id else None,
            "slots": slots_summary(active_task.get("slots", {}) if active_task else {}),
        },
    }

    # Track pending_slot for next turn
    active_task2 = get_active_task(session_id) if session_id else None
    if session_id and active_task2:
        # Check if any tool result suggests a clarifying question
        for tr in tool_results:
            if hasattr(tr, "data") and isinstance(tr.data, dict):
                questions = tr.data.get("clarifying_questions", [])
                if questions:
                    pending = get_pending_slot(session_id)
                    if not pending:
                        for q in questions:
                            field = q.get("field")
                            if field:
                                task_slots2 = active_task2.get("slots", {})
                                slot_val = task_slots2.get(field, {})
                                val = slot_val.get("value", "unknown") if isinstance(slot_val, dict) else str(slot_val)
                                if val in ("unknown", "", None):
                                    set_pending_slot(session_id, field)
                                    break

    if session_id:
        append_session_event(session_id, {
            "event_type": "chat_message",
            "message": message,
            "policy_source": policy_source,
            "tools_used": [a.get("tool") for a in actions],
        })
        result["student_graph"] = build_student_ability_graph(session_id)
        result["learner_context"] = learner_context_pack(session_id)

    if session_id:
        append_assistant_message(session_id, answer)

    # ---- Knowledge card fallback (if compose_response did not populate) ----
    if not result.get("knowledge_gaps"):
        if knowledge_refs_raw:
            result["knowledge_gaps"] = knowledge_refs_raw
            result["knowledge_refs"] = list(knowledge_refs_raw)
        else:
            try:
                sr = search_knowledge(message, limit=5, job_role=payload.get("job_role"))
                if sr:
                    result["knowledge_gaps"] = sr
                    result["knowledge_refs"] = list(sr)
                else:
                    result["knowledge_refs"] = []
            except Exception:
                pass

    return result


# ---- Legacy intent-based routing (fallback only) ----
    assist_result = assist({"user_input": message, "context": effective_context})
    evidence_used = evidence_used_from_assist(assist_result, effective_context)
    reasoning_steps = reasoning_steps_from_assist(assist_result)
    knowledge_refs = knowledge_refs_from_assist(message, assist_result, job_role=payload.get("job_role"))
    next_questions = suggested_questions_from_assist(assist_result)

    fallback_used = True
    llm_error = ""
    answer = fallback_answer(assist_result)

    # ---- LLM-powered clarification ----
    clarify_handled = False
    if assist_result.get("status") == "need_clarification" and is_configured():
        try:
            clarify_qs, clarify_safety, _ = generate_clarify_questions(
                message, assist_result, effective_context,
                history=history[-4:]
            )
            if clarify_qs:
                pattern_title = (assist_result.get("matched_pattern") or {}).get(
                    "title", "??????"
                )
                question_lines = "\n".join(
                    f"{i + 1}. **{q.get('question', '')}**"
                    + (
                        f"\n   > {q.get('why_needed', '')}"
                        if q.get("why_needed")
                        else ""
                    )
                    for i, q in enumerate(clarify_qs)
                )
                answer = (
                    f"????{pattern_title}?????????????????????????????\n\n"
                    f"{question_lines}\n\n"
                    "??????????????????????????PLC ????????????"
                )
                if clarify_safety:
                    reasoning_steps.insert(0, clarify_safety)
                clarify_handled = True
                fallback_used = False
        except Exception:
            pass

    if is_configured() and not clarify_handled:
        messages = [{"role": "system", "content": build_system_prompt(profile)}]
        for item in history:
            role = item.get("role")
            c = item.get("content")
            if role in {"user", "assistant"} and c:
                messages.append({"role": role, "content": str(c)})
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
        "intent": intent,
        "intent_source": intent_result.get("source", "keyword") if intent_result else "task_continuation",
        "conversation_state": {
            "active_task": task_summary(session_id) if session_id else None,
            "slots": slots_summary(active_task.get("slots", {}) if active_task else {}),
        },
    }

    # Track pending_slot for next turn
    active_task2 = get_active_task(session_id) if session_id else None
    if session_id and active_task2 and assist_result.get("status") == "need_clarification":
        pending = get_pending_slot(session_id)
        if not pending:
            for q in assist_result.get("clarifying_questions", []):
                field = q.get("field")
                if field:
                    task_slots2 = active_task2.get("slots", {})
                    slot_val = task_slots2.get(field, {})
                    val = slot_val.get("value", "unknown") if isinstance(slot_val, dict) else str(slot_val)
                    if val in ("unknown", "", None):
                        set_pending_slot(session_id, field)
                        break

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

    if session_id:
        append_assistant_message(session_id, answer)

    return result


def _route_by_intent(intent, payload, intent_result, session_id, active_task, effective_context, history, profile, learner_context, message):
    """Legacy intent-based routing. Used as fallback when policy/planner cannot determine actions."""
    if intent == "quiz":
        return _finalize(handle_quiz(payload, intent_result), session_id)
    if intent == "graph":
        return _finalize(handle_graph(payload, intent_result), session_id)
    if intent == "learning_path":
        return _finalize(handle_learning_path(payload, intent_result), session_id)
    if intent == "knowledge_qa":
        result = _finalize(handle_knowledge_qa(payload, intent_result), session_id)
        if session_id:
            active = get_active_task(session_id)
            if active:
                result["conversation_state"] = {
                    "active_task": task_summary(session_id),
                    "slots": slots_summary(active.get("slots", {})),
                }
        return result
    if intent == "clarify":
        return _finalize(handle_clarify(payload, intent_result), session_id)
    # Default: run diagnosis
    assist_result = assist({"user_input": message, "context": effective_context})
    answer = fallback_answer(assist_result)
    result = {
        "answer": answer,
        "matched_pattern": assist_result.get("matched_pattern"),
        "intent": intent,
        "intent_source": "fallback",
    }
    if session_id:
        append_assistant_message(session_id, answer)
    return _finalize(result, session_id)


def _finalize(result, session_id):
    """Record session event and attach updated graph/context for non-diagnosis intents."""
    if session_id:
        append_session_event(
            session_id,
            {
                "event_type": "chat_message",
                "intent": result.get("intent"),
                "intent_source": result.get("intent_source"),
                "answer": result.get("answer", "")[:200],
            },
        )
        result["student_graph"] = build_student_ability_graph(session_id)
        result["learner_context"] = learner_context_pack(session_id)
    return result
