"""班级与学生管理闭环集成测试。

覆盖：班级 CRUD、成员增删、权限隔离、班级作用域一致性。
"""
import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services.class_management import (
    add_students,
    create_class,
    get_available_students,
    get_class,
    get_class_students,
    list_classes,
    remove_students,
    update_class,
)


class ClassManagementTest(unittest.TestCase):
    def setUp(self):
        self.teacher_id = 1
        self.teacher_id2 = 2
        self.stamp = str(int(time.time()))
        self.class_name = "TF6D_" + self.stamp

    def test_full_class_lifecycle(self):
        # 创建班级
        result = create_class(self.teacher_id, self.class_name, "test_role", "test_term")
        self.assertTrue(result.get("ok"), result)
        class_id = result["class"]["id"]

        # 查询班级
        cls = get_class(class_id, self.teacher_id)
        self.assertIsNotNone(cls)
        self.assertEqual(cls["name"], self.class_name)
        self.assertEqual(cls["student_count"], 0)

        # 添加学生
        add_result = add_students(class_id, self.teacher_id, ["001", "002", "003"])
        self.assertTrue(add_result.get("ok"), add_result)
        self.assertEqual(sorted(add_result["added"]), ["001", "002", "003"])
        self.assertEqual(add_result["student_count"], 3)

        # 重复加入
        dup_result = add_students(class_id, self.teacher_id, ["002"])
        self.assertEqual(dup_result["added"], [])
        self.assertEqual(dup_result["already_in_class"], ["002"])

        # 不存在的学生
        missing_result = add_students(class_id, self.teacher_id, ["9999"])
        self.assertEqual(missing_result["not_found"], ["9999"])

        # 查询成员
        cls_with_students = get_class_students(class_id, self.teacher_id)
        usernames = [s["username"] for s in cls_with_students["students"]]
        self.assertEqual(sorted(usernames), ["001", "002", "003"])

        # 移除
        remove_result = remove_students(class_id, self.teacher_id, ["002"])
        self.assertEqual(remove_result["removed"], ["002"])
        self.assertEqual(remove_result["student_count"], 2)

    def test_teacher_ownership_isolation(self):
        result = create_class(self.teacher_id, self.class_name, "test_role", "test_term")
        class_id = result["class"]["id"]

        # 另一个教师不能访问
        self.assertIsNone(get_class(class_id, self.teacher_id2))
        self.assertIsNone(get_class_students(class_id, self.teacher_id2))

        # 也不能修改或添加学生
        update_result = update_class(class_id, self.teacher_id2, name="hack")
        self.assertFalse(update_result.get("ok"))

        add_result = add_students(class_id, self.teacher_id2, ["004"])
        self.assertFalse(add_result.get("ok"))

    def test_list_classes_only_own(self):
        create_class(self.teacher_id, self.class_name, "test_role", "test_term")
        classes = list_classes(self.teacher_id)
        ids = [c["id"] for c in classes]
        self.assertTrue(any(c["name"] == self.class_name for c in classes))

        # 教师 2 没有班级
        classes2 = list_classes(self.teacher_id2)
        self.assertFalse(any(c["name"] == self.class_name for c in classes2))

    def test_available_students_filter(self):
        result = create_class(self.teacher_id, self.class_name, "test_role", "test_term")
        class_id = result["class"]["id"]
        add_students(class_id, self.teacher_id, ["001"])

        avail = get_available_students(class_id, self.teacher_id, search="001")
        self.assertTrue(avail.get("ok"), avail)
        student = [s for s in avail["students"] if s["username"] == "001"][0]
        self.assertTrue(student["in_current_class"])

        avail2 = get_available_students(class_id, self.teacher_id, search="002")
        student2 = [s for s in avail2["students"] if s["username"] == "002"][0]
        self.assertFalse(student2["in_current_class"])




class P6CrossClassIsolationTest(unittest.TestCase):
    """P6: 跨班隔离、学生上下文、评语 scope。"""

    def setUp(self):
        self.teacher_a = 1
        self.teacher_b = 2
        self.stamp = str(int(time.time()))
        self.class_a = create_class(self.teacher_a, "A_" + self.stamp, "role_a", "")["class"]["id"]
        self.class_b = create_class(self.teacher_b, "B_" + self.stamp, "role_b", "")["class"]["id"]
        add_students(self.class_a, self.teacher_a, ["001", "002", "003"])
        add_students(self.class_b, self.teacher_b, ["004", "005", "006"])

    def test_cross_teacher_roster_403(self):
        # Teacher B cannot access Class A
        result = get_class_students(self.class_a, self.teacher_b)
        self.assertIsNone(result)
        # Teacher A cannot access Class B
        result2 = get_class_students(self.class_b, self.teacher_a)
        self.assertIsNone(result2)

    def test_cross_class_data_isolation(self):
        cls_a = get_class_students(self.class_a, self.teacher_a)
        usernames_a = {s["username"] for s in cls_a["students"]}
        self.assertEqual(usernames_a, {"001", "002", "003"})
        self.assertFalse({"004", "005", "006"} & usernames_a)

    def test_student_active_classes(self):
        from app.services.class_management import get_student_active_classes
        # Student 001 in Class A
        classes = get_student_active_classes(1)  # 001 maps to id=1? Need to resolve
        # Resolve actual student id for username "001"
        from app.services.auth import _conn as auth_conn
        with auth_conn() as conn:
            row = conn.execute("SELECT id FROM users WHERE username='001'").fetchone()
        sid = row["id"]
        classes = get_student_active_classes(sid)
        class_ids = {c["id"] for c in classes}
        self.assertIn(self.class_a, class_ids)

    def test_learning_context_resolver(self):
        from app.services.class_management import resolve_learning_context
        from app.services.auth import _conn as auth_conn
        with auth_conn() as conn:
            row = conn.execute("SELECT id, username, job_role FROM users WHERE username='001'").fetchone()
        user = {"id": row["id"], "username": row["username"], "role": "student", "job_role": row["job_role"] or ""}
        # With explicit class_id, should resolve to class scope
        result = resolve_learning_context(user, class_id=self.class_a)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "class")
        self.assertEqual(result["class_id"], self.class_a)

    def test_learning_context_with_explicit_class(self):
        from app.services.class_management import resolve_learning_context
        from app.services.auth import _conn as auth_conn
        with auth_conn() as conn:
            row = conn.execute("SELECT id, username, job_role FROM users WHERE username='001'").fetchone()
        user = {"id": row["id"], "username": row["username"], "role": "student", "job_role": row["job_role"] or ""}
        # Explicit wrong class -> NOT_IN_CLASS
        result = resolve_learning_context(user, class_id=self.class_b)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("code"), "NOT_IN_CLASS")

    def test_archive_lifecycle(self):
        from app.services.class_management import archive_class, restore_class
        # Archive
        r1 = archive_class(self.class_a, self.teacher_a)
        self.assertTrue(r1["ok"])
        self.assertEqual(r1["status"], "archived")
        # Archived class not in active list
        active = list_classes(self.teacher_a)
        self.assertFalse(any(c["id"] == self.class_a for c in active))
        # Restore
        r2 = restore_class(self.class_a, self.teacher_a)
        self.assertTrue(r2["ok"])
        active2 = list_classes(self.teacher_a)
        self.assertTrue(any(c["id"] == self.class_a for c in active2))



class P7TeacherAIIsolationTest(unittest.TestCase):
    """P7: Teacher AI class-scoped isolation."""

    def setUp(self):
        self.teacher_a = 1
        self.stamp = str(int(time.time()))
        self.class_a = create_class(self.teacher_a, "A7_" + self.stamp, "role_a", "")["class"]["id"]
        add_students(self.class_a, self.teacher_a, ["001", "002", "003"])

    def test_ai_student_state_class_scoped(self):
        from app.services.teacher_ai_v2 import TeacherAIV2
        ai = TeacherAIV2()
        # Student 001 in class
        r1 = ai.get_student_state("001", class_id=self.class_a, teacher_id=self.teacher_a)
        self.assertNotIn("not_in_class", r1.get("status", ""))
        # Student 999 not in class
        r2 = ai.get_student_state("999", class_id=self.class_a, teacher_id=self.teacher_a)
        self.assertEqual(r2.get("status"), "not_in_class")

    def test_ai_candidates_class_filtered(self):
        from app.services.teacher_ai_v2 import TeacherAIV2
        ai = TeacherAIV2()
        # Only 001 in class, 999 outside
        result = ai.generate_intervention_candidates(
            "ISSUE_TEST", ["001", "999"], class_id=self.class_a, teacher_id=self.teacher_a
        )
        # Should only process 001, no error
        self.assertIsInstance(result, list)

if __name__ == "__main__":
    unittest.main()
