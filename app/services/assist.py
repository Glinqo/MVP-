from .data_loader import load_data, primary_job_profile
from .graph import build_ability_graph
from .safety import safety_notice


UNKNOWN_VALUES = {"", None, "unknown", "未确认", "不知道", "不清楚"}


def normalize_value(value):
    if value is None:
        return "unknown"
    return str(value).strip().lower()


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


def context_value(context, field):
    return normalize_value((context or {}).get(field, "unknown"))


def is_unknown(value):
    return normalize_value(value) in UNKNOWN_VALUES


def infer_pattern_from_context(context):
    sensor_led = context_value(context, "sensor_led")
    plc_input_led = context_value(context, "plc_input_led")
    online_monitor = context_value(context, "online_monitor")
    cylinder_action = context_value(context, "cylinder_action")

    if cylinder_action not in UNKNOWN_VALUES:
        return "cylinder_no_action_layered"
    if sensor_led in {"off", "unstable"}:
        return "sensor_led_off_or_unstable"
    if sensor_led == "on" and plc_input_led == "on" and online_monitor == "off":
        return "plc_led_on_monitor_off"
    if sensor_led == "on" and plc_input_led == "off":
        return "sensor_led_on_plc_led_off"
    return None


def score_pattern(pattern, text):
    raw = str(text or "").lower()
    score = 0
    for term in pattern.get("match_terms", []):
        if str(term).lower() in raw:
            score += 1
    return score + int(pattern.get("priority", 0)) / 1000


def choose_pattern(user_input, context):
    data = load_data()
    patterns = data["problem_patterns"]
    by_id = {pattern.get("id"): pattern for pattern in patterns}

    inferred_id = infer_pattern_from_context(context)
    if inferred_id and inferred_id in by_id:
        return by_id[inferred_id]

    scored = [(score_pattern(pattern, user_input), pattern) for pattern in patterns]
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("id", "")))
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return patterns[0] if patterns else {}


def missing_required_context(pattern, context):
    missing = []
    for field in pattern.get("required_context", []):
        if is_unknown((context or {}).get(field)):
            missing.append(field)
    return missing


def clarifying_questions(pattern, missing_fields):
    questions = []
    missing = set(missing_fields)
    for item in pattern.get("clarifying_questions", []):
        if item.get("field") in missing:
            questions.append(item)
    return questions[:3]


def related_resources_for_abilities(ability_ids):
    resources = []
    seen = set()
    for resource in load_data()["resources"]:
        if resource.get("id") in seen:
            continue
        if any(ability_id in resource.get("node_ids", []) for ability_id in ability_ids):
            seen.add(resource.get("id"))
            resources.append(resource)
    return resources


def build_highlighted_abilities(pattern):
    data = load_data()
    highlighted = []
    for item in pattern.get("highlighted_abilities", []):
        ability_id = item.get("id")
        ability = data["ability_by_id"].get(ability_id, {})
        highlighted.append(
            {
                "id": ability_id,
                "name": ability.get("name", ability_id),
                "reason": item.get("reason", ""),
                "related_knowledge": ability.get("related_knowledge", []),
                "related_tasks": ability.get("related_tasks", []),
                "source": ability.get("source"),
            }
        )
    return highlighted


def build_knowledge_gaps(pattern):
    data = load_data()
    gaps = []
    for knowledge_id in pattern.get("related_knowledge", []):
        item = data["knowledge_by_id"].get(knowledge_id)
        if item:
            gaps.append(compact_knowledge(item))
    return gaps


def build_remediation_cards(pattern):
    data = load_data()
    ability_ids = [item.get("id") for item in pattern.get("highlighted_abilities", [])]
    task_cards = [
        compact_task(data["task_by_id"][task_id])
        for task_id in pattern.get("related_tasks", [])
        if task_id in data["task_by_id"]
    ]
    resource_cards = [compact_resource(item) for item in related_resources_for_abilities(ability_ids)]

    cards = []
    for task in task_cards:
        cards.append(
            {
                "type": "training_task",
                "title": task.get("title"),
                "action": task.get("deliverable"),
                "estimated_minutes": task.get("estimated_minutes"),
                "difficulty": task.get("difficulty"),
                "source": task.get("source"),
            }
        )

    for resource in resource_cards[:4]:
        cards.append(
            {
                "type": "learning_resource",
                "title": resource.get("title"),
                "action": resource.get("use_when"),
                "resource_type": resource.get("type"),
                "source": resource.get("source"),
            }
        )

    return cards[:6]


def assist(payload):
    payload = payload or {}
    user_input = payload.get("user_input", "")
    context = payload.get("context", {}) or {}
    pattern = choose_pattern(user_input, context)
    missing = missing_required_context(pattern, context)
    highlighted = build_highlighted_abilities(pattern)
    highlighted_ids = [item["id"] for item in highlighted]
    knowledge_gaps = build_knowledge_gaps(pattern)
    remediation_cards = build_remediation_cards(pattern)
    graph = build_ability_graph(highlighted_ids)

    status = "need_clarification" if missing else "answered"
    questions = clarifying_questions(pattern, missing)
    direct_answer = "" if status == "need_clarification" else pattern.get("direct_answer", "")

    return {
        "status": status,
        "job_profile": primary_job_profile(),
        "matched_pattern": {
            "id": pattern.get("id"),
            "title": pattern.get("title"),
            "typical_symptom": pattern.get("typical_symptom"),
            "source": pattern.get("source"),
        },
        "safety_notice": safety_notice(user_input),
        "clarifying_questions": questions,
        "direct_answer": direct_answer,
        "first_checks": [] if status == "need_clarification" else pattern.get("first_checks", []),
        "fault_candidates": [] if status == "need_clarification" else pattern.get("fault_candidates", []),
        "highlighted_abilities": highlighted,
        "knowledge_gaps": knowledge_gaps,
        "remediation_cards": remediation_cards,
        "ability_knowledge_view": {
            "graph": graph,
            "highlighted_abilities": highlighted,
            "knowledge_gaps": knowledge_gaps,
            "remediation_cards": remediation_cards,
        },
    }
