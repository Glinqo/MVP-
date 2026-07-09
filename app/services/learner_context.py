from .data_loader import load_data, primary_job_profile
from .feedback import load_session_record, safe_session_id
from .graph import build_student_ability_graph
from .graph_update_engine import event_ability_ids


PRIORITY_STATUSES = {"weak", "improving", "recommended_next", "touched"}


def compact_node(node):
    return {
        "ability_id": node.get("id"),
        "ability_name": node.get("label"),
        "status": node.get("status"),
        "status_label": node.get("status_label"),
        "mastery_score": node.get("mastery_score"),
        "confidence": node.get("confidence"),
        "evidence_count": node.get("evidence_count"),
        "update_reasons": node.get("update_reasons", [])[:3],
        "next_best_action": node.get("next_best_action"),
        "source": node.get("source"),
    }


def ability_name(ability_id):
    ability = load_data()["ability_by_id"].get(ability_id, {})
    return ability.get("name", ability_id)


def compact_event(event):
    ability_ids = event_ability_ids(event)
    return {
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "created_at": event.get("created_at"),
        "ability_ids": ability_ids,
        "ability_names": [ability_name(ability_id) for ability_id in ability_ids],
        "note": event.get("note") or event.get("feedback") or event.get("matched_pattern", {}).get("title") or event.get("message", "")[:80],
        "source": event.get("source", "session_event"),
    }


def nodes_by_status(nodes, status):
    return [compact_node(node) for node in nodes if node.get("status") == status]


def next_actions(nodes, limit=5):
    prioritized = [
        node
        for node in nodes
        if node.get("status") in PRIORITY_STATUSES
    ]
    prioritized.sort(
        key=lambda node: (
            {"weak": 0, "improving": 1, "recommended_next": 2, "touched": 3}.get(node.get("status"), 9),
            node.get("mastery_score", 30),
            -node.get("evidence_count", 0),
        )
    )
    return [
        {
            "ability_id": node.get("id"),
            "ability_name": node.get("label"),
            "status": node.get("status"),
            "action": node.get("next_best_action"),
            "reason": (node.get("update_reasons") or node.get("evidence") or ["个人图谱建议"])[0],
        }
        for node in prioritized[:limit]
    ]


def summarize_context(graph, weak, improving, recommended, touched):
    event_count = graph.get("event_count", 0)
    if not event_count:
        return "尚未产生学习证据，建议先通过一次现场问题问答或自测建立个人图谱。"
    parts = [f"已记录 {event_count} 条学习证据"]
    if weak:
        parts.append("薄弱：" + "、".join(item["ability_name"] for item in weak[:3]))
    if improving:
        parts.append("正在提升：" + "、".join(item["ability_name"] for item in improving[:2]))
    if recommended:
        parts.append("下一步：" + "、".join(item["ability_name"] for item in recommended[:2]))
    if not weak and not improving and not recommended and touched:
        parts.append("已命中：" + "、".join(item["ability_name"] for item in touched[:3]))
    return "；".join(parts) + "。"


def learner_context_pack(session_id=None):
    session_id = safe_session_id(session_id)
    graph = build_student_ability_graph(session_id)
    record = load_session_record(session_id)
    nodes = graph.get("nodes", [])
    weak = nodes_by_status(nodes, "weak")
    improving = nodes_by_status(nodes, "improving")
    recommended = nodes_by_status(nodes, "recommended_next")
    touched = nodes_by_status(nodes, "touched")
    mastered = nodes_by_status(nodes, "mastered")
    recent_events = [compact_event(event) for event in record.get("events", [])[-6:]]

    return {
        "session_id": graph.get("session_id"),
        "summary": summarize_context(graph, weak, improving, recommended, touched),
        "event_count": graph.get("event_count", 0),
        "weak_abilities": weak[:5],
        "improving_abilities": improving[:5],
        "recommended_next": recommended[:5],
        "touched_abilities": touched[:5],
        "mastered_abilities": mastered[:5],
        "recent_events": recent_events,
        "next_best_actions": next_actions(nodes),
        "source": "student_graph + session_events",
    }


def format_context_for_prompt(context_pack):
    context_pack = context_pack or {}
    lines = [context_pack.get("summary", "暂无个人图谱证据。")]
    for label, key in [
        ("薄弱能力", "weak_abilities"),
        ("正在提升", "improving_abilities"),
        ("建议下一步", "recommended_next"),
    ]:
        items = context_pack.get(key, [])[:3]
        if items:
            lines.append(label + "：" + "、".join(item.get("ability_name", item.get("ability_id", "")) for item in items))
    actions = context_pack.get("next_best_actions", [])[:3]
    if actions:
        lines.append("下一步动作：" + "；".join(item.get("action", "") for item in actions if item.get("action")))
    return "\n".join(line for line in lines if line)


def bootstrap_questions(context_pack):
    weak = context_pack.get("weak_abilities", [])
    recommended = context_pack.get("recommended_next", [])
    if weak:
        return [
            f"我为什么在“{weak[0]['ability_name']}”上薄弱？",
            f"请按现场排故方式讲解“{weak[0]['ability_name']}”。",
            "今天我应该完成哪个训练任务？",
        ]
    if recommended:
        return [
            f"我下一步怎么练“{recommended[0]['ability_name']}”？",
            "能不能给我一张今天的训练单？",
            "做题错了以后怎么反映到个人图谱？",
        ]
    return [
        "传感器动作灯亮但 PLC 没输入，应该先查哪里？",
        "我怎么判断 NPN/PNP 和 PLC 公共端是否匹配？",
        "PLC 输入灯亮但在线监控不变，可能是什么问题？",
    ]


def student_bootstrap(session_id=None):
    context_pack = learner_context_pack(session_id)
    return {
        "session_id": context_pack.get("session_id"),
        "job_profile": primary_job_profile(),
        "learner_context": context_pack,
        "student_graph": build_student_ability_graph(context_pack.get("session_id")),
        "suggested_questions": bootstrap_questions(context_pack),
        "tool_suggestions": [
            {"id": "student_graph", "label": "查看个人能力图谱"},
            {"id": "plan", "label": "生成个人培养方案"},
            {"id": "scenario", "label": "排故角色扮演"},
            {"id": "quiz", "label": "做自测验证"},
        ],
        "source": "borrowed_feature: Inno Agent learner context pack; local session graph",
    }
