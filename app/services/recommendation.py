from .data_loader import load_data, primary_job_profile
from .feedback import append_session_event
from .graph import build_ability_graph, build_student_ability_graph
from .retrieval import refs_for_ability_ids, search_knowledge
from .safety import safety_notice
from .scoring import score_answers


def reverse_ability_catalog():
    rules = load_data()["rules_data"]
    reverse = {}
    for internal_id, catalog in rules.get("ability_catalog", {}).items():
        reverse[catalog.get("ability_id", internal_id)] = internal_id
    return reverse


def internal_ability_ids(weak_abilities):
    reverse = reverse_ability_catalog()
    return [reverse.get(item.get("ability_id"), item.get("ability_id")) for item in weak_abilities]


def compact_knowledge(item):
    return {
        "id": item.get("id"),
        "topic": item.get("topic"),
        "ability_node_id": item.get("ability_node_id"),
        "content": item.get("content"),
        "source": item.get("source"),
    }


def compact_task(item):
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "difficulty": item.get("difficulty"),
        "estimated_minutes": item.get("estimated_minutes"),
        "deliverable": item.get("deliverable"),
        "source": item.get("source"),
    }


def compact_resource(item):
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "type": item.get("type"),
        "use_when": item.get("use_when"),
        "source": item.get("source"),
    }


def diagnose(payload):
    payload = payload or {}
    user_input = payload.get("user_input", "")
    answers = payload.get("answers", {})
    score_result = score_answers({"answers": answers})
    weak_internal_ids = internal_ability_ids(score_result.get("weak_abilities", []))
    refs = refs_for_ability_ids(weak_internal_ids)

    retrieved = search_knowledge(user_input, limit=5) if user_input else []
    notice = safety_notice(user_input, score_result.get("weak_abilities", []), score_result.get("recommended_path", []))

    result = {
        "job_profile": primary_job_profile(),
        "safety_notice": notice,
        "score_result": score_result,
        "weak_abilities": score_result.get("weak_abilities", []),
        "ability_refs": [
            {
                "id": ability_id,
                "name": load_data()["ability_by_id"].get(ability_id, {}).get("name", ability_id),
                "source": load_data()["ability_by_id"].get(ability_id, {}).get("source"),
            }
            for ability_id in weak_internal_ids
        ],
        "recommended_path": score_result.get("recommended_path", []),
        "knowledge_refs": [compact_knowledge(item) for item in refs["knowledge_refs"][:6]],
        "task_recommendations": [compact_task(item) for item in refs["task_refs"][:4]],
        "resource_recommendations": [compact_resource(item) for item in refs["resource_refs"][:4]],
        "retrieved_knowledge": retrieved,
        "ability_graph": build_ability_graph(weak_internal_ids),
    }

    session_id = payload.get("session_id")
    if session_id:
        append_session_event(
            session_id,
            {
                "event_type": "diagnosis",
                "user_input": user_input,
                "answers": answers,
                "score_result": score_result,
                "weak_abilities": score_result.get("weak_abilities", []),
                "recommended_path": score_result.get("recommended_path", []),
            },
        )
        result["student_graph"] = build_student_ability_graph(session_id)

    return result
