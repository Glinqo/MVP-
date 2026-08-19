# -*- coding: utf-8 -*-
"""教师端学生管理服务 - 阶段二。
聚合用户数据、测评结果、能力状态和学习事件，为教师提供统一的学生列表和详情。
"""
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
USER_DB = ROOT / "data" / "users.db"
ASSESS_DB = ROOT / "data" / "assessments.db"

def _query_users_db(sql: str, params=()) -> List[Dict]:
    try:
        conn = sqlite3.connect(str(USER_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("users.db query failed: %s", e)
        return []

def _query_assess_db(sql: str, params=()) -> List[Dict]:
    try:
        conn = sqlite3.connect(str(ASSESS_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("assessments.db query failed: %s", e)
        return []

def list_teacher_students(
    job_role=None,
    search=None,
    has_assessment=None,
):
    """列出教师管理范围内的学生，聚合测评和能力数据。"""
    sql = "SELECT id, username, nickname, role, job_role, updated_at FROM users WHERE role = 'student'"
    params = []
    if job_role:
        sql += " AND job_role = ?"
        params.append(job_role)
    if search:
        sql += " AND (username LIKE ? OR nickname LIKE ?)"
        p = "%" + search + "%"
        params.extend([p, p])
    users = _query_users_db(sql, tuple(params))

    if not users:
        return {"students": [], "total": 0, "stats": {"total": 0, "assessed": 0, "not_assessed": 0}}

    assess_rows = _query_assess_db(
        "SELECT session_id, job_role, state, result_json, completed_at FROM assessments"
    )
    assess_map = {}
    for row in assess_rows:
        sid = row.get("session_id", "")
        assess_map[sid] = row

    students = []
    stats = {"total": len(users), "assessed": 0, "not_assessed": 0}

    for u in users:
        username = u.get("username", "")
        nickname = u.get("nickname", "User_" + username)
        user_job_role = u.get("job_role", "") or ""
        sess_id = user_job_role + "-" + username if user_job_role else ""
        assess = assess_map.get(sess_id) or _find_session_for_user(username, assess_map)

        if job_role:
            student_jr = (assess and assess.get("job_role")) or user_job_role
            if student_jr and student_jr != job_role:
                continue
        if has_assessment == "true" and not assess:
            continue
        if has_assessment == "false" and assess and assess.get("completed"):
            continue

        overall_score = 0
        assess_state = "not_started"
        completed = False
        completed_at = None

        if assess:
            overall_score = _parse_score(assess.get("result_json"))
            assess_state = assess.get("assess_state", "not_started")
            completed = (assess.get("state", "") == "completed")
            completed_at = assess.get("completed_at")

        status = _student_status(overall_score, completed)
        actual_job_role = (assess and assess.get("job_role")) or user_job_role or "未选择岗位"

        student = {
            "username": username,
            "nickname": nickname,
            "job_role": actual_job_role,
            "overall_score": overall_score,
            "status": status,
            "assess_state": assess_state,
            "completed": completed,
            "completed_at": completed_at,
            "recent_activity": None,
            "weak_abilities": [],
        }

        if assess and completed:
            stats["assessed"] += 1
        else:
            stats["not_assessed"] += 1

        students.append(student)

    return {"students": students, "total": len(students), "stats": stats}

def get_teacher_student_detail(username: str, job_role=None):
    """获取单个学生的详细档案，聚合所有可用数据。"""
    user = _query_users_db(
        "SELECT id, username, nickname, role, job_role, updated_at FROM users WHERE username = ?",
        (username,)
    )
    if not user:
        return {"error": "学生不存在", "username": username}
    u = user[0]

    user_job_role = u.get("job_role", "") or job_role or ""
    DEFAULT_JOB = "automation_line_commissioning_maintenance_newcomer"
    if user_job_role:
        sess_id = user_job_role + "-" + username
    elif job_role:
        sess_id = job_role + "-" + username
    else:
        sess_id = DEFAULT_JOB + "-" + username

    assess_rows = _query_assess_db(
        "SELECT session_id, job_role, state, result_json, completed_at, answers_json FROM assessments WHERE session_id = ?",
        (sess_id,)
    )
    assess = assess_rows[0] if assess_rows else None

    overall_score = 0
    weak_abilities = []
    strong_abilities = []
    dimension_scores = {}
    completed = False
    completed_at = None

    if assess:
        result_json_str = assess.get("result_json", "")
        if result_json_str:
            try:
                result = json.loads(result_json_str) if isinstance(result_json_str, str) else result_json_str
                overall_score = result.get("total_score", 0)
                weak_abilities = result.get("weak_abilities", [])
                strong_abilities = result.get("strong_abilities", [])
                dimension_scores = result.get("dimension_scores", {})
            except Exception:
                pass
        completed = (assess.get("state", "") == "completed")
        completed_at = assess.get("completed_at")

    actual_job_role = (assess and assess.get("job_role")) or user_job_role or "未选择岗位"
    status = _student_status(overall_score, completed)

    recent_events = _get_recent_events(sess_id, limit=10)
    ability_state = _get_ability_state_safe(sess_id)

    # P10: Aggregate diagnosis + evidence coverage
    diagnostic_patterns = _get_diagnostic_patterns_safe(username, sess_id)
    event_count = len(recent_events)
    evidence_count = _get_evidence_count_safe(sess_id)
    last_activity = recent_events[0].get("timestamp") if recent_events else None

    return {
        "username": username,
        "nickname": u.get("nickname", "User_" + username),
        "job_role": actual_job_role,
        "overall_score": overall_score,
        "status": status,
        "completed": completed,
        "completed_at": completed_at,
        "dimension_scores": dimension_scores,
        "weak_abilities": weak_abilities,
        "strong_abilities": strong_abilities,
        "recent_events": recent_events,
        "ability_state": ability_state,
        # P10: Enhanced profile fields
        "diagnostic_patterns": diagnostic_patterns,
        "event_count": event_count,
        "evidence_count": evidence_count,
        "last_activity_at": last_activity,
        "evidence_coverage": min(1.0, evidence_count / 20.0) if evidence_count else 0.0,
    }

def _get_diagnostic_patterns_safe(username, session_id):
    """Safe diagnostic pattern query for student profile."""
    try:
        from app.services.diagnostic_events import get_diagnostic_events
        events = get_diagnostic_events(session_id) if hasattr(get_diagnostic_events, "__call__") else []
        return events or []
    except Exception:
        return []

def _get_evidence_count_safe(session_id):
    """Count learning evidence for student."""
    try:
        from app.services.learning_event_store import get_events
        events = get_events(session_id, limit=200)
        return len(events or [])
    except Exception:
        return 0

def _parse_score(result_json):
    if not result_json:
        return 0
    try:
        if isinstance(result_json, str):
            r = json.loads(result_json)
        else:
            r = result_json
        return int(r.get("total_score", 0))
    except Exception:
        return 0

def _student_status(score, completed):
    if not completed:
        return "未测评"
    if score >= 80:
        return "良好"
    if score >= 60:
        return "正常"
    if score >= 40:
        return "需关注"
    return "高风险"

def _find_session_for_user(username, assess_map):
    for sid, row in assess_map.items():
        if sid.endswith("-" + username):
            return row
    return None

def _get_recent_events(session_id, limit=10):
    try:
        from app.services.learning_event_store import get_events
        events = get_events(session_id, limit=limit)
        return events or []
    except Exception:
        return []

def _get_ability_state_safe(session_id):
    try:
        from app.services.ability_state_engine import compute_ability_state
        state = compute_ability_state(session_id)
        return state or {}
    except Exception:
        return {}


def save_teacher_student_selection(username, job_role, student_usernames):
    """[DEPRECATED] 保存教师勾选的学生账号。

    TF-6D 班级-学生管理正式上线后，该临时 selection 不再承担业务作用域。
    保留此函数仅为旧接口兼容；新 UI 使用 /api/teacher/classes 和班级成员表。
    """
    import json as _json
    from pathlib import Path as _Path
    selection_path = _Path(__file__).resolve().parents[2] / "data" / "teacher_student_selections.json"
    data = {}
    if selection_path.exists():
        try:
            data = _json.loads(selection_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    entry = {
        "job_role": job_role,
        "student_usernames": list(student_usernames or []),
        "updated_at": time.time(),
    }
    data[username or "demo"] = entry
    selection_path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "saved": entry}

