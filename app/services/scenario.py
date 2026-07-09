from .data_loader import load_data
from .graph import build_student_ability_graph
from .graph_update_engine import record_student_graph_event


def compact_ability(ability_id):
    ability = load_data()["ability_by_id"].get(ability_id, {})
    if not ability:
        return {"id": ability_id, "name": ability_id}
    return {
        "id": ability_id,
        "name": ability.get("name", ability_id),
        "source": ability.get("source") or ", ".join(ability.get("sources", [])[:2]),
    }


def scenario_by_id(scenario_id=None):
    scenarios = load_data()["troubleshooting_scenarios"]
    if scenario_id:
        for scenario in scenarios:
            if scenario.get("id") == scenario_id:
                return scenario
    if not scenarios:
        raise ValueError("no troubleshooting scenarios configured")
    return scenarios[0]


def step_by_id(scenario, step_id=None):
    steps = scenario.get("steps", [])
    if step_id:
        for step in steps:
            if step.get("id") == step_id:
                return step
    if not steps:
        raise ValueError("scenario has no steps")
    return steps[0]


def public_step(step):
    return {
        "id": step.get("id"),
        "prompt": step.get("prompt"),
        "ability_hits": [compact_ability(item) for item in step.get("ability_ids", [])],
        "options": [
            {
                "id": option.get("id"),
                "text": option.get("text"),
            }
            for option in step.get("options", [])
        ],
    }


def scenario_summary(scenario):
    return {
        "id": scenario.get("id"),
        "title": scenario.get("title"),
        "roleplay_frame": scenario.get("roleplay_frame"),
        "initial_symptom": scenario.get("initial_symptom"),
        "safety_notice": scenario.get("safety_notice"),
        "ability_hits": [compact_ability(item) for item in scenario.get("ability_ids", [])],
        "source": scenario.get("source"),
    }


def list_scenarios():
    return {
        "scenarios": [
            {
                "id": scenario.get("id"),
                "title": scenario.get("title"),
                "initial_symptom": scenario.get("initial_symptom"),
                "ability_hits": [compact_ability(item) for item in scenario.get("ability_ids", [])],
                "source": scenario.get("source"),
            }
            for scenario in load_data()["troubleshooting_scenarios"]
        ]
    }


def start_scenario(payload=None):
    payload = payload or {}
    scenario = scenario_by_id(payload.get("scenario_id"))
    first_step = step_by_id(scenario)
    session_id = payload.get("session_id")
    if session_id:
        record_student_graph_event(
            {
                "session_id": session_id,
                "event_type": "scenario_started",
                "ability_ids": scenario.get("ability_ids", []),
                "note": scenario.get("title"),
                "source": scenario.get("source", "project_curated"),
            }
        )
    return {
        "status": "in_progress",
        "scenario": scenario_summary(scenario),
        "current_step": public_step(first_step),
        "student_graph": build_student_ability_graph(session_id) if session_id else None,
    }


def step_scenario(payload=None):
    payload = payload or {}
    scenario = scenario_by_id(payload.get("scenario_id"))
    step = step_by_id(scenario, payload.get("step_id"))
    choice_id = payload.get("choice_id")
    option = None
    for item in step.get("options", []):
        if item.get("id") == choice_id:
            option = item
            break
    if not option:
        raise ValueError("choice_id not found")

    is_correct = bool(option.get("is_correct"))
    next_step = step_by_id(scenario, step.get("next_step_id")) if step.get("next_step_id") else None
    completed = is_correct and next_step is None
    session_id = payload.get("session_id")
    event_type = "scenario_step_completed" if is_correct else "scenario_step_mistake"
    ability_ids = step.get("ability_ids", [])
    if session_id:
        record_student_graph_event(
            {
                "session_id": session_id,
                "event_type": event_type,
                "ability_ids": ability_ids,
                "outcome": "correct" if is_correct else "incorrect",
                "note": f"{scenario.get('title')} / {step.get('id')} / 选择 {choice_id}",
                "source": scenario.get("source", "project_curated"),
            }
        )

    return {
        "status": "completed" if completed else "in_progress",
        "scenario": scenario_summary(scenario),
        "step_id": step.get("id"),
        "choice_id": choice_id,
        "is_correct": is_correct,
        "feedback": option.get("feedback"),
        "observation": option.get("observation"),
        "ability_hits": [compact_ability(item) for item in ability_ids],
        "current_step": public_step(next_step) if is_correct and next_step else (public_step(step) if not is_correct else None),
        "suggested_questions": [
            "为什么这一步要放在当前顺序？",
            "如果我选错了，对应哪个能力点薄弱？",
            "能不能把这个场景转换成一张排故检查表？",
        ],
        "student_graph": build_student_ability_graph(session_id) if session_id else None,
    }
