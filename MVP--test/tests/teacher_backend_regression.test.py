import json
import os
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PORT = 8771
BASE_URL = f"http://127.0.0.1:{PORT}"
PYTHON = sys.executable
JOB_ROLE = "automation_line_commissioning_maintenance_newcomer"


def request_json(path, payload=None, token=None, method=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers=headers,
        method=method or ("POST" if payload is not None else "GET"),
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            pass
        return exc.code, body


def wait_for_server(process):
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError("server exited early")
        try:
            status, body = request_json("/api/health")
            if status == 200 and body.get("status") == "ok":
                return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.1)
    raise TimeoutError("server did not become ready")


class TeacherBackendRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = os.environ.copy()
        env.pop("LLM_API_KEY", None)
        env.pop("LLM_BASE_URL", None)
        env.pop("LLM_MODEL", None)
        cls.process = subprocess.Popen(
            [PYTHON, "-m", "app.server", "--port", str(PORT)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_for_server(cls.process)
        status, body = request_json("/api/auth/login", {"username": "000", "password": "123456"})
        assert status == 200 and body.get("token"), body
        cls.teacher_token = body["token"]

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        try:
            cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.process.kill()

    def create_class(self, name, job_role=JOB_ROLE, students=None):
        status, body = request_json(
            "/api/teacher/classes",
            {"name": name, "job_role": job_role},
            token=self.teacher_token,
        )
        self.assertEqual(status, 200, body)
        class_id = body["class"]["id"]
        if students:
            status, body = request_json(
                f"/api/teacher/classes/{class_id}/students",
                {"student_usernames": students},
                token=self.teacher_token,
            )
            self.assertEqual(status, 200, body)
        return class_id

    def test_public_quiz_does_not_expose_answers(self):
        status, body = request_json(f"/api/quiz?job_role={JOB_ROLE}")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["questions"])
        forbidden = {"correct_answer", "explanation", "wrong_feedback"}
        self.assertFalse(forbidden & set(body["questions"][0]))

    def test_get_auth_me_restores_server_role(self):
        status, body = request_json("/api/auth/me", token=self.teacher_token)
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertEqual(body["user"]["role"], "teacher")

    def test_teacher_comment_lifecycle_is_authed_and_class_scoped(self):
        stamp = str(int(time.time() * 1000))
        class_id = self.create_class("TBR-comments-" + stamp, students=["001"])

        status, body = request_json(
            "/api/teacher/comments/generate",
            {"student_id": "001", "class_id": class_id, "job_role": JOB_ROLE},
            token=self.teacher_token,
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"], body)
        comment_id = body["comment"]["id"]

        status, _ = request_json(f"/api/teacher/comments/{comment_id}")
        self.assertEqual(status, 401)

        status, detail = request_json(f"/api/teacher/comments/{comment_id}", token=self.teacher_token)
        self.assertEqual(status, 200, detail)
        self.assertEqual(detail["id"], comment_id)

        status, reviewed = request_json(
            f"/api/teacher/comments/{comment_id}/review",
            {},
            token=self.teacher_token,
        )
        self.assertEqual(status, 200, reviewed)
        self.assertEqual(reviewed["comment"]["status"], "reviewed")

        status, published = request_json(
            f"/api/teacher/comments/{comment_id}/publish",
            {},
            token=self.teacher_token,
        )
        self.assertEqual(status, 200, published)
        self.assertEqual(published["comment"]["status"], "published")

        status, body = request_json(
            "/api/teacher/comments/generate",
            {"student_id": "002", "class_id": class_id, "job_role": JOB_ROLE},
            token=self.teacher_token,
        )
        self.assertEqual(status, 403, body)

    def test_teacher_issues_candidates_and_class_insights_use_class_scope(self):
        from app.services.assessment_store import save_state
        from app.services.feedback import append_session_event

        stamp = str(int(time.time() * 1000))
        job_role = "tbr_" + stamp
        class_id = self.create_class("TBR-issues-" + stamp, job_role=job_role, students=["001", "002"])

        for username in ("001", "002"):
            session_id = f"{job_role}-{username}"
            for _ in range(3):
                append_session_event(
                    session_id,
                    {
                        "event_type": "initial_quiz_answered",
                        "ability_id": "sn_type_identify",
                        "is_correct": False,
                    },
                )
            save_state(
                {
                    "session_id": session_id,
                    "job_role": job_role,
                    "assessment_id": "TBR-" + session_id,
                    "assessment_version": "1.0.0",
                    "state": "completed",
                    "answers": [],
                    "result": {
                        "total_score": 0,
                        "weak_abilities": ["sn_type_identify"],
                        "strong_abilities": [],
                    },
                    "completed_at": time.time(),
                }
            )

        status, issues_body = request_json(
            "/api/v2/teacher/issues",
            {"class_id": class_id, "job_role": job_role},
            token=self.teacher_token,
        )
        self.assertEqual(status, 200, issues_body)
        issues = issues_body["issues"]
        self.assertTrue(issues, issues_body)
        issue = issues[0]
        self.assertIn("001", issue["affected_students"])
        self.assertIn("002", issue["affected_students"])

        status, candidates_body = request_json(
            "/api/v2/teacher/issues/candidates",
            {
                "class_id": class_id,
                "job_role": job_role,
                "issue_id": issue["issue_id"],
                "student_ids": ["001", "999"],
            },
            token=self.teacher_token,
        )
        self.assertEqual(status, 200, candidates_body)
        candidates = candidates_body["candidates"]
        self.assertTrue(candidates, candidates_body)
        self.assertEqual(candidates[0]["target_students"], ["001"])

        status, overview = request_json(
            f"/api/teacher/class/overview?class_id={class_id}&job_role={job_role}",
            token=self.teacher_token,
        )
        self.assertEqual(status, 200, overview)
        self.assertTrue(overview["weakest_abilities"], overview)
        self.assertEqual(overview["weakest_abilities"][0]["ability_id"], "sn_type_identify")

    def test_job_graph_proposal_generation_requires_teacher(self):
        status, _ = request_json(
            "/api/graph/job/proposals",
            {"material": "sensor wiring and PLC input diagnosis", "source_type": "teacher_curated"},
        )
        self.assertEqual(status, 401)

        status, body = request_json(
            "/api/graph/job/proposals",
            {"material": "sensor wiring and PLC input diagnosis", "source_type": "teacher_curated"},
            token=self.teacher_token,
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body.get("proposals"))


if __name__ == "__main__":
    unittest.main()
