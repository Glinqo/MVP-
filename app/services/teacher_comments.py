# -*- coding: utf-8 -*-
"""教师评语服务 - 阶段四。

提供评语持久化、AI 生成、编辑、审核、发布、批量操作和学生端查看。
"""
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "teacher_comments.db"

DEFAULT_JOB = "automation_line_commissioning_maintenance_newcomer"

# ── DB ──

def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute("PRAGMA journal_mode=WAL")
    c.row_factory = sqlite3.Row
    return c

def _ensure_table():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teacher_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                teacher_id TEXT NOT NULL DEFAULT "",
                job_role TEXT NOT NULL DEFAULT "",
                period_start TEXT NOT NULL DEFAULT "",
                period_end TEXT NOT NULL DEFAULT "",
                content TEXT NOT NULL DEFAULT "",
                ai_draft TEXT NOT NULL DEFAULT "",
                evidence_json TEXT NOT NULL DEFAULT "[]",
                status TEXT NOT NULL DEFAULT "draft",
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                reviewed_at REAL,
                published_at REAL
            )
        """)
        # P6-F: Migration - add class_id column if missing
        table_info = conn.execute("PRAGMA table_info(teacher_comments)").fetchall()
        cols = {row["name"] for row in table_info}
        if "class_id" not in cols:
            conn.execute("ALTER TABLE teacher_comments ADD COLUMN class_id INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_student ON teacher_comments(student_id, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_status ON teacher_comments(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_class ON teacher_comments(class_id, student_id)")
        conn.commit()
_ensure_table()

# ── CRUD ──

def list_comments(student_id=None, status=None, teacher_id=None, job_role=None, class_id=None) -> Dict:
    sql = "SELECT * FROM teacher_comments WHERE 1=1"
    params = []
    if student_id:
        sql += " AND student_id = ?"
        params.append(student_id)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if job_role:
        sql += " AND job_role = ?"
        params.append(job_role)
    if class_id:
        sql += " AND class_id = ?"
        params.append(int(class_id))
    sql += " ORDER BY created_at DESC LIMIT 200"

    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    comments = [_row_to_dict(r) for r in rows]

    stats = _compute_stats(teacher_id, job_role)

    return {"comments": comments, "total": len(comments), "stats": stats}

def _compute_stats(teacher_id=None, job_role=None) -> Dict:
    base = "FROM teacher_comments WHERE 1=1"
    params = []
    if job_role:
        base += " AND job_role = ?"
        params.append(job_role)

    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) " + base, params).fetchone()[0]
        draft = conn.execute("SELECT COUNT(*) " + base + " AND status='draft'", params).fetchone()[0]
        reviewed = conn.execute("SELECT COUNT(*) " + base + " AND status='reviewed'", params).fetchone()[0]
        published = conn.execute("SELECT COUNT(*) " + base + " AND status='published'", params).fetchone()[0]
    return {
        "total": total, "draft": draft, "reviewed": reviewed, "published": published
    }

def get_comment(comment_id: int) -> Optional[Dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM teacher_comments WHERE id = ?", (comment_id,)).fetchone()
    return _row_to_dict(row) if row else None

def _row_to_dict(row) -> Dict:
    d = dict(row)
    try:
        d["evidence"] = json.loads(d.pop("evidence_json", "[]") or "[]")
    except Exception:
        d["evidence"] = []
    return d

def save_comment(comment_id: int, content: str) -> Dict:
    now = time.time()
    with _conn() as conn:
        conn.execute(
            "UPDATE teacher_comments SET content = ?, updated_at = ? WHERE id = ?",
            (content, now, comment_id)
        )
        conn.commit()
    return {"ok": True, "comment": get_comment(comment_id)}

def review_comment(comment_id: int) -> Dict:
    c = get_comment(comment_id)
    if not c:
        return {"ok": False, "error": "评语不存在"}
    now = time.time()
    with _conn() as conn:
        conn.execute(
            "UPDATE teacher_comments SET status = 'reviewed', reviewed_at = ?, updated_at = ? WHERE id = ?",
            (now, now, comment_id)
        )
        conn.commit()
    return {"ok": True, "comment": get_comment(comment_id)}

def publish_comment(comment_id: int) -> Dict:
    c = get_comment(comment_id)
    if not c:
        return {"ok": False, "error": "评语不存在"}
    if c["status"] != "reviewed":
        return {"ok": False, "error": "只有已审核评语才能发布"}
    now = time.time()
    with _conn() as conn:
        conn.execute(
            "UPDATE teacher_comments SET status = 'published', published_at = ?, updated_at = ? WHERE id = ?",
            (now, now, comment_id)
        )
        conn.commit()
    return {"ok": True, "comment": get_comment(comment_id)}

# ── AI 生成 ──

def generate_comment(student_id: str, teacher_id: str = "", job_role: str = None, class_id: int = None) -> Dict:
    """为单个学生 AI 生成评语草稿。"""
    jr = job_role or DEFAULT_JOB
    now = time.time()
    period_start, period_end = _current_week_range()

    # P6-F: Duplicate check by class_id + student_id + period
    with _conn() as conn:
        existing = conn.execute(
            "SELECT id FROM teacher_comments WHERE class_id=? AND student_id=? AND status='draft' AND period_start=?",
            (int(class_id) if class_id else 0, student_id, period_start)
        ).fetchone()
    if existing:
        return {"ok": False, "error": "本周已有未发布草稿", "comment_id": existing[0]}

    evidence = _collect_student_evidence(student_id, jr)

    llm_configured = False
    try:
        from app.services.llm_client import is_configured
        llm_configured = is_configured()
    except Exception:
        pass

    if llm_configured:
        ai_draft, ai_raw = _ai_generate(student_id, jr, evidence)
    else:
        ai_draft, ai_raw = _template_generate(student_id, jr, evidence), ""

    content = ai_draft

    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO teacher_comments
               (student_id, teacher_id, job_role, class_id, period_start, period_end, content, ai_draft, evidence_json, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
            (student_id, teacher_id, jr, int(class_id) if class_id else 0, period_start, period_end, content, ai_draft, json.dumps(evidence, ensure_ascii=False), now, now)
        )
        conn.commit()
        cid = cur.lastrowid

    return {"ok": True, "comment": get_comment(cid), "llm_used": llm_configured}

def generate_comments_batch(student_ids: List[str], teacher_id: str = "", job_role: str = None, class_id: int = None) -> Dict:
    """批量生成评语草稿。"""
    results = []
    for sid in student_ids:
        r = generate_comment(sid, teacher_id=teacher_id, job_role=job_role, class_id=class_id)
        results.append(r)
    return {"ok": True, "results": results, "total": len(results)}

def review_comments_batch(comment_ids: List[int]) -> Dict:
    """批量审核评语。"""
    results = []
    for cid in comment_ids:
        results.append(review_comment(cid))
    return {"ok": True, "results": results}

def publish_comments_batch(comment_ids: List[int]) -> Dict:
    """批量发布已审核评语（只发布 reviewed 状态，跳过 draft）。"""
    results = []
    for cid in comment_ids:
        c = get_comment(cid)
        if c and c["status"] == "reviewed":
            results.append(publish_comment(cid))
        else:
            results.append({"ok": False, "error": "仅已审核评语可发布", "comment_id": cid})
    return {"ok": True, "results": results}

# ── 学生端 ──

def get_student_published_comments(student_id: str, job_role: str = None) -> Dict:
    """获取学生自己的已发布评语。"""
    sql = "SELECT * FROM teacher_comments WHERE student_id = ? AND status = 'published'"
    params = [student_id]
    if job_role:
        sql += " AND job_role = ?"
        params.append(job_role)
    sql += " ORDER BY published_at DESC LIMIT 20"
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"comments": [_row_to_dict(r) for r in rows], "total": len(rows)}

# ── 证据收集 ──

def _collect_student_evidence(student_id: str, job_role: str) -> List[Dict]:
    """收集学生真实学习证据，不做任何虚构。"""
    evidence = []
    sess_id = f"{job_role}-{student_id}"

    # 测评结果
    try:
        from app.services.teacher_students import get_teacher_student_detail
        detail = get_teacher_student_detail(student_id, job_role)
        if detail.get("completed"):
            evidence.append({
                "source": "assessment", "summary": f"测评得分: {detail.get('overall_score', 0)}",
                "ability_ids": [], "ts": detail.get("completed_at", "")
            })
        for w in (detail.get("weak_abilities") or [])[:3]:
            name = w if isinstance(w, str) else (w.get("name") or w.get("ability_name") or str(w))
            evidence.append({"source": "weak_ability", "summary": f"薄弱: {name}", "ability_ids": [], "ts": ""})
        for s in (detail.get("strong_abilities") or [])[:3]:
            name = s if isinstance(s, str) else (s.get("name") or s.get("ability_name") or str(s))
            evidence.append({"source": "strong_ability", "summary": f"优势: {name}", "ability_ids": [], "ts": ""})
    except Exception:
        pass

    # 近期学习事件
    try:
        from app.services.learning_event_store import get_events
        events = get_events(sess_id, limit=10) or []
        for ev in events[:5]:
            evidence.append({
                "source": "learning_event",
                "summary": ev.get("description") or ev.get("event_type") or str(ev)[:80],
                "ability_ids": [ev.get("ability_id")] if ev.get("ability_id") else [],
                "ts": ev.get("timestamp") or ev.get("created_at") or "",
            })
    except Exception:
        pass

    # 能力状态
    try:
        from app.services.ability_state_engine import compute_ability_state
        state = compute_ability_state(sess_id)
        abilities = (state or {}).get("abilities", {})
        for aid, ab in list(abilities.items())[:5]:
            score = ab.get("cognitive_mastery_score")
            if score is not None:
                evidence.append({
                    "source": "ability_state", "summary": f"{aid}: mastery={score}",
                    "ability_ids": [aid], "ts": ""
                })
    except Exception:
        pass

    return evidence

# ── AI / 模板生成 ──

def _ai_generate(student_id: str, job_role: str, evidence: List[Dict]) -> tuple:
    """调用 LLM 生成评语。"""
    evidence_text = "\n".join([
        f"- [{e.get('source', '')}] {e.get('summary', '')}"
        for e in evidence[:15]
    ]) or "暂无系统学习证据"

    system_prompt = """你是机电岗位培训的 AI 教学助教。请根据学生真实学习证据生成一段简洁的教学评语草稿。
规则：
1. 只能基于提供的 evidence 撰写，不得编造未提及的学习事实。
2. 如果证据很少，应明确说明"目前学习证据有限"。
3. 评语面向学生，语气温和、具体、有建设性。
4. 包含：近期表现、需要提升的问题、下一步建议。
5. 输出纯文本，不超过 200 字。"""

    user_prompt = f"""学生: {student_id}
岗位: {job_role}

学习证据:
{evidence_text}

请为该生生成本周教学评语草稿。"""

    try:
        from app.services.llm_client import chat_completion
        result = chat_completion([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        return result.strip(), result
    except Exception as e:
        logger.warning("LLM comment generation failed: %s", e)
        return _template_generate(student_id, job_role, evidence), ""

def _template_generate(student_id: str, job_role: str, evidence: List[Dict]) -> str:
    """模板兜底生成评语。"""
    weak_items = [e for e in evidence if e.get("source") == "weak_ability"]
    strong_items = [e for e in evidence if e.get("source") == "strong_ability"]

    parts = []
    if strong_items:
        parts.append(f"在{'、'.join([s['summary'].replace('优势: ', '') for s in strong_items[:2]])}方面表现良好。")
    if weak_items:
        parts.append(f"建议继续加强{'、'.join([w['summary'].replace('薄弱: ', '') for w in weak_items[:2]])}。")
    if not parts:
        parts.append("当前系统中的学习证据还比较有限，暂时无法对近期变化做出充分判断。请继续完成实训任务以积累更多学习数据。")
    else:
        parts.append("请继续按计划完成实训任务，巩固已有技能。")

    return " ".join(parts)

def _current_week_range() -> tuple:
    """返回本周日期范围 (YYYY-MM-DD 格式)。"""
    from datetime import datetime, timedelta
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
