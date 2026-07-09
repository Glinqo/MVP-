from .data_loader import load_data, public_questions
from .graph import CORE_CHAIN, extract_ability_ids, session_ability_state
from .retrieval import search_knowledge


GENERIC_DISTRACTORS = [
    "只观察传感器动作灯，不再核对 PLC 输入灯和在线监控。",
    "先修改 PLC 程序，再回头确认接线和公共端。",
    "在没有断电和教师确认的情况下直接调整接线。",
]


def knowledge_for_abilities(ability_ids):
    data = load_data()
    seen = set()
    items = []
    for ability_id in ability_ids:
        ability = data["ability_by_id"].get(ability_id, {})
        for knowledge_id in ability.get("related_knowledge", []):
            item = data["knowledge_by_id"].get(knowledge_id)
            if item and item.get("id") not in seen:
                seen.add(item.get("id"))
                items.append(item)
        for item in data["knowledge"]:
            if item.get("ability_node_id") == ability_id and item.get("id") not in seen:
                seen.add(item.get("id"))
                items.append(item)
    return items


def ability_ids_from_payload(payload):
    payload = payload or {}
    ability_ids = []
    ability_ids.extend(extract_ability_ids(payload.get("weak_abilities", [])))
    ability_ids.extend(extract_ability_ids(payload.get("highlighted_abilities", [])))

    session_id = payload.get("session_id")
    if session_id:
        state = session_ability_state(session_id)
        ability_ids.extend(state["weak_hits"].keys())
        ability_ids.extend(state["chat_hits"].keys())
        ability_ids.extend(state["recommended_ids"])

    user_input = payload.get("user_input") or payload.get("message") or ""
    if user_input:
        for item in search_knowledge(user_input, limit=5):
            ability_id = item.get("ability_node_id")
            if ability_id:
                ability_ids.append(ability_id)

    ordered = []
    for ability_id in ability_ids + CORE_CHAIN:
        if ability_id in load_data()["ability_by_id"] and ability_id not in ordered:
            ordered.append(ability_id)
    return ordered


def compact_question(item, index):
    ability_id = item.get("ability_node_id")
    ability = load_data()["ability_by_id"].get(ability_id, {})
    common_errors = list(item.get("common_errors") or [])
    distractors = (common_errors + GENERIC_DISTRACTORS)[:3]
    correct = item.get("content") or f"围绕{item.get('topic')}，先按安全和证据顺序判断。"

    options = [{"id": "A", "text": correct}]
    for offset, text in enumerate(distractors, start=1):
        options.append({"id": chr(ord("A") + offset), "text": text})

    return {
        "id": f"P{index:02d}",
        "type": "single_choice",
        "question": f"围绕“{item.get('topic')}”，下面哪一项最符合岗位排查要求？",
        "options": options,
        "correct_answer": "A",
        "ability_id": ability_id,
        "ability_name": ability.get("name", ability_id),
        "knowledge_id": item.get("id"),
        "knowledge_topic": item.get("topic"),
        "explanation": correct,
        "ask_prompts": [
            f"请结合我的故障现象解释“{item.get('topic')}”。",
            f"这道题为什么选 A？我容易错在哪里？",
            f"我该做哪个实训任务来补“{ability.get('name', ability_id)}”？",
        ],
        "source": item.get("source"),
    }


def personalized_quiz(payload=None):
    payload = payload or {}
    limit = int(payload.get("limit") or 4)
    limit = max(1, min(limit, 8))
    ability_ids = ability_ids_from_payload(payload)
    knowledge_items = knowledge_for_abilities(ability_ids)

    questions = []
    seen = set()
    for item in knowledge_items:
        if item.get("id") in seen:
            continue
        seen.add(item.get("id"))
        questions.append(compact_question(item, len(questions) + 1))
        if len(questions) >= limit:
            break

    return {
        "mode": "personalized",
        "generation_mode": "knowledge_rule_template",
        "based_on_abilities": ability_ids[:8],
        "questions": questions,
        "preset_available": True,
        "preset_questions": public_questions(),
    }
