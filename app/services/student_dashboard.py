from .data_loader import load_data
from .graph import build_student_ability_graph
from .graph_update_engine import normalize_ability_id
from .learner_context import learner_context_pack


STATUS_WEIGHTS = {
    "weak": 1,
    "improving": 2,
    "recommended_next": 3,
    "touched": 4,
    "unknown": 5,
    "mastered": 6,
}


def status_counts(nodes):
    counts = {}
    for node in nodes:
        status = node.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def readiness_score(nodes, event_count):
    if not event_count:
        return 18
    if not nodes:
        return 0
    total = 0
    for node in nodes:
        total += int(node.get("mastery_score", 30) or 0)
    average = total / max(len(nodes), 1)
    confidence_bonus = min(12, event_count * 2)
    return max(0, min(100, round(average + confidence_bonus)))


def readiness_level(score, counts):
    if counts.get("weak", 0) >= 3:
        return "需要补基础"
    if score >= 75 and not counts.get("weak"):
        return "可以进入综合排故"
    if score >= 55:
        return "适合边练边补"
    return "需要建立证据"


def sort_focus_nodes(nodes):
    return sorted(
        nodes,
        key=lambda node: (
            STATUS_WEIGHTS.get(node.get("status"), 9),
            int(node.get("mastery_score", 30) or 0),
            -int(node.get("evidence_count", 0) or 0),
        ),
    )


def linked_items(ability_id):
    data = load_data()
    ability = data["ability_by_id"].get(ability_id, {})
    knowledge = [
        data["knowledge_by_id"][item_id]
        for item_id in ability.get("related_knowledge", [])
        if item_id in data["knowledge_by_id"]
    ]
    tasks = [
        data["task_by_id"][item_id]
        for item_id in ability.get("related_tasks", [])
        if item_id in data["task_by_id"]
    ]
    resources = [
        item
        for item in data["resources"]
        if ability_id in item.get("ability_ids", [])
        or any(knowledge_item.get("id") in item.get("knowledge_ids", []) for knowledge_item in knowledge)
    ]
    questions = [
        item
        for item in data["questions_data"].get("questions", [])
        if normalize_ability_id(item.get("ability_id")) == ability_id
        or ability_id in [normalize_ability_id(raw_id) for raw_id in item.get("ability_ids", [])]
    ]
    return {
        "knowledge": [
            {
                "id": item.get("id"),
                "topic": item.get("topic"),
                "content": item.get("content", "")[:140],
                "source": item.get("source"),
            }
            for item in knowledge[:3]
        ],
        "tasks": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "deliverable": item.get("deliverable") or item.get("action"),
                "estimated_minutes": item.get("estimated_minutes"),
                "source": item.get("source"),
            }
            for item in tasks[:2]
        ],
        "resources": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "type": item.get("type"),
                "url": item.get("url"),
                "source": item.get("source"),
            }
            for item in resources[:2]
        ],
        "checkpoint_questions": [
            {
                "id": item.get("id"),
                "question": item.get("question"),
                "type": item.get("type"),
                "source": item.get("source"),
            }
            for item in questions[:2]
        ],
    }


def risk_flags(nodes, counts, event_count):
    flags = []
    safety = next((node for node in nodes if node.get("id") == "electrical_safety_check"), None)
    if safety and safety.get("status") in {"weak", "touched", "recommended_next", "unknown"}:
        flags.append(
            {
                "level": "safety",
                "title": "安全能力必须优先确认",
                "detail": "涉及接线、通电、PLC 监控或气动执行机构前，先断电确认急停、气源和设备状态。",
            }
        )
    if counts.get("weak", 0) >= 2:
        flags.append(
            {
                "level": "weak",
                "title": "薄弱能力集中",
                "detail": "建议先完成一个短训练单，不要直接进入综合排故。",
            }
        )
    if event_count == 0:
        flags.append(
            {
                "level": "evidence",
                "title": "个人图谱证据不足",
                "detail": "先问一个真实现场问题，或完成一次自测，系统才能形成更可靠的个人能力图谱。",
            }
        )
    return flags[:3]


def dashboard_actions(focus_nodes, event_count):
    if not event_count:
        return [
            {
                "title": "先建立个人图谱证据",
                "action": "在主对话输入一个真实排故问题，例如传感器灯亮但 PLC 没输入。",
                "tool_id": "chat",
            },
            {
                "title": "做一次快速自测",
                "action": "完成预设题中的安全、NPN/PNP、公共端和 PLC 监控题。",
                "tool_id": "quiz",
            },
        ]

    actions = []
    for node in focus_nodes[:3]:
        actions.append(
            {
                "title": node.get("label"),
                "action": node.get("next_best_action") or "查看讲解并完成一个关联实训任务。",
                "ability_id": node.get("id"),
                "status": node.get("status"),
                "tool_id": "plan" if node.get("status") in {"weak", "improving"} else "student_graph",
            }
        )
    return actions


def build_student_dashboard(session_id=None):
    graph = build_student_ability_graph(session_id)
    context = learner_context_pack(graph.get("session_id"))
    nodes = graph.get("nodes", [])
    counts = status_counts(nodes)
    event_count = graph.get("event_count", 0)
    score = readiness_score(nodes, event_count)
    focus_nodes = sort_focus_nodes(nodes)
    primary = focus_nodes[0] if focus_nodes else None

    immediate_focus = []
    for node in focus_nodes[:4]:
        linked = linked_items(node.get("id"))
        immediate_focus.append(
            {
                "ability_id": node.get("id"),
                "ability_name": node.get("label"),
                "status": node.get("status"),
                "status_label": node.get("status_label"),
                "mastery_score": node.get("mastery_score"),
                "confidence": node.get("confidence"),
                "reason": (node.get("update_reasons") or node.get("evidence") or ["个人图谱排序建议"])[0],
                "next_best_action": node.get("next_best_action"),
                **linked,
            }
        )

    tool_suggestions = [
        {"id": "student_graph", "label": "查看个人能力图谱", "reason": "确认本次排序依据"},
        {"id": "plan", "label": "生成今日训练单", "reason": "把薄弱点变成可执行任务"},
        {"id": "scenario", "label": "做排故角色扮演", "reason": "用现场证据验证判断顺序"},
        {"id": "quiz", "label": "做自测验证", "reason": "用确定性评分确认是否掌握"},
    ]

    if primary:
        headline = f"当前最该处理：{primary.get('label')}。{primary.get('next_best_action') or ''}"
    else:
        headline = "尚未形成个人图谱，请先完成一次问答或自测。"

    return {
        "session_id": graph.get("session_id"),
        "dashboard_title": "学生学习驾驶舱",
        "headline": headline,
        "readiness_score": score,
        "readiness_level": readiness_level(score, counts),
        "event_count": event_count,
        "status_counts": counts,
        "graph_summary": graph.get("summary", {}),
        "learner_summary": context.get("summary"),
        "risk_flags": risk_flags(nodes, counts, event_count),
        "immediate_focus": immediate_focus,
        "today_actions": dashboard_actions(focus_nodes, event_count),
        "tool_suggestions": tool_suggestions,
        "evidence_summary": {
            "recent_events": context.get("recent_events", [])[:5],
            "next_best_actions": context.get("next_best_actions", [])[:5],
        },
        "self_critique": [
            "原有功能点较多，但学生需要一个总控视角判断下一步先做什么。",
            "驾驶舱把图谱、计划、自测和场景训练压缩成同一个行动面板，减少工具之间来回找入口。",
            "所有分数来自本地事件和规则图谱，不让 LLM 自由评价学生能力。",
        ],
        "borrowed_from": [
            "Inno Agent learner context pack",
            "DeepTutor mastery path",
            "EduAdapt progress tracker",
            "PersonalizedAdaptiveLearning weak-topic path ordering",
        ],
        "source": "student_graph + learner_context_pack + local deterministic rules",
    }
