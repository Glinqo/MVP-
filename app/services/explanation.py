from .assist import assist
from .data_loader import load_data
from .graph_update_engine import record_student_graph_event
from .retrieval import refs_for_ability_ids, search_knowledge
from .safety import safety_notice


def compact_ability(ability_id, reason=""):
    ability = load_data()["ability_by_id"].get(ability_id, {})
    if not ability:
        return {}
    return {
        "id": ability_id,
        "name": ability.get("name", ability_id),
        "description": ability.get("description", ""),
        "reason": reason,
        "source": ability.get("source") or ", ".join(ability.get("sources", [])[:2]),
    }


def compact_knowledge(item):
    if not item:
        return {}
    return {
        "id": item.get("id"),
        "topic": item.get("topic"),
        "ability_node_id": item.get("ability_node_id"),
        "content": item.get("content"),
        "common_errors": item.get("common_errors", []),
        "source": item.get("source"),
    }


def compact_task(item):
    if not item:
        return {}
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "difficulty": item.get("difficulty"),
        "estimated_minutes": item.get("estimated_minutes"),
        "deliverable": item.get("deliverable"),
        "source": item.get("source"),
    }


def compact_resource(item):
    if not item:
        return {}
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "type": item.get("type"),
        "url": item.get("url"),
        "use_when": item.get("use_when"),
        "source": item.get("source"),
    }


def find_question(question_id):
    for question in load_data()["questions_data"].get("questions", []):
        if question.get("id") == question_id:
            return question
    return None


def normalize_answer(value):
    if isinstance(value, list):
        return "".join(str(item).strip().upper() for item in value if str(item).strip())
    return "".join(part.strip().upper() for part in str(value or "").replace(",", " ").split())


def related_resources_for_abilities(ability_ids):
    resources = []
    seen = set()
    for resource in load_data()["resources"]:
        if resource.get("id") in seen:
            continue
        node_ids = set(resource.get("node_ids", [])) | set(resource.get("ability_ids", []))
        if node_ids.intersection(ability_ids):
            seen.add(resource.get("id"))
            resources.append(compact_resource(resource))
    return resources


def question_explanation(payload):
    data = load_data()
    question = find_question(payload.get("question_id") or payload.get("id"))
    if not question:
        knowledge = data["knowledge_by_id"].get(payload.get("knowledge_id"))
        if not knowledge:
            raise ValueError("question_id not found")
        question = {
            "id": payload.get("question_id") or payload.get("id") or knowledge.get("id"),
            "question": payload.get("question") or payload.get("prompt") or f"围绕{knowledge.get('topic')}的个性化练习题",
            "correct_answer": payload.get("correct_answer") or "A",
            "ability_id": payload.get("ability_id") or knowledge.get("ability_node_id"),
            "explanation": payload.get("explanation") or knowledge.get("content", ""),
            "wrong_feedback": "这类个性化题主要检查你能否把知识点放回现场排故链路中使用。",
            "remediation_resources": [knowledge.get("id")],
            "remediation_tasks": knowledge.get("related_tasks", []),
            "source": knowledge.get("source"),
        }

    ability_id = question.get("ability_id")
    knowledge_refs = [
        compact_knowledge(data["knowledge_by_id"].get(item_id))
        for item_id in question.get("remediation_resources", [])
        if data["knowledge_by_id"].get(item_id)
    ]
    task_refs = [
        compact_task(data["task_by_id"].get(item_id))
        for item_id in question.get("remediation_tasks", [])
        if data["task_by_id"].get(item_id)
    ]

    selected = normalize_answer(payload.get("selected_answer"))
    correct = normalize_answer(question.get("correct_answer"))
    has_answer = bool(selected)
    is_correct = has_answer and selected == correct
    answer_state = "not_answered"
    if has_answer:
        answer_state = "correct" if is_correct else "incorrect"

    explanation = question.get("explanation", "")
    if has_answer and not is_correct:
        explanation = f"{question.get('wrong_feedback', '')}\n\n标准判断：{question.get('explanation', '')}"

    reasoning_steps = [
        "先看题目考查的岗位能力点，再看现场信号链路中的位置。",
        f"本题绑定能力：{compact_ability(ability_id).get('name', ability_id)}。",
        f"标准答案：{question.get('correct_answer')}。题目讲解：{question.get('explanation', '')}",
    ]
    if has_answer:
        reasoning_steps.insert(2, f"你的答案：{selected or '未作答'}，判断结果：{'答对' if is_correct else '需要再看错因'}。")

    return {
        "explain_type": "question",
        "target_id": question.get("id"),
        "title": f"{question.get('id')} 题目讲解",
        "answer_state": answer_state,
        "explanation": explanation,
        "safety_notice": safety_notice(question.get("question", "")),
        "evidence_used": [
            {"label": "题干", "value": question.get("question"), "source": question.get("source")},
            {"label": "标准答案", "value": question.get("correct_answer"), "source": question.get("source")},
            {"label": "错因反馈", "value": question.get("wrong_feedback"), "source": question.get("source")},
        ],
        "reasoning_steps": reasoning_steps,
        "ability_hits": [compact_ability(ability_id, "题目绑定的能力点")],
        "knowledge_refs": knowledge_refs,
        "task_refs": task_refs,
        "resource_refs": related_resources_for_abilities([ability_id]),
        "suggested_questions": [
            "这道题对应现场排故的哪一步？",
            "如果我答错了，应该先补哪个知识点？",
            "能不能用传感器灯、PLC 输入灯、在线监控三联状态再解释一次？",
        ],
        "source": question.get("source"),
    }


def ability_explanation(payload):
    ability_id = payload.get("ability_id") or payload.get("id")
    ability = load_data()["ability_by_id"].get(ability_id)
    if not ability:
        raise ValueError("ability_id not found")

    refs = refs_for_ability_ids([ability_id])
    knowledge_refs = [compact_knowledge(item) for item in refs.get("knowledge_refs", [])[:5]]
    task_refs = [compact_task(item) for item in refs.get("task_refs", [])[:4]]
    resource_refs = [compact_resource(item) for item in refs.get("resource_refs", [])[:4]]
    prerequisites = [compact_ability(item, "前置能力") for item in ability.get("prerequisites", [])]

    return {
        "explain_type": "ability",
        "target_id": ability_id,
        "title": ability.get("name", ability_id),
        "explanation": (
            f"{ability.get('name', ability_id)} 是当前岗位排故链路中的能力点。"
            f"{ability.get('description', '')} 学生如果在这里卡住，通常需要同时补知识、看现场证据并完成一个实训任务。"
        ),
        "safety_notice": safety_notice(ability.get("description", "")),
        "evidence_used": [
            {"label": "能力描述", "value": ability.get("description"), "source": ability.get("source")},
            {"label": "常见错误", "value": "；".join(ability.get("common_errors", [])[:3]), "source": ability.get("source")},
        ],
        "reasoning_steps": [
            "先确认这个能力在岗位链路中的前置关系。",
            "再查看关联知识点，明确学生缺的是概念、接线判断还是监控验证。",
            "最后安排一个可提交成果的实训任务，用结果更新个人能力图谱。",
        ],
        "ability_hits": [compact_ability(ability_id, "当前讲解对象")] + [item for item in prerequisites if item],
        "knowledge_refs": knowledge_refs,
        "task_refs": task_refs,
        "resource_refs": resource_refs,
        "suggested_questions": [
            f"我怎么判断自己是否掌握了{ability.get('name', ability_id)}？",
            "这个能力对应哪一道自测题？",
            "给我一个一节课内能完成的训练任务。",
        ],
        "source": ability.get("source") or ", ".join(ability.get("sources", [])[:2]),
    }


def knowledge_explanation(payload):
    knowledge_id = payload.get("knowledge_id") or payload.get("id")
    item = load_data()["knowledge_by_id"].get(knowledge_id)
    if not item:
        raise ValueError("knowledge_id not found")
    ability_id = item.get("ability_node_id")
    task_refs = [
        compact_task(load_data()["task_by_id"].get(task_id))
        for task_id in item.get("related_tasks", [])
        if load_data()["task_by_id"].get(task_id)
    ]
    return {
        "explain_type": "knowledge",
        "target_id": knowledge_id,
        "title": item.get("topic", knowledge_id),
        "explanation": item.get("content", ""),
        "safety_notice": safety_notice(item.get("content", "")),
        "evidence_used": [
            {"label": "知识内容", "value": item.get("content"), "source": item.get("source")},
            {"label": "常见错误", "value": "；".join(item.get("common_errors", [])[:3]), "source": item.get("source")},
        ],
        "reasoning_steps": [
            "先把知识点放回传感器到 PLC 输入的信号链路中理解。",
            "再对照常见错误，判断学生当前问题是否命中这些错误。",
            "最后用关联任务验证能不能在现场正确应用。",
        ],
        "ability_hits": [compact_ability(ability_id, "知识点所属能力")],
        "knowledge_refs": [compact_knowledge(item)],
        "task_refs": task_refs,
        "resource_refs": related_resources_for_abilities([ability_id]),
        "suggested_questions": [
            "这个知识点在现场排故中怎么用？",
            "我容易把它和哪个概念混淆？",
            "有没有对应的实训任务可以马上练？",
        ],
        "source": item.get("source"),
    }


def task_explanation(payload):
    task_id = payload.get("task_id") or payload.get("id")
    task = load_data()["task_by_id"].get(task_id)
    if not task:
        raise ValueError("task_id not found")
    ability_ids = task.get("node_ids", []) + task.get("ability_ids", [])
    refs = refs_for_ability_ids(ability_ids)
    return {
        "explain_type": "task",
        "target_id": task_id,
        "title": task.get("title", task_id),
        "explanation": (
            f"这个任务用于把知识点落实到可观察成果。建议用 {task.get('estimated_minutes', '一节课内')} 分钟完成，"
            f"提交物是：{task.get('deliverable', '')}"
        ),
        "safety_notice": safety_notice(task.get("title", "") + " " + task.get("deliverable", "")),
        "evidence_used": [
            {"label": "任务提交物", "value": task.get("deliverable"), "source": task.get("source")},
            {"label": "任务难度", "value": task.get("difficulty"), "source": task.get("source")},
        ],
        "reasoning_steps": [
            "先做安全检查和现场状态记录。",
            "再按任务提交物逐项完成，不跳过接线和监控验证。",
            "完成后用自测题或现场复述验证是否真正掌握。",
        ],
        "ability_hits": [compact_ability(item, "任务覆盖能力") for item in ability_ids if compact_ability(item)],
        "knowledge_refs": [compact_knowledge(item) for item in refs.get("knowledge_refs", [])[:5]],
        "task_refs": [compact_task(task)],
        "resource_refs": [compact_resource(item) for item in refs.get("resource_refs", [])[:4]],
        "suggested_questions": [
            "这个任务第一步应该怎么做安全检查？",
            "完成这个任务需要拍照或记录哪些证据？",
            "如果任务失败，应该回到哪个能力点补？",
        ],
        "source": task.get("source"),
    }


def message_explanation(payload):
    message = payload.get("message") or payload.get("prompt") or payload.get("user_input") or ""
    analysis = assist({"user_input": message, "context": payload.get("context", {}) or {}})
    ability_ids = [item.get("id") for item in analysis.get("highlighted_abilities", []) if item.get("id")]
    return {
        "explain_type": "message",
        "target_id": analysis.get("matched_pattern", {}).get("id"),
        "title": analysis.get("matched_pattern", {}).get("title") or "问题讲解",
        "explanation": analysis.get("direct_answer") or "当前信息还不完整，可以先补充关键现场证据，再判断故障落点。",
        "safety_notice": analysis.get("safety_notice"),
        "evidence_used": [
            {"label": "典型现象", "value": analysis.get("matched_pattern", {}).get("typical_symptom"), "source": analysis.get("matched_pattern", {}).get("source")},
            {"label": "追问问题", "value": "；".join(item.get("question", "") for item in analysis.get("clarifying_questions", [])), "source": analysis.get("matched_pattern", {}).get("source")},
        ],
        "reasoning_steps": [
            "先判断输入属于哪个典型排故现象。",
            "再检查三联状态：传感器动作灯、PLC 输入灯、在线监控。",
            "最后把问题落到接线、公共端、地址映射或程序/气路层面。",
        ],
        "ability_hits": analysis.get("highlighted_abilities", []),
        "knowledge_refs": analysis.get("knowledge_gaps", []),
        "task_refs": analysis.get("remediation_cards", []),
        "resource_refs": related_resources_for_abilities(ability_ids),
        "suggested_questions": [
            item.get("question")
            for item in analysis.get("clarifying_questions", [])
            if item.get("question")
        ][:3],
        "source": analysis.get("matched_pattern", {}).get("source"),
    }


def explain(payload):
    payload = payload or {}
    explain_type = payload.get("type") or payload.get("explain_type")
    if not explain_type:
        if payload.get("question_id"):
            explain_type = "question"
        elif payload.get("ability_id"):
            explain_type = "ability"
        elif payload.get("knowledge_id"):
            explain_type = "knowledge"
        elif payload.get("task_id"):
            explain_type = "task"
        else:
            explain_type = "message"

    handlers = {
        "question": question_explanation,
        "ability": ability_explanation,
        "knowledge": knowledge_explanation,
        "task": task_explanation,
        "message": message_explanation,
    }
    if explain_type not in handlers:
        raise ValueError("unsupported explain_type")

    result = handlers[explain_type](payload)
    prompt = payload.get("prompt") or payload.get("message") or result.get("title")
    if prompt:
        extra_results = search_knowledge(prompt, limit=3)
        seen = {item.get("id") for item in result.get("knowledge_refs", [])}
        for item in extra_results:
            if item.get("id") not in seen:
                result.setdefault("knowledge_refs", []).append(item)
                seen.add(item.get("id"))

    session_id = payload.get("session_id")
    ability_ids = [item.get("id") for item in result.get("ability_hits", []) if item.get("id")]
    if session_id and ability_ids:
        event_type = payload.get("event_type") or f"{result['explain_type']}_explained"
        record_student_graph_event(
            {
                "session_id": session_id,
                "event_type": event_type,
                "ability_ids": ability_ids,
                "question_id": payload.get("question_id"),
                "knowledge_id": payload.get("knowledge_id"),
                "task_id": payload.get("task_id"),
                "note": f"学生查看{result.get('title', '')}讲解",
                "source": payload.get("source", "explain_api"),
            }
        )

    result.setdefault("fallback_used", True)
    result.setdefault("suggested_questions", [])
    return result
