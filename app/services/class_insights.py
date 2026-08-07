# -*- coding: utf-8 -*-
"""班级洞察服务 - 阶段三。
提供班级平均能力图谱聚合和共性问题发现。
"""
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
USER_DB = ROOT / "data" / "users.db"
ASSESS_DB = ROOT / "data" / "assessments.db"

# Status thresholds (matches ability_state_engine)
MASTERY_THRESHOLD = 75
IMPROVING_THRESHOLD = 55
WEAK_THRESHOLD = 35

DEFAULT_JOB = "automation_line_commissioning_maintenance_newcomer"

def _query_db(db_path: Path, sql: str, params=()) -> List[Dict]:
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("DB query failed (%s): %s", db_path.name, e)
        return []

def _get_student_sessions(job_role: str) -> List[str]:
    """获取该岗位下所有有测评记录的学生 session_id 列表。"""
    rows = _query_db(ASSESS_DB,
        "SELECT session_id FROM assessments WHERE job_role = ? AND state = 'completed'",
        (job_role,))
    return [r["session_id"] for r in rows]

def _classify_status(cognitive_mastery_score: float) -> str:
    s = cognitive_mastery_score
    if s >= MASTERY_THRESHOLD:
        return "mastered"
    elif s >= IMPROVING_THRESHOLD:
        return "improving"
    elif s >= WEAK_THRESHOLD:
        return "weak"
    else:
        return "critical"

def get_class_ability_graph(job_role=None, ability_id=None):
    """获取班级平均能力图谱。

    以岗位能力图谱为骨架，聚合该岗位下所有有测评记录学生的能力状态。
    """
    jr = job_role or DEFAULT_JOB

    try:
        from app.services.graph import build_job_ability_graph
        job_graph = build_job_ability_graph(jr)
    except Exception as e:
        logger.warning("Failed to build job graph: %s", e)
        job_graph = {"nodes": [], "edges": []}

    if ability_id:
        node_ids = {ability_id}
    else:
        node_ids = {n.get("id", "") for n in job_graph.get("nodes", [])}

    sessions = _get_student_sessions(jr)

    # 聚合数据结构
    node_scores = {nid: [] for nid in node_ids}
    node_statuses = {nid: [] for nid in node_ids}
    student_count = len(sessions)
    evidence_students = {nid: 0 for nid in node_ids}

    try:
        from app.services.ability_state_engine import compute_ability_state
    except Exception:
        compute_ability_state = None

    for sess in sessions:
        if compute_ability_state:
            try:
                state = compute_ability_state(sess)
                abilities = state.get("abilities", {}) if state else {}
            except Exception:
                abilities = {}
        else:
            abilities = {}

        for nid in node_ids:
            ab = abilities.get(nid, {})
            score = ab.get("cognitive_mastery_score")
            status = ab.get("status", "")
            if score is not None:
                node_scores[nid].append(score)
                evidence_students[nid] += 1
            if status:
                node_statuses[nid].append(status)

    # 聚合入节点
    enriched_nodes = []
    for node in job_graph.get("nodes", []):
        nid = node.get("id", "")
        if ability_id and nid != ability_id:
            continue

        scores = node_scores.get(nid, [])
        statuses = node_statuses.get(nid, [])
        ev_count = evidence_students.get(nid, 0)

        if not scores:
            enriched_nodes.append({**node,
                "class_stats": {
                    "student_count": student_count,
                    "evidence_student_count": 0,
                    "evidence_coverage": 0.0,
                    "mean_mastery": None,
                    "median_mastery": None,
                    "weak_count": 0,
                    "weak_ratio": 0.0,
                    "improving_count": 0,
                    "improving_ratio": 0.0,
                    "mastered_count": 0,
                    "mastered_ratio": 0.0,
                    "critical_count": 0,
                }
            })
            continue

        s_sorted = sorted(scores)
        n = len(s_sorted)
        mean = sum(s_sorted) / n
        mid = n // 2
        median = (s_sorted[mid] + s_sorted[~mid]) / 2 if n % 2 == 0 else s_sorted[mid]

        weak_c = sum(1 for s in scores if s < IMPROVING_THRESHOLD)
        imp_c = sum(1 for s in scores if IMPROVING_THRESHOLD <= s < MASTERY_THRESHOLD)
        mas_c = sum(1 for s in scores if s >= MASTERY_THRESHOLD)
        crit_c = sum(1 for s in scores if s < WEAK_THRESHOLD)

        coverage = ev_count / max(student_count, 1)

        enriched_nodes.append({**node,
            "class_stats": {
                "student_count": student_count,
                "evidence_student_count": ev_count,
                "evidence_coverage": round(coverage, 3),
                "mean_mastery": round(mean, 1),
                "median_mastery": round(median, 1),
                "weak_count": weak_c,
                "weak_ratio": round(weak_c / n, 3) if n else 0.0,
                "improving_count": imp_c,
                "improving_ratio": round(imp_c / n, 3) if n else 0.0,
                "mastered_count": mas_c,
                "mastered_ratio": round(mas_c / n, 3) if n else 0.0,
                "critical_count": crit_c,
            }
        })

    overview = {
        "job_role": jr,
        "total_students": student_count,
        "evidence_students": len([r for r in enriched_nodes if r.get("class_stats", {}).get("evidence_student_count", 0) > 0]),
        "nodes_with_evidence": sum(1 for n in enriched_nodes if n.get("class_stats", {}).get("evidence_student_count", 0) > 0),
        "weak_nodes": sum(1 for n in enriched_nodes if n.get("class_stats", {}).get("weak_ratio", 0) > 0.3),
        "has_data": student_count > 0,
    }
    try:
        overview["common_issue_count"] = len(get_common_issues(jr))
    except Exception:
        overview["common_issue_count"] = 0

    return {
        "job_role": jr,
        "overview": overview,
        "nodes": enriched_nodes,
        "edges": job_graph.get("edges", []),
    }

def get_common_issues(job_role=None, ability_id=None, min_students=3):
    """基于学习事件发现共性问题。

    第一版使用规则聚合：同一 ability_id + event_category 在多学生中出现。
    """
    jr = job_role or DEFAULT_JOB
    sessions = _get_student_sessions(jr)
    if not sessions:
        return []

    try:
        from app.services.learning_event_store import get_events
    except Exception:
        get_events = None

    if not get_events:
        return []

    # 收集所有学生的错误/薄弱事件
    issue_groups = {}  # key: (ability_id, event_category) -> {student_ids: set, events: [], severity: ...}
    job_graph_nodes = {}
    try:
        from app.services.graph import build_job_ability_graph
        g = build_job_ability_graph(jr)
        job_graph_nodes = {n["id"]: n for n in g.get("nodes", [])}
    except Exception:
        pass

    for sess in sessions:
        try:
            events = get_events(sess, limit=50) or []
        except Exception:
            events = []

        for ev in events:
            aid = ev.get("ability_id", "") or ev.get("ability", "")
            if not aid:
                continue
            if ability_id and aid != ability_id:
                continue

            cat = ev.get("category", "") or ev.get("event_type", "") or "unknown"
            st = ev.get("status", "") or ev.get("result", "")
            is_negative = st in ("wrong", "incorrect", "error", "fail", "weak", "critical", "仍不会")

            if not is_negative:
                continue

            key = (aid, cat)
            if key not in issue_groups:
                issue_groups[key] = {"student_ids": set(), "events": [], "total_strength": 0}
            issue_groups[key]["student_ids"].add(sess)
            issue_groups[key]["events"].append(ev)
            issue_groups[key]["total_strength"] += 1

    # 过滤人数不足的
    issues = []
    for (aid, cat), group in issue_groups.items():
        if len(group["student_ids"]) < min_students:
            continue

        node = job_graph_nodes.get(aid, {})
        job_importance = node.get("demand_weight", 0.5)
        affected_ratio = len(group["student_ids"]) / max(len(sessions), 1)

        # 严重程度：基于错误事件占比
        severity = min(1.0, group["total_strength"] / max(len(group["student_ids"]) * 3, 1))

        # 可信度：基于证据数量
        confidence = min(1.0, len(group["events"]) / 10.0) if len(group["events"]) >= 2 else 0.3

        # 优先级
        priority = round(affected_ratio * 0.4 + job_importance * 0.3 + severity * 0.2 + confidence * 0.1, 3)

        # 证据摘要
        evidence_summary = {
            "total_events": len(group["events"]),
            "event_categories": list(set(e.get("category", "") or e.get("event_type", "") for e in group["events"][:5])),
            "sample_event": str(group["events"][0].get("description", "") or group["events"][0].get("event_type", ""))[:120],
        }

        title = (node.get("label", "") or node.get("name", "") or aid) + " - " + cat
        if len(title) > 80:
            title = title[:77] + "..."

        issues.append({
            "issue_id": f"CI_{aid}_{cat}".replace(" ", "_")[:40],
            "title": title,
            "ability_id": aid,
            "ability_name": node.get("label", "") or node.get("name", ""),
            "event_category": cat,
            "affected_student_count": len(group["student_ids"]),
            "affected_ratio": round(affected_ratio, 3),
            "job_importance": round(job_importance, 3),
            "severity": round(severity, 3),
            "confidence": round(confidence, 3),
            "priority": priority,
            "evidence_summary": evidence_summary,
            "student_ids": list(group["student_ids"])[:20],
        })

    # 按优先级降序
    issues.sort(key=lambda x: x["priority"], reverse=True)

    return issues

def get_class_overview(job_role=None):
    """获取班级概览统计。"""
    jr = job_role or DEFAULT_JOB
    sessions = _get_student_sessions(jr)
    student_count = len(sessions)

    graph = get_class_ability_graph(jr)

    weak_nodes = [n for n in graph.get("nodes", []) if n.get("class_stats", {}).get("weak_ratio", 0) > 0.3]
    try:
        common_issues = get_common_issues(jr)
    except Exception:
        common_issues = []

    return {
        "job_role": jr,
        "total_students": student_count,
        "assessed_students": student_count,
        "weak_node_count": len(weak_nodes),
        "common_issue_count": len(common_issues),
        "high_priority_issues": len([i for i in common_issues if i["priority"] > 0.5]),
        "has_data": student_count > 0,
    }

