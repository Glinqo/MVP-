"""教师班级与学生成员管理。

职责：
  - 班级（Class）：一个教师可创建多个班级，一个班级一个目标岗位。
  - 班级成员（ClassMember）：一个学生可属于多个班级，与个人 job_role 无关。

存储复用 data/users.db，避免为两个表新增数据库。
"""

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "users.db"


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute("PRAGMA journal_mode=WAL")
    c.row_factory = sqlite3.Row
    return c


def _ensure_tables():
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                teacher_id INTEGER NOT NULL,
                job_role TEXT NOT NULL DEFAULT '',
                term TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS class_members (
                class_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                joined_at REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                PRIMARY KEY (class_id, student_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_class_members_student ON class_members(student_id)"
        )
        conn.commit()


_ensure_tables()


def require_teacher_class(user: Dict[str, Any], class_id: Any) -> Dict[str, Any]:
    """验证 class_id 属于当前教师。

    返回 (ok, class_dict, error_status, error_message)：
      - ok=True: class_dict 为该班级详情
      - ok=False: error_status 和 error_message 可用于 API 响应
    """
    if not user:
        return {"ok": False, "status": 401, "error": "请先登录"}
    if user.get("role", "") != "teacher":
        return {"ok": False, "status": 403, "error": "需要教师权限"}
    if class_id is None or class_id == "":
        return {"ok": False, "status": 400, "error": "class_id is required"}
    try:
        cid = int(class_id)
    except (TypeError, ValueError):
        return {"ok": False, "status": 400, "error": "非法的 class_id"}
    cls = get_class(cid, user["id"])
    if cls is None:
        # 区分不存在与无权限
        with _conn() as conn:
            exists = conn.execute("SELECT id FROM classes WHERE id = ?", (cid,)).fetchone()
        if exists:
            return {"ok": False, "status": 403, "error": "无权访问该班级"}
        return {"ok": False, "status": 404, "error": "班级不存在"}
    return {"ok": True, "class": cls}


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _class_row_to_dict(row: sqlite3.Row, student_count: int = 0) -> Dict[str, Any]:
    d = dict(row)
    d["student_count"] = student_count
    return d


def _get_class(class_id: int, teacher_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM classes WHERE id = ? AND teacher_id = ?",
            (class_id, teacher_id),
        ).fetchone()
        if not row:
            return None
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM class_members WHERE class_id = ?",
            (class_id,),
        ).fetchone()["c"]
        return _class_row_to_dict(row, count)


def _resolve_student_ids(conn: sqlite3.Connection, usernames: List[str]) -> Dict[str, int]:
    """将 username 列表映射为 id。不存在的 username 不会出现在结果里。"""
    mapping = {}
    if not usernames:
        return mapping
    placeholders = ",".join("?" for _ in usernames)
    rows = conn.execute(
        f"SELECT id, username FROM users WHERE username IN ({placeholders})",
        usernames,
    ).fetchall()
    return {r["username"]: r["id"] for r in rows}


def _resolve_student_ids_to_username(conn: sqlite3.Connection, ids: List[int]) -> Dict[int, str]:
    mapping = {}
    if not ids:
        return mapping
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, username FROM users WHERE id IN ({placeholders})",
        ids,
    ).fetchall()
    return {r["id"]: r["username"] for r in rows}


# ---------------------------------------------------------------------------
# 班级 CRUD
# ---------------------------------------------------------------------------

def create_class(
    teacher_id: int,
    name: str,
    job_role: str = "",
    term: str = "",
) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "班级名称不能为空", "code": "INVALID_INPUT"}

    now = time.time()
    with _conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO classes (name, teacher_id, job_role, term, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
            """,
            (name, teacher_id, job_role or "", term or "", now, now),
        )
        conn.commit()
        class_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
    return {
        "ok": True,
        "class": _class_row_to_dict(row, 0),
    }


def list_classes(teacher_id: int) -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM classes WHERE teacher_id = ? AND status = 'active' ORDER BY updated_at DESC",
            (teacher_id,),
        ).fetchall()
        result = []
        for row in rows:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM class_members WHERE class_id = ?",
                (row["id"],),
            ).fetchone()["c"]
            result.append(_class_row_to_dict(row, count))
        return result


def get_class(class_id: int, teacher_id: int) -> Optional[Dict[str, Any]]:
    return _get_class(class_id, teacher_id)


def update_class(
    class_id: int,
    teacher_id: int,
    name: str = None,
    job_role: str = None,
    term: str = None,
    status: str = None,
) -> Dict[str, Any]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM classes WHERE id = ? AND teacher_id = ?",
            (class_id, teacher_id),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "班级不存在", "code": "NOT_FOUND"}

        updates = {}
        if name is not None:
            name = (name or "").strip()
            if not name:
                return {"ok": False, "error": "班级名称不能为空", "code": "INVALID_INPUT"}
            updates["name"] = name
        if job_role is not None:
            updates["job_role"] = job_role or ""
        if term is not None:
            updates["term"] = term or ""
        if status is not None:
            if status not in ("active", "archived"):
                return {"ok": False, "error": "非法的班级状态", "code": "INVALID_INPUT"}
            updates["status"] = status

        if updates:
            updates["updated_at"] = time.time()
            set_parts = ", ".join(f"{k} = ?" for k in updates)
            params = list(updates.values()) + [class_id]
            conn.execute(
                f"UPDATE classes SET {set_parts} WHERE id = ?",
                params,
            )
            conn.commit()

        return {"ok": True, "class": _get_class(class_id, teacher_id)}


# ---------------------------------------------------------------------------
# 班级成员
# ---------------------------------------------------------------------------

def get_class_students(class_id: int, teacher_id: int) -> Optional[Dict[str, Any]]:
    cls = _get_class(class_id, teacher_id)
    if cls is None:
        return None
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT u.username, u.nickname, u.role, u.job_role,
                   cm.joined_at, cm.source
            FROM class_members cm
            JOIN users u ON u.id = cm.student_id
            WHERE cm.class_id = ?
            ORDER BY cm.joined_at ASC
            """,
            (class_id,),
        ).fetchall()
    cls["students"] = [dict(r) for r in rows]
    return cls


def add_students(
    class_id: int,
    teacher_id: int,
    student_usernames: List[str],
) -> Dict[str, Any]:
    cls = _get_class(class_id, teacher_id)
    if cls is None:
        return {"ok": False, "error": "班级不存在", "code": "NOT_FOUND"}

    usernames = [u.strip() for u in (student_usernames or []) if str(u).strip()]
    # 去重并保持顺序
    seen = set()
    unique_usernames = []
    for u in usernames:
        if u not in seen:
            seen.add(u)
            unique_usernames.append(u)

    with _conn() as conn:
        id_map = _resolve_student_ids(conn, unique_usernames)
        existing_rows = conn.execute(
            "SELECT student_id FROM class_members WHERE class_id = ?",
            (class_id,),
        ).fetchall()
        existing_ids = {r["student_id"] for r in existing_rows}
        id_to_username = _resolve_student_ids_to_username(conn, list(existing_ids))

        added = []
        already = []
        not_found = []
        now = time.time()
        for username in unique_usernames:
            if username not in id_map:
                not_found.append(username)
                continue
            sid = id_map[username]
            if sid in existing_ids:
                already.append(username)
                continue
            conn.execute(
                "INSERT INTO class_members (class_id, student_id, joined_at, source) VALUES (?, ?, ?, 'manual')",
                (class_id, sid, now),
            )
            added.append(username)

        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM class_members WHERE class_id = ?",
            (class_id,),
        ).fetchone()["c"]

    return {
        "ok": True,
        "added": added,
        "already_in_class": already,
        "not_found": not_found,
        "student_count": count,
    }


def remove_students(
    class_id: int,
    teacher_id: int,
    student_usernames: List[str],
) -> Dict[str, Any]:
    cls = _get_class(class_id, teacher_id)
    if cls is None:
        return {"ok": False, "error": "班级不存在", "code": "NOT_FOUND"}

    usernames = [u.strip() for u in (student_usernames or []) if str(u).strip()]
    with _conn() as conn:
        id_map = _resolve_student_ids(conn, usernames)
        removed = []
        for username in usernames:
            if username in id_map:
                sid = id_map[username]
                cursor = conn.execute(
                    "DELETE FROM class_members WHERE class_id = ? AND student_id = ?",
                    (class_id, sid),
                )
                if cursor.rowcount:
                    removed.append(username)
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM class_members WHERE class_id = ?",
            (class_id,),
        ).fetchone()["c"]

    return {"ok": True, "removed": removed, "student_count": count}


def get_available_students(
    class_id: int,
    teacher_id: int,
    search: str = "",
) -> Dict[str, Any]:
    """获取可加入班级的学生列表，包括已在本班和未在本班。"""
    cls = _get_class(class_id, teacher_id)
    if cls is None:
        return {"ok": False, "error": "班级不存在", "code": "NOT_FOUND"}

    search = (search or "").strip()
    query = "SELECT id, username, nickname, role, job_role FROM users WHERE role = 'student'"
    params: List[Any] = []
    if search:
        query += " AND (username LIKE ? OR nickname LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like])
    query += " ORDER BY username ASC"

    with _conn() as conn:
        students = [dict(r) for r in conn.execute(query, params).fetchall()]
        member_rows = conn.execute(
            "SELECT student_id FROM class_members WHERE class_id = ?",
            (class_id,),
        ).fetchall()
        in_current = {r["student_id"] for r in member_rows}

        # 查询所有学生所属班级
        all_members = conn.execute(
            """
            SELECT cm.student_id, c.id AS class_id, c.name AS class_name
            FROM class_members cm
            JOIN classes c ON c.id = cm.class_id
            """
        ).fetchall()
        classes_by_student: Dict[int, List[Dict[str, Any]]] = {}
        for m in all_members:
            classes_by_student.setdefault(m["student_id"], []).append(
                {"class_id": m["class_id"], "name": m["class_name"]}
            )

        result = []
        for s in students:
            sid = s["id"]
            result.append(
                {
                    "username": s["username"],
                    "nickname": s["nickname"],
                    "in_current_class": sid in in_current,
                    "classes": classes_by_student.get(sid, []),
                    "job_role": s["job_role"] or "",
                }
            )
        return {"ok": True, "students": result}


def get_student_classes(student_id: int) -> List[Dict[str, Any]]:
    """查询学生所属班级，用于其它服务按班级作用域解析。"""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT c.*, cm.joined_at
            FROM class_members cm
            JOIN classes c ON c.id = cm.class_id
            WHERE cm.student_id = ?
            ORDER BY cm.joined_at ASC
            """,
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_student_active_classes(student_id: int) -> List[Dict[str, Any]]:
    """查询学生所属的 active classes，包含教师名称。"""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.job_role, c.term, c.status,
                   u.nickname AS teacher_name, cm.joined_at
            FROM class_members cm
            JOIN classes c ON c.id = cm.class_id
            LEFT JOIN users u ON u.id = c.teacher_id
            WHERE cm.student_id = ? AND c.status = 'active'
            ORDER BY cm.joined_at ASC
            """,
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def resolve_learning_context(
    user: Dict[str, Any],
    class_id: Any = None,
) -> Dict[str, Any]:
    """解析学生学习上下文，决定 effective_job_role。

    规则：
      - 如果提供了 class_id 且该学生属于该班：source=class, job_role=class.job_role
      - 如果学生只属于一个 active class：自动进入该班
      - 否则：source=personal, job_role=user.job_role
    """
    if not user:
        return {"ok": False, "error": "not authenticated", "code": "UNAUTHENTICATED"}

    student_id = user.get("id")
    if not student_id:
        return {"ok": False, "error": "missing user id", "code": "INVALID_USER"}

    active_classes = get_student_active_classes(student_id)

    selected_class = None
    if class_id:
        try:
            cid = int(class_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid class_id", "code": "INVALID_CLASS_ID"}
        for cls in active_classes:
            if cls["id"] == cid:
                selected_class = cls
                break
        if not selected_class:
            return {"ok": False, "error": "student not in this class", "code": "NOT_IN_CLASS"}
    elif len(active_classes) == 1:
        selected_class = active_classes[0]

    if selected_class:
        return {
            "ok": True,
            "student_id": student_id,
            "class_id": selected_class["id"],
            "job_role": selected_class.get("job_role", ""),
            "source": "class",
            "class": selected_class,
            "available_classes": active_classes,
        }

    return {
        "ok": True,
        "student_id": student_id,
        "class_id": None,
        "job_role": user.get("job_role", ""),
        "source": "personal",
        "class": None,
        "available_classes": active_classes,
    }


def archive_class(class_id: int, teacher_id: int) -> Dict[str, Any]:
    """归档班级，不做硬删除。历史数据保留。"""
    cls = get_class(class_id, teacher_id)
    if cls is None:
        return {"ok": False, "error": "班级不存在", "code": "NOT_FOUND"}
    with _conn() as conn:
        conn.execute(
            "UPDATE classes SET status = 'archived', updated_at = ? WHERE id = ?",
            (time.time(), class_id),
        )
        conn.commit()
    return {"ok": True, "class_id": class_id, "status": "archived"}


def restore_class(class_id: int, teacher_id: int) -> Dict[str, Any]:
    """恢复已归档班级。"""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM classes WHERE id = ? AND teacher_id = ? AND status = 'archived'",
            (class_id, teacher_id),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "归档班级不存在", "code": "NOT_FOUND"}
        conn.execute(
            "UPDATE classes SET status = 'active', updated_at = ? WHERE id = ?",
            (time.time(), class_id),
        )
        conn.commit()
    return {"ok": True, "class_id": class_id, "status": "active"}
