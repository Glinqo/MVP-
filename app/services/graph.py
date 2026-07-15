from collections import Counter, defaultdict

from .data_loader import load_data, primary_job_profile
from .feedback import load_session_record
from .graph_update_engine import (
    compute_node_metrics,
    confirmed_job_snapshots,
    pending_job_proposals,
    personal_graph_state,
)


CORE_CHAIN = [
    "electrical_safety_check",
    "sensor_type_identification",
    "sensor_wiring_judgement",
    "plc_input_common_terminal",
    "plc_io_address_mapping",
    "plc_input_monitoring",
    "input_no_response_fault_scope",
    "personalized_training_task_recommendation",
]


STATUS_LABELS = {
    "normal": "常规",
    "core": "岗位核心",
    "industry_hot": "行业高频",
    "industry": "行业补充",
    "weak": "薄弱",
    "touched": "问答命中",
    "improving": "正在提升",
    "mastered": "已掌握",
    "recommended_next": "建议下一步",
    "unknown": "待确认",
}


def mermaid_text(value):
    return str(value or "").replace('"', "'")


def float_or_zero(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_ability_id(ability_id):
    if not ability_id:
        return None
    data = load_data()
    raw = str(ability_id)
    if raw in data["ability_by_id"]:
        return raw

    catalog = data["rules_data"].get("ability_catalog", {})
    for internal_id, item in catalog.items():
        if raw in {str(item.get("ability_id")), str(item.get("ability_name"))}:
            return internal_id

    for internal_id, ability in data["ability_by_id"].items():
        if raw == str(ability.get("name")):
            return internal_id
    return raw


def extract_ability_ids(items):
    ability_ids = []
    for item in items or []:
        if isinstance(item, str):
            ability_id = normalize_ability_id(item)
        elif isinstance(item, dict):
            ability_id = None
            for key in ("ability_internal_id", "ability_node_id", "id", "ability_id", "node_id"):
                if item.get(key):
                    ability_id = normalize_ability_id(item.get(key))
                    break
        else:
            ability_id = None

        if ability_id and ability_id not in ability_ids:
            ability_ids.append(ability_id)
    return ability_ids


def ability_ids_from_names(names):
    data = load_data()
    matched = []
    for name in names or []:
        ability_id = normalize_ability_id(name)
        if ability_id in data["ability_by_id"] and ability_id not in matched:
            matched.append(ability_id)
    return matched


def ability_label(ability_id):
    ability = load_data()["ability_by_id"].get(ability_id, {})
    return ability.get("name", ability_id)


def ability_source(ability_id):
    ability = load_data()["ability_by_id"].get(ability_id, {})
    return ability.get("source") or ", ".join(ability.get("sources", [])[:2])


def next_best_action(ability_id, status):
    ability = load_data()["ability_by_id"].get(ability_id, {})
    task_id = (ability.get("related_tasks") or [None])[0]
    task = load_data()["task_by_id"].get(task_id, {}) if task_id else {}
    if status == "weak":
        return f"先看该节点讲解，再完成任务：{task.get('title', '关联实训任务')}"
    if status == "improving":
        return f"继续完成一次现场验证或复测：{task.get('title', '关联实训任务')}"
    if status == "recommended_next":
        return f"建议作为下一步训练：{task.get('title', '关联实训任务')}"
    if status == "mastered":
        return "用一个现场复述或任务提交物保持证据，安全相关能力仍需教师复核。"
    if status == "touched":
        return "补充现场证据，确认是否真的形成能力缺口。"
    return "先在真实问题或自测中产生证据，再更新个人图谱。"


def node_payload(ability_id, key, status="normal", **extra):
    ability = load_data()["ability_by_id"].get(ability_id, {})
    return {
        "id": ability_id,
        "key": key,
        "label": ability_label(ability_id),
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "source": ability_source(ability_id),
        "level": ability.get("level"),
        "parent_id": ability.get("parent_id"),
        "description": ability.get("description", ""),
        "radar_dimension_ids": ability.get("radar_dimension_ids", []),
        **extra,
    }


def append_status_classes(lines, nodes):
    class_defs = {
        "weak": "fill:#fff1f2,stroke:#e11d48,stroke-width:2px,color:#881337",
        "industry_hot": "fill:#fffbeb,stroke:#d97706,stroke-width:2px,color:#78350f",
        "industry": "fill:#eff6ff,stroke:#2563eb,stroke-width:1.5px,color:#1e3a8a",
        "core": "fill:#ecfdf5,stroke:#059669,stroke-width:1.5px,color:#064e3b",
        "touched": "fill:#eef2ff,stroke:#4f46e5,stroke-width:1.5px,color:#312e81",
        "improving": "fill:#ecfeff,stroke:#0891b2,stroke-width:2px,color:#164e63",
        "mastered": "fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#14532d",
        "recommended_next": "fill:#fff7ed,stroke:#ea580c,stroke-width:2px,color:#7c2d12",
        "unknown": "fill:#f8fafc,stroke:#94a3b8,stroke-width:1px,color:#475569",
    }
    by_status = defaultdict(list)
    for node in nodes:
        by_status[node.get("status", "normal")].append(node["key"])

    for status, keys in by_status.items():
        if status in class_defs and keys:
            lines.append(f"  classDef {status} {class_defs[status]}")
            lines.append(f"  class {','.join(keys)} {status}")


def graph_summary(nodes):
    status_counts = Counter(node.get("status", "normal") for node in nodes)
    return {
        "node_count": len(nodes),
        "status_counts": dict(status_counts),
        "weak_count": status_counts.get("weak", 0),
        "improving_count": status_counts.get("improving", 0),
        "recommended_next_count": status_counts.get("recommended_next", 0),
        "mastered_count": status_counts.get("mastered", 0),
    }


def build_ability_graph(highlight_ability_ids=None):
    highlight_ability_ids = set(normalize_ability_id(item) for item in (highlight_ability_ids or []))
    nodes = []
    edges = []
    lines = ["flowchart TD"]

    for index, ability_id in enumerate(CORE_CHAIN):
        if ability_id not in load_data()["ability_by_id"]:
            continue
        node_key = f"N{index + 1}"
        status = "weak" if ability_id in highlight_ability_ids else "normal"
        nodes.append(node_payload(ability_id, node_key, status))
        lines.append(f'  {node_key}["{mermaid_text(ability_label(ability_id))}"]')

    for index in range(len(nodes) - 1):
        edges.append({"from": nodes[index]["id"], "to": nodes[index + 1]["id"], "type": "core_chain"})
        lines.append(f"  {nodes[index]['key']} --> {nodes[index + 1]['key']}")

    append_status_classes(lines, nodes)

    return {
        "graph_type": "current_problem",
        "graph_title": "当前问题能力缺口图谱",
        "mermaid": "\n".join(lines),
        "summary": graph_summary(nodes),
        "nodes": nodes,
        "edges": edges,
    }


def industry_demand_index():
    demand = {}
    demand_sources = []
    for snapshot in load_data()["industry_demand_snapshots"] + confirmed_job_snapshots():
        source_summary = {
            "snapshot_id": snapshot.get("snapshot_id"),
            "collected_at": snapshot.get("collected_at"),
            "source_type": snapshot.get("source_type"),
            "source": snapshot.get("source"),
            "evidence": snapshot.get("evidence"),
            "weight": snapshot.get("weight", 0),
        }
        demand_sources.append(source_summary)
        snapshot_weight = float_or_zero(snapshot.get("weight", 1))
        for required in snapshot.get("required_abilities", []):
            ability_id = normalize_ability_id(required.get("ability_id"))
            if ability_id not in load_data()["ability_by_id"]:
                continue
            item = demand.setdefault(
                ability_id,
                {
                    "ability_id": ability_id,
                    "weight": 0.0,
                    "labels": set(),
                    "evidence": [],
                    "sources": set(),
                    "snapshot_ids": [],
                },
            )
            item["weight"] += snapshot_weight * float_or_zero(required.get("weight", 1))
            if required.get("demand_label"):
                item["labels"].add(required.get("demand_label"))
            if required.get("evidence"):
                item["evidence"].append(required.get("evidence"))
            if required.get("source"):
                item["sources"].add(required.get("source"))
            if snapshot.get("source"):
                item["sources"].add(snapshot.get("source"))
            item["snapshot_ids"].append(snapshot.get("snapshot_id"))

    for item in demand.values():
        item["weight"] = round(item["weight"], 2)
        item["labels"] = sorted(item["labels"])
        item["sources"] = sorted(item["sources"])
    return demand, demand_sources


def build_job_ability_graph():
    data = load_data()
    profile = primary_job_profile()
    chain = [item for item in profile.get("ability_chain", CORE_CHAIN) if item in data["ability_by_id"]]
    demand, demand_sources = industry_demand_index()
    extra_ids = [ability_id for ability_id in demand if ability_id not in chain]
    graph_ids = chain + extra_ids

    nodes = []
    edges = []
    key_by_id = {}
    lines = ["flowchart TD", f'  R["岗位: {mermaid_text(profile.get("role_name", "自动化生产线装调与运维技术员"))}"]']

    for index, ability_id in enumerate(graph_ids):
        demand_item = demand.get(ability_id, {})
        node_key = f"J{index + 1}"
        key_by_id[ability_id] = node_key
        status = "industry_hot" if demand_item.get("weight", 0) >= 1.0 else "core"
        if ability_id not in chain:
            status = "industry"
        nodes.append(
            node_payload(
                ability_id,
                node_key,
                status,
                demand_weight=demand_item.get("weight", 0),
                demand_labels=demand_item.get("labels", []),
                evidence=demand_item.get("evidence", [])[:3],
                demand_sources=demand_item.get("sources", []),
            )
        )
        lines.append(f'  {node_key}["{mermaid_text(ability_label(ability_id))}"]')

    if nodes:
        lines.append(f"  R --> {nodes[0]['key']}")
    for index in range(len(chain) - 1):
        if chain[index] in key_by_id and chain[index + 1] in key_by_id:
            edges.append({"from": chain[index], "to": chain[index + 1], "type": "job_chain"})
            lines.append(f"  {key_by_id[chain[index]]} --> {key_by_id[chain[index + 1]]}")

    for ability_id in extra_ids:
        ability = data["ability_by_id"].get(ability_id, {})
        parent_id = ability.get("parent_id")
        if parent_id in key_by_id:
            edges.append({"from": parent_id, "to": ability_id, "type": "industry_extension"})
            lines.append(f"  {key_by_id[parent_id]} --> {key_by_id[ability_id]}")
        else:
            edges.append({"from": "role", "to": ability_id, "type": "industry_extension"})
            lines.append(f"  R --> {key_by_id[ability_id]}")

    # Attach evidence metadata from SQLite
    try:
        from scripts.pipeline.evidence_store import ability_evidence_summary
        for n in nodes:
            aid = n["id"]
            ev_summary = ability_evidence_summary(aid, profile.get("role_name"))
            n["evidence_count"] = ev_summary["evidence_count"]
            n["avg_confidence"] = ev_summary["avg_confidence"]
            n["last_updated_at"] = ev_summary["last_updated_at"]
            n["source_types"] = ev_summary["source_type_distribution"]
            n["latest_evidence"] = ev_summary["latest_evidence"]
    except Exception:
        pass


    append_status_classes(lines, nodes)

    return {
        "graph_type": "job_ability",
        "graph_title": "岗位能力图谱",
        "job_role": profile.get("role_name", "自动化生产线装调与运维技术员"),
        "update_policy": data["industry_demand_data"].get("update_policy", {}),
        "demand_sources": demand_sources,
        "pending_proposals": pending_job_proposals(),
        "mermaid": "\n".join(lines),
        "summary": {
            **graph_summary(nodes),
            "demand_source_count": len(demand_sources),
            "pending_proposal_count": len(pending_job_proposals()),
        },
        "nodes": nodes,
        "edges": edges,
    }


def session_ability_state(session_id):
    engine_state = personal_graph_state(session_id, CORE_CHAIN)
    record = engine_state["record"]
    buckets = engine_state["buckets"]
    return {
        "record": record,
        "event_count": len(record.get("events", [])),
        "chat_hits": Counter({ability_id: bucket["chat"] for ability_id, bucket in buckets.items() if bucket["chat"]}),
        "weak_hits": Counter({ability_id: bucket["weak"] for ability_id, bucket in buckets.items() if bucket["weak"]}),
        "mastered_hits": Counter({ability_id: bucket["mastered"] for ability_id, bucket in buckets.items() if bucket["mastered"]}),
        "recommended_ids": set(engine_state["recommended_ids"]),
    }


def build_student_ability_graph(session_id=None):
    data = load_data()
    engine_state = personal_graph_state(session_id, CORE_CHAIN)
    buckets = engine_state["buckets"]
    touched_ids = {
        ability_id
        for ability_id, bucket in buckets.items()
        if bucket["chat"] or bucket["weak"] or bucket["mastered"] or bucket["improving"] or bucket["recommended"]
    }
    graph_ids = [item for item in CORE_CHAIN if item in data["ability_by_id"]]
    graph_ids.extend([item for item in touched_ids if item in data["ability_by_id"] and item not in graph_ids])

    nodes = []
    edges = []
    key_by_id = {}
    lines = ["flowchart TD", '  S["学生个人能力图谱"]']

    for index, ability_id in enumerate(graph_ids):
        bucket = buckets[ability_id]
        metrics = compute_node_metrics(ability_id, bucket)
        status = metrics["status"]
        evidence = list(metrics["update_reasons"])

        node_key = f"S{index + 1}"
        key_by_id[ability_id] = node_key
        nodes.append(
            node_payload(
                ability_id,
                node_key,
                status,
                evidence=evidence,
                chat_count=bucket["chat"],
                weak_count=bucket["weak"],
                improving_count=bucket["improving"],
                mastered_count=bucket["mastered"],
                mastery_score=metrics["mastery_score"],
                confidence=metrics["confidence"],
                evidence_count=metrics["evidence_count"],
                last_updated_at=metrics["last_updated_at"],
                update_reasons=metrics["update_reasons"],
                evidence_events=metrics["evidence_events"],
                next_best_action=next_best_action(ability_id, status),
            )
        )
        lines.append(f'  {node_key}["{mermaid_text(ability_label(ability_id))}"]')

    if nodes:
        lines.append(f"  S --> {nodes[0]['key']}")
    for index in range(len(CORE_CHAIN) - 1):
        if CORE_CHAIN[index] in key_by_id and CORE_CHAIN[index + 1] in key_by_id:
            edges.append({"from": CORE_CHAIN[index], "to": CORE_CHAIN[index + 1], "type": "personal_chain"})
            lines.append(f"  {key_by_id[CORE_CHAIN[index]]} --> {key_by_id[CORE_CHAIN[index + 1]]}")

    for ability_id in graph_ids:
        if ability_id in CORE_CHAIN:
            continue
        parent_id = data["ability_by_id"].get(ability_id, {}).get("parent_id")
        if parent_id in key_by_id:
            edges.append({"from": parent_id, "to": ability_id, "type": "personal_evidence"})
            lines.append(f"  {key_by_id[parent_id]} --> {key_by_id[ability_id]}")
        else:
            edges.append({"from": "student", "to": ability_id, "type": "personal_evidence"})
            lines.append(f"  S --> {key_by_id[ability_id]}")

    append_status_classes(lines, nodes)

    return {
        "graph_type": "student_ability",
        "graph_title": "学生个人能力图谱",
        "session_id": engine_state["record"].get("session_id"),
        "event_count": len(engine_state["record"].get("events", [])),
        "update_log": [
            event
            for node in nodes
            for event in node.get("evidence_events", [])
        ][-12:],
        "mermaid": "\n".join(lines),
        "summary": graph_summary(nodes),
        "nodes": nodes,
        "edges": edges,
    }
