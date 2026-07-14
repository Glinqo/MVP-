import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .data_loader import ROOT, load_data
from .feedback import append_session_event, load_session_record, safe_session_id


GRAPH_EVENTS_PATH = ROOT / "data" / "graph_update_events.json"
JOB_PROPOSALS_PATH = ROOT / "data" / "job_graph_update_proposals.json"
JOB_CONFIRMED_PATH = ROOT / "data" / "job_graph_confirmed_snapshots.json"

IMPROVING_EVENTS = {"question_explained", "practice_completed", "learning_plan_started", "learning_plan_checkpoint", "scenario_step_completed", "scenario_completed"}
WEAK_EVENTS = {"scenario_step_mistake"}
MASTERED_EVENTS = {"task_completed"}
SAFETY_REVIEW_ABILITIES = {"electrical_safety_check", "power_isolation_confirmation", "multimeter_voltage_measurement"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def float_or_zero(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_runtime_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_runtime_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


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


def event_ability_ids(event):
    ability_ids = []
    for key in ("ability_ids", "abilities", "weak_abilities", "highlighted_abilities", "related_abilities"):
        ability_ids.extend(extract_ability_ids(event.get(key, [])))
    for key in ("ability_id", "ability_node_id", "node_id"):
        if event.get(key):
            ability_ids.extend(extract_ability_ids([event.get(key)]))
    ordered = []
    for ability_id in ability_ids:
        if ability_id in load_data()["ability_by_id"] and ability_id not in ordered:
            ordered.append(ability_id)
    return ordered


def append_global_graph_event(session_id, event):
    data = read_runtime_json(GRAPH_EVENTS_PATH, {"version": "0.1.0", "source": "project_runtime", "events": []})
    event = dict(event or {})
    event["session_id"] = safe_session_id(session_id)
    event.setdefault("created_at", now_iso())
    event.setdefault("event_id", event["created_at"].replace(":", "").replace("-", "").replace(".", ""))
    data.setdefault("events", []).append(event)
    write_runtime_json(GRAPH_EVENTS_PATH, data)


def record_student_graph_event(payload):
    payload = payload or {}
    session_id = safe_session_id(payload.get("session_id"))
    ability_ids = event_ability_ids(payload)
    event = {
        "event_type": payload.get("event_type", "learning_event"),
        "ability_ids": ability_ids,
        "highlighted_abilities": [{"id": ability_id, "name": load_data()["ability_by_id"][ability_id].get("name", ability_id)} for ability_id in ability_ids],
        "question_id": payload.get("question_id"),
        "knowledge_id": payload.get("knowledge_id"),
        "task_id": payload.get("task_id"),
        "outcome": payload.get("outcome"),
        "note": payload.get("note", ""),
        "source": payload.get("source", "student_action"),
    }
    saved = append_session_event(session_id, event)
    append_global_graph_event(session_id, {**event, "created_at": now_iso()})
    return saved


def ability_event_bucket():
    return {
        "chat": 0,
        "weak": 0,
        "improving": 0,
        "mastered": 0,
        "recommended": 0,
        "last_updated_at": None,
        "reasons": [],
        "events": [],
    }


def add_bucket_event(bucket, event, reason):
    bucket["last_updated_at"] = event.get("created_at") or bucket["last_updated_at"]
    bucket["reasons"].append(reason)
    bucket["events"].append(
        {
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "created_at": event.get("created_at"),
            "reason": reason,
            "source": event.get("source"),
            "question_id": event.get("question_id"),
            "knowledge_id": event.get("knowledge_id"),
            "task_id": event.get("task_id"),
            "note": event.get("note", ""),
        }
    )


def personal_graph_state(session_id, core_chain):
    record = load_session_record(session_id)
    buckets = defaultdict(ability_event_bucket)
    recommended_names = []

    for event in record.get("events", []):
        event_type = event.get("event_type")
        ability_ids = event_ability_ids(event)

        if event_type == "chat_message":
            ability_ids = ability_ids or extract_ability_ids(event.get("highlighted_abilities", []))
            for ability_id in ability_ids:
                buckets[ability_id]["chat"] += 1
                add_bucket_event(buckets[ability_id], event, "问答命中该能力")
            recommended_names.extend(event.get("recommended_path", []))
            continue

        if event_type in {"score", "diagnosis"}:
            weak_ids = extract_ability_ids(event.get("weak_abilities", []))
            for ability_id in weak_ids:
                buckets[ability_id]["weak"] += 1
                add_bucket_event(buckets[ability_id], event, "确定性评分显示薄弱")
            if event.get("score_result", {}).get("score") == 100:
                for ability_id in core_chain:
                    buckets[ability_id]["mastered"] += 1
                    add_bucket_event(buckets[ability_id], event, "预设自测满分")
            recommended_names.extend(event.get("recommended_path", []))
            continue

        if event_type == "feedback":
            related_ids = extract_ability_ids(event.get("weak_abilities", [])) or extract_ability_ids(event.get("highlighted_abilities", []))
            feedback = event.get("feedback")
            for ability_id in related_ids:
                if feedback == "已掌握":
                    buckets[ability_id]["mastered"] += 1
                    buckets[ability_id]["weak"] = 0
                    add_bucket_event(buckets[ability_id], event, "学生反馈已掌握")
                elif feedback in {"仍不会", "需要更基础讲解"}:
                    buckets[ability_id]["weak"] += 1
                    add_bucket_event(buckets[ability_id], event, f"学生反馈{feedback}")
            recommended_names.extend(event.get("recommended_path", []))
            continue

        if event_type in IMPROVING_EVENTS:
            for ability_id in ability_ids:
                buckets[ability_id]["improving"] += 1
                add_bucket_event(buckets[ability_id], event, "讲题/练习产生改进证据")
            continue

        if event_type in WEAK_EVENTS:
            for ability_id in ability_ids:
                buckets[ability_id]["weak"] += 1
                add_bucket_event(buckets[ability_id], event, "排故角色扮演选择错误，提示该能力需补强")
            continue

        if event_type in MASTERED_EVENTS:
            for ability_id in ability_ids:
                if event.get("outcome") in {None, "", "passed", "completed"}:
                    buckets[ability_id]["mastered"] += 1
                    add_bucket_event(buckets[ability_id], event, "任务完成产生掌握证据")
                else:
                    buckets[ability_id]["improving"] += 1
                    add_bucket_event(buckets[ability_id], event, "任务完成但仍需复核")

    for ability_id in extract_ability_ids(record.get("weak_abilities", [])):
        buckets[ability_id]["weak"] += 1
    if record.get("feedback") == "已掌握":
        for ability_id in extract_ability_ids(record.get("weak_abilities", [])):
            buckets[ability_id]["mastered"] += 1
            buckets[ability_id]["weak"] = 0
    elif record.get("feedback") in {"仍不会", "需要更基础讲解"}:
        for ability_id in extract_ability_ids(record.get("weak_abilities", [])):
            buckets[ability_id]["weak"] += 1
    recommended_names.extend(record.get("recommended_path", []))

    recommended_ids = set(ability_ids_from_names(recommended_names))
    if any(bucket["weak"] for bucket in buckets.values()):
        for ability_id, bucket in list(buckets.items()):
            if not bucket["weak"]:
                continue
            ability = load_data()["ability_by_id"].get(ability_id, {})
            for prerequisite in ability.get("prerequisites", []):
                recommended_ids.add(prerequisite)
    elif any(bucket["chat"] for bucket in buckets.values()):
        touched_chain = [item for item in core_chain if buckets[item]["chat"]]
        if touched_chain:
            last_index = max(core_chain.index(item) for item in touched_chain)
            if last_index + 1 < len(core_chain):
                recommended_ids.add(core_chain[last_index + 1])

    for ability_id in recommended_ids:
        if ability_id in load_data()["ability_by_id"]:
            buckets[ability_id]["recommended"] += 1
            if not buckets[ability_id]["reasons"]:
                buckets[ability_id]["reasons"].append("推荐下一步训练")

    return {"record": record, "buckets": buckets, "recommended_ids": recommended_ids}


def compute_node_metrics(ability_id, bucket):
    evidence_count = bucket["chat"] + bucket["weak"] + bucket["improving"] + bucket["mastered"] + bucket["recommended"]
    score = 35 + bucket["chat"] * 8 + bucket["improving"] * 14 + bucket["mastered"] * 35 + bucket["recommended"] * 4 - bucket["weak"] * 22
    if evidence_count == 0:
        score = 30
    if ability_id in SAFETY_REVIEW_ABILITIES and bucket["mastered"]:
        score = min(score, 80)
    score = max(0, min(100, int(score)))
    confidence = round(min(0.95, 0.2 + evidence_count * 0.13), 2)

    if bucket["mastered"] and not bucket["weak"] and ability_id not in SAFETY_REVIEW_ABILITIES:
        status = "mastered"
    elif bucket["weak"] and bucket["improving"]:
        status = "improving"
    elif bucket["weak"]:
        status = "weak"
    elif bucket["improving"] or (bucket["mastered"] and ability_id in SAFETY_REVIEW_ABILITIES):
        status = "improving"
    elif bucket["recommended"]:
        status = "recommended_next"
    elif bucket["chat"]:
        status = "touched"
    else:
        status = "unknown"

    reasons = list(dict.fromkeys(bucket["reasons"]))
    if ability_id in SAFETY_REVIEW_ABILITIES and bucket["mastered"]:
        reasons.append("安全相关能力需教师或实训指导人员复核")

    return {
        "status": status,
        "mastery_score": score,
        "confidence": confidence,
        "evidence_count": evidence_count,
        "last_updated_at": bucket["last_updated_at"],
        "update_reasons": reasons[:5],
        "evidence_events": bucket["events"][-6:],
    }


def graph_update_timeline(session_id):
    record = load_session_record(session_id)
    updates = []
    for event in record.get("events", []):
        ability_ids = event_ability_ids(event)
        if not ability_ids and event.get("event_type") == "chat_message":
            ability_ids = extract_ability_ids(event.get("highlighted_abilities", []))
        if not ability_ids:
            continue
        for ability_id in ability_ids:
            updates.append(
                {
                    "created_at": event.get("created_at"),
                    "event_type": event.get("event_type"),
                    "ability_id": ability_id,
                    "ability_name": load_data()["ability_by_id"].get(ability_id, {}).get("name", ability_id),
                    "reason": event.get("note") or event.get("feedback") or event.get("matched_pattern", {}).get("title") or "图谱证据更新",
                    "source": event.get("source") or "session_event",
                }
            )
    return {"session_id": safe_session_id(session_id), "updates": updates}


def proposal_id():
    return "JP" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


def keyword_hits(material, ability):
    text = material.lower()
    terms = {ability.get("name", ""), ability.get("id", ""), ability.get("description", "")}
    terms.update(ability.get("common_errors", []))
    terms.update(ability.get("related_knowledge", []))
    aliases = {
        "sensor_type_identification": ["npn", "pnp", "传感器类型", "型号", "线色"],
        "sensor_wiring_judgement": ["接线", "端子", "输出线", "黑线", "三线制"],
        "plc_input_common_terminal": ["公共端", "com", "s/s", "输入公共端"],
        "plc_io_address_mapping": ["i/o", "io", "地址", "变量", "映射"],
        "plc_input_monitoring": ["监控", "输入灯", "在线", "输入信号"],
        "input_no_response_fault_scope": ["排故", "无响应", "故障", "定位"],
        "electrical_safety_check": ["安全", "断电", "急停", "气源"],
    }
    terms.update(aliases.get(ability.get("id"), []))
    score = 0
    evidence = []
    for term in terms:
        term = str(term).strip()
        if not term:
            continue
        if term.lower() in text:
            score += 1
            evidence.append(term)
    return score, evidence[:4]


def generate_job_graph_proposals(payload):
    payload = payload or {}
    material = payload.get("material", "") or payload.get("text", "")
    source = payload.get("source", "teacher_imported_material")
    source_type = payload.get("source_type", "teacher_curated")
    if not material.strip():
        raise ValueError("material is required")

    scored = []
    for ability in load_data()["abilities"]:
        score, evidence = keyword_hits(material, ability)
        if score:
            scored.append((score, ability, evidence))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        scored = [(1, load_data()["ability_by_id"][ability_id], ["默认岗位主链"]) for ability_id in list(load_data()["ability_by_id"])[:3]]

    batch_id = proposal_id()
    created_at = now_iso()
    proposals = []
    for score, ability, evidence_terms in scored[:6]:
        action = "strengthen" if ability.get("id") in {"sensor_wiring_judgement", "plc_input_common_terminal", "input_no_response_fault_scope"} else "add_evidence"
        proposals.append(
            {
                "proposal_id": f"{batch_id}-{len(proposals) + 1:02d}",
                "batch_id": batch_id,
                "status": "pending",
                "created_at": created_at,
                "source_type": source_type,
                "source": source,
                "ability_id": ability.get("id"),
                "ability_name": ability.get("name"),
                "action": action,
                "suggested_weight_delta": round(min(0.5, 0.08 * score), 2),
                "evidence": f"材料命中关键词：{'、'.join(evidence_terms)}",
                "material_excerpt": re.sub(r"\s+", " ", material.strip())[:180],
            }
        )

    store = read_runtime_json(JOB_PROPOSALS_PATH, {"version": "0.1.0", "source": "project_runtime", "proposal_batches": [], "proposals": []})
    store.setdefault("proposal_batches", []).append(
        {
            "batch_id": batch_id,
            "created_at": created_at,
            "source_type": source_type,
            "source": source,
            "material_excerpt": re.sub(r"\s+", " ", material.strip())[:240],
            "proposal_count": len(proposals),
        }
    )
    store.setdefault("proposals", []).extend(proposals)
    write_runtime_json(JOB_PROPOSALS_PATH, store)
    return {"batch_id": batch_id, "proposals": proposals}


def pending_job_proposals():
    store = read_runtime_json(JOB_PROPOSALS_PATH, {"version": "0.1.0", "source": "project_runtime", "proposal_batches": [], "proposals": []})
    return [item for item in store.get("proposals", []) if item.get("status") == "pending"]


def confirmed_job_snapshots():
    store = read_runtime_json(JOB_CONFIRMED_PATH, {"version": "0.1.0", "source": "project_runtime", "snapshots": []})
    return store.get("snapshots", [])


def confirm_job_graph_proposals(payload):
    payload = payload or {}
    proposal_ids = set(payload.get("proposal_ids", []))
    confirm_all = bool(payload.get("confirm_all"))
    teacher = payload.get("confirmed_by", "teacher")
    store = read_runtime_json(JOB_PROPOSALS_PATH, {"version": "0.1.0", "source": "project_runtime", "proposal_batches": [], "proposals": []})
    proposals = []
    for proposal in store.get("proposals", []):
        if proposal.get("status") != "pending":
            continue
        if confirm_all or proposal.get("proposal_id") in proposal_ids:
            proposal["status"] = "confirmed"
            proposal["confirmed_at"] = now_iso()
            proposal["confirmed_by"] = teacher
            proposals.append(proposal)

    if not proposals:
        raise ValueError("no pending proposals selected")

    snapshot = {
        "snapshot_id": "CONF" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"),
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source_type": "teacher_confirmed_update",
        "source": f"confirmed_by:{teacher}",
        "job_role": "自动化生产线装调与运维技术员",
        "evidence": "教师确认的岗位能力图谱更新建议。",
        "weight": 0.8,
        "required_abilities": [
            {
                "ability_id": proposal.get("ability_id"),
                "demand_label": "确认更新",
                "evidence": proposal.get("evidence"),
                "weight": max(0.1, proposal.get("suggested_weight_delta", 0.1)),
                "source": proposal.get("source"),
            }
            for proposal in proposals
        ],
    }
    confirmed_store = read_runtime_json(JOB_CONFIRMED_PATH, {"version": "0.1.0", "source": "project_runtime", "snapshots": []})
    confirmed_store.setdefault("snapshots", []).append(snapshot)
    write_runtime_json(JOB_CONFIRMED_PATH, confirmed_store)
    write_runtime_json(JOB_PROPOSALS_PATH, store)
    return {"confirmed": True, "snapshot": snapshot, "confirmed_proposals": proposals}


def generate_proposals_from_evidence(job_role=None):
    """Read evidence from SQLite, compute scores, generate proposals"""
    try:
        from scripts.pipeline.evidence_store import query_events, add_proposal, compute_proposal_score, proposal_threshold
        from .data_loader import primary_job_profile
        
        events = query_events(job_role=(job_role or None), limit=1000)
        abilities = {}
        for ev in events:
            aid = ev["ability_id"]
            if aid not in abilities:
                abilities[aid] = {"count": 0, "source_types": set(), "confs": []}
            abilities[aid]["count"] += 1
            abilities[aid]["source_types"].add(ev.get("source_type", "unknown"))
            abilities[aid]["confs"].append(ev.get("confidence", 0.5))

        target_role = job_role or primary_job_profile().get("role_name", "自动化生产线装调与运维技术员")
        proposals = []
        for aid, data in abilities.items():
            srclist = list(data["source_types"])
            source_type = srclist[0] if srclist else "unknown"
            avg_conf = sum(data["confs"]) / len(data["confs"]) if data["confs"] else 0.5
            score = compute_proposal_score(source_type, avg_conf, data["count"], 7)
            threshold = proposal_threshold(score)
            if threshold in ("auto_approve", "pending"):
                evidence_text = f"{data['count']} 条证据，平均置信度 {round(avg_conf, 2)}"
                pr = add_proposal(
                    job_role=target_role,
                    ability_id=aid,
                    action="strengthen",
                    suggested_weight_delta=round(score * 0.2, 2),
                    evidence=evidence_text,
                    source="evidence_aggregation",
                    proposal_score=score
                )
                pr["threshold"] = threshold
                pr["evidence_count"] = data["count"]
                proposals.append(pr)
        return proposals
    except Exception as e:
        return {"error": str(e)}


def dimension_scores_from_nodes(nodes):
    scores = defaultdict(float)
    for node in nodes:
        weight = float_or_zero(node.get("demand_weight") or node.get("weight") or 0)
        dimensions = node.get("radar_dimension_ids") or ["unknown"]
        for dimension_id in dimensions:
            scores[dimension_id] += weight
    return {key: round(value, 2) for key, value in sorted(scores.items())}


def build_confirmed_proposal_snapshot(job_role, proposals):
    """Create a versioned job graph snapshot after SQLite proposals are confirmed."""
    from app.services.graph import ability_label, build_job_ability_graph, node_payload
    from scripts.pipeline.evidence_store import ability_evidence_summary, create_snapshot

    graph = build_job_ability_graph()
    nodes = [dict(node) for node in graph.get("nodes", [])]
    by_id = {node["id"]: node for node in nodes}

    for proposal in proposals:
        ability_id = proposal.get("ability_id")
        if not ability_id:
            continue
        node = by_id.get(ability_id)
        if not node:
            node = node_payload(ability_id, f"C{len(nodes) + 1}", "industry")
            node["demand_weight"] = 0
            node["evidence"] = []
            node["demand_sources"] = []
            nodes.append(node)
            by_id[ability_id] = node

        delta = float_or_zero(proposal.get("suggested_weight_delta"))
        node["demand_weight"] = round(float_or_zero(node.get("demand_weight")) + delta, 2)
        node["status"] = "industry_hot" if float_or_zero(proposal.get("proposal_score")) >= 0.75 else "industry"
        node["status_label"] = "教师确认更新"
        node.setdefault("evidence", [])
        if proposal.get("evidence"):
            node["evidence"] = list(dict.fromkeys(node["evidence"] + [proposal.get("evidence")]))[:5]
        node.setdefault("demand_sources", [])
        if proposal.get("source"):
            node["demand_sources"] = list(dict.fromkeys(node["demand_sources"] + [proposal.get("source")]))
        node["confirmed_proposal_id"] = proposal.get("proposal_id")
        node["confirmed_by"] = proposal.get("confirmed_by")
        node["confirmed_at"] = proposal.get("confirmed_at")
        node["proposal_score"] = proposal.get("proposal_score")
        node["label"] = node.get("label") or ability_label(ability_id)

    for node in nodes:
        evidence = ability_evidence_summary(node["id"], job_role)
        node["evidence_count"] = evidence["evidence_count"]
        node["avg_confidence"] = evidence["avg_confidence"]
        node["last_updated_at"] = evidence["last_updated_at"]
        node["source_types"] = evidence["source_type_distribution"]
        node["latest_evidence"] = evidence["latest_evidence"]

    dimension_scores = dimension_scores_from_nodes(nodes)
    version = datetime.now(timezone.utc).strftime("v%Y%m%d.%H%M%S.%f")
    snapshot = create_snapshot(job_role, nodes, dimension_scores, version)
    return {
        "snapshot": snapshot,
        "snapshot_graph": {
            "graph_type": "job_ability_snapshot",
            "job_role": job_role,
            "created_from": "confirmed_sqlite_proposals",
            "confirmed_proposal_ids": [item.get("proposal_id") for item in proposals],
            "nodes": nodes,
            "edges": graph.get("edges", []),
            "dimension_scores": dimension_scores,
        },
    }


def confirm_sqlite_job_graph_proposal(payload):
    """Confirm/reject a SQLite proposal and create a graph snapshot on confirmation."""
    from scripts.pipeline.evidence_store import confirm_proposal, reject_proposal

    proposal_id = payload.get("proposal_id", "")
    action = payload.get("action", "confirm")
    if action == "reject":
        return {"action": "reject", "proposal": reject_proposal(proposal_id), "snapshot": None}

    proposal = confirm_proposal(proposal_id, payload.get("confirmed_by", "teacher"))
    if proposal.get("error"):
        return {"action": "confirm", "proposal": proposal, "snapshot": None}

    snapshot_result = build_confirmed_proposal_snapshot(proposal.get("job_role"), [proposal])
    return {
        "action": "confirm",
        "proposal": proposal,
        "snapshot": snapshot_result["snapshot"],
        "snapshot_graph": snapshot_result["snapshot_graph"],
    }


def confirm_sqlite_job_graph_proposals(payload):
    """Confirm/reject multiple SQLite proposals and snapshot confirmed changes by job role."""
    from collections import defaultdict
    from scripts.pipeline.evidence_store import confirm_proposal, get_pending_proposals, reject_proposal

    payload = payload or {}
    action = payload.get("action", "confirm")
    confirmed_by = payload.get("confirmed_by", "teacher")
    job_role = payload.get("job_role")
    proposal_ids = list(dict.fromkeys(payload.get("proposal_ids") or []))

    if payload.get("confirm_all"):
        proposal_ids = [item["proposal_id"] for item in get_pending_proposals(job_role)]
    if not proposal_ids:
        raise ValueError("proposal_ids or confirm_all is required")

    proposals = []
    errors = []
    if action == "reject":
        for proposal_id in proposal_ids:
            result = reject_proposal(proposal_id)
            if result.get("error"):
                errors.append({"proposal_id": proposal_id, "error": result["error"]})
            else:
                proposals.append(result)
        return {
            "action": "reject",
            "requested_count": len(proposal_ids),
            "rejected_count": len(proposals),
            "proposals": proposals,
            "errors": errors,
            "snapshots": [],
        }

    by_role = defaultdict(list)
    for proposal_id in proposal_ids:
        proposal = confirm_proposal(proposal_id, confirmed_by)
        if proposal.get("error"):
            errors.append({"proposal_id": proposal_id, "error": proposal["error"]})
            continue
        proposals.append(proposal)
        by_role[proposal.get("job_role")].append(proposal)

    snapshots = []
    for role, role_proposals in by_role.items():
        snapshot_result = build_confirmed_proposal_snapshot(role, role_proposals)
        snapshots.append({
            "job_role": role,
            "snapshot": snapshot_result["snapshot"],
            "snapshot_graph": snapshot_result["snapshot_graph"],
        })

    return {
        "action": "confirm",
        "requested_count": len(proposal_ids),
        "confirmed_count": len(proposals),
        "proposals": proposals,
        "errors": errors,
        "snapshots": snapshots,
    }
