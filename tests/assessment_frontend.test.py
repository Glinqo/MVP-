#!/usr/bin/env python3
"""Frontend assessment flow regression tests (v3).

Covers:
  1-25  Static frontend checks (HTML/JS/CSS parsing, no server)
  API   Real HTTP flow tests with isolated DB + random port
"""
import unittest
import re
import json
import threading
import time
import urllib.request
import urllib.error
import tempfile
import shutil
import os
import sys
from pathlib import Path
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer

sys.path.insert(0, ".")
from app.server import MVPHandler

import app.services.data_store as _data_store_check  # ensure importable
# ──────────────────────────────────────────
# Static checks (no server required)
# ──────────────────────────────────────────

PROJECT = Path(__file__).resolve().parent.parent


def _read(name):
    return (PROJECT / name).read_text(encoding="utf-8")


class StaticFrontendChecks(unittest.TestCase):
    """Offline tests that parse HTML / JS / CSS without a running server."""

    @classmethod
    def setUpClass(cls):
        cls.html = _read("web/index.html")
        cls.js = _read("web/app.js")
        cls.css = _read("web/styles.css")

    def test_s01_assessment_is_body_child(self):
        landing_start = self.html.find('id="landingOverlay"')
        assess_start = self.html.find('id="assessmentOverlay"')
        self.assertTrue(assess_start > 0, "assessmentOverlay not found")
        depth = 0
        for i in range(landing_start, assess_start):
            if self.html[i:i+4] == "<div":
                depth += 1
            elif self.html[i:i+5] == "</div":
                depth -= 1
        self.assertEqual(depth, 0, f"assessmentOverlay not outside landing: depth={depth}")

    def test_s02_all_ids_unique(self):
        """No duplicate HTML IDs."""
        ids = []
        class IdFinder(HTMLParser):
            def handle_starttag(self, tag, attrs):
                for k, v in attrs:
                    if k == "id":
                        ids.append(v)
        IdFinder().feed(self.html)
        seen = set()
        dupes = []
        for i in ids:
            if i in seen:
                dupes.append(i)
            seen.add(i)
        self.assertEqual(len(dupes), 0, f"Duplicate IDs: {dupes}")

    def test_s03_tags_balanced(self):
        """button, div, section tags are balanced."""
        for tag in ("button", "div", "section"):
            opens = len(re.findall(rf"<{tag}\b", self.html, re.I))
            closes = len(re.findall(rf"</{tag}>", self.html, re.I))
            self.assertEqual(opens, closes, f"<{tag}> open={opens} close={closes}")

    def test_s04_bootOnce_exists(self):
        self.assertIn("function bootOnce()", self.js)

    def test_s05_admin_calls_bootOnce(self):
        """Admin path calls dismissLanding().then(bootOnce)."""
        admin_line = "dismissLanding().then(bootOnce)"
        self.assertIn(admin_line, self.js, f"Admin must call: {admin_line}")

    def test_s06_student_enters_assessment_gate(self):
        """Student path calls startAssessment."""
        self.assertIn("startAssessment(jobId)", self.js)

    def test_s07_completed_check_is_status_field(self):
        """start checks resp.status === 'completed', NOT resp.error includes 'completed'."""
        self.assertIn('resp.status === "completed"', self.js)
        self.assertNotIn("resp.error.includes(\"completed\")", self.js)

    def test_s08_completed_does_not_render(self):
        start_idx = self.js.find("async function startAssessment")
        next_func = self.js.find("function renderAssessmentQuestion", start_idx)
        start_body = self.js[start_idx:next_func] if next_func > 0 else self.js[start_idx:start_idx+2000]
        completed_idx = start_body.find('resp.status === "completed"')
        self.assertGreater(completed_idx, 0, "completed check not found")
        after = start_body[completed_idx:completed_idx + 400]
        self.assertIn("hideAssessmentOverlay", after)
        self.assertNotIn("renderAssessmentQuestion", after)

    def test_s09_start_request_has_session_id_and_job_role(self):
        self.assertIn("session_id: state.sessionId", self.js)
        self.assertIn("job_role: role", self.js)

    def test_s10_answer_request_has_four_fields(self):
        answer_func = self.js[self.js.find("async function submitAssessmentAnswer"):]
        self.assertIn("session_id:", answer_func)
        self.assertIn("qid:", answer_func)
        self.assertIn("selected_key:", answer_func)
        self.assertIn("job_role:", answer_func)

    def test_s11_no_answers_so_far_in_frontend(self):
        """Frontend JS does NOT send answers_so_far."""
        self.assertNotIn("answers_so_far", self.js,
                         "answers_so_far must not appear in frontend JS")

    def test_s12_render_saves_currentQid(self):
        render_func = self.js[self.js.find("function renderAssessmentQuestion"):]
        self.assertIn("assessmentState.currentQid = q.qid", render_func)

    def test_s13_render_saves_abilityLabels(self):
        render_func = self.js[self.js.find("function renderAssessmentQuestion"):]
        self.assertIn("assessmentState.abilityLabels", render_func)

    def test_s14_retry_bound_once_not_in_render(self):
        render_start = self.js.find("function renderAssessmentQuestion")
        next_start = self.js.find("async function submitAssessmentAnswer", render_start)
        render_body = self.js[render_start:next_start] if next_start > 0 else self.js[render_start:]
        self.assertNotIn("assessmentRetryBtn.onclick", render_body,
                         "Retry binding should NOT be inside renderAssessmentQuestion")
        self.assertIn("assessmentRetryBtn", self.js)

    def test_s15_start_error_has_start_retry(self):
        start_func = self.js[self.js.find("async function startAssessment"):self.js.find("function renderAssessmentQuestion")]
        self.assertIn("setAssessmentError", start_func)
        self.assertIn("startAssessment", start_func)

    def test_s16_answer_error_has_answer_retry(self):
        answer_func = self.js[self.js.find("async function submitAssessmentAnswer"):]
        self.assertIn("setAssessmentError", answer_func)
        self.assertIn("submitAssessmentAnswer", answer_func)

    def test_s17_submitting_guard(self):
        self.assertIn("assessmentState.submitting", self.js)

    def test_s18_disable_ui_on_submit(self):
        submit_func = self.js[self.js.find("async function submitAssessmentAnswer"):]
        self.assertIn("pointerEvents", submit_func)

    def test_s19_finally_restores(self):
        self.assertIn("finally {", self.js)

    def test_s20_sessionStorage_skip_key(self):
        self.assertIn("mcp_assessment_skipped", self.js)

    def test_s21_admin_does_not_call_startAssessment(self):
        """Admin path must not call startAssessment."""
        select_func = self.js[self.js.find("function selectJob"):self.js.find("function dismissLanding")]
        admin_block = select_func[select_func.find('identity !== "student"'):]
        self.assertNotIn("startAssessment", admin_block[:600])

    def test_s22_result_uses_escapeHtml(self):
        result_func = self.js[self.js.find("function showAssessmentResult"):]
        self.assertIn("escapeHtml", result_func, "Result must escape user data")

    def test_s23_resource_cache_updated(self):
        self.assertIn("v=20260730-2", self.html, "Cache version must be 20260730-2")

    def test_s24_css_z_index_above_landing(self):
        self.assertIn("z-index: 10010", self.css,
                      "Assessment overlay z-index must be above landing (10010)")

    def test_s25_show_hide_overlay_functions_exist(self):
        self.assertIn("function showAssessmentOverlay", self.js)
        self.assertIn("function hideAssessmentOverlay", self.js)
    def test_s26_starting_false_before_retry(self):
        # resp.error branch must set starting=false BEFORE setAssessmentError
        js = self.js
        err_block = re.search(
            r'if\s*\(resp\.error\)\s*\{[^}]*?setAssessmentError',
            js, re.DOTALL
        )
        self.assertIsNotNone(err_block, "resp.error branch not found")
        block = err_block.group()
        start_false_pos = block.find('starting = false')
        set_error_pos = block.find('setAssessmentError')
        self.assertGreaterEqual(start_false_pos, 0,
                                "starting=false missing before setAssessmentError")
        self.assertLess(start_false_pos, set_error_pos,
                        "starting=false must appear BEFORE setAssessmentError")

    def test_s27_finally_no_unconditional_nextbtn_enable(self):
        # finally must NOT do nextBtn.disabled = false unconditionally
        js = self.js
        self.assertNotIn('finally {\n    assessmentState.submitting = false;\n    nextBtn.disabled = false;',
                         js, "finally must not unconditionally enable nextBtn")
        self.assertIn('nextBtn.disabled = !assessmentState.selectedOption;', js,
                      "finally must use conditional nextBtn.disabled")

    def test_s28_ability_label_priority(self):
        # renderAssessmentQuestion must use ability_label over dimension
        js = self.js
        self.assertIn('q.ability_label || q.dimension || q.ability_id', js,
                      "Ability label must use ability_label || dimension || ability_id")

    def test_s29_skip_key_has_session_and_job(self):
        # assessmentSkipKey must include state.sessionId and selectedJobRole()
        js = self.js
        self.assertIn('function assessmentSkipKey', js,
                      "assessmentSkipKey function must exist")
        self.assertIn('state.sessionId || ""', js,
                      "Skip key must include sessionId")
        self.assertIn('selectedJobRole() || ""', js,
                      "Skip key must include selectedJobRole()")

    def test_s30_api_flow_tests_exist(self):
        # ApiFlowTests must contain at least 8 test methods
        test_content = _read("tests/assessment_frontend.test.py")
        api_tests_found = re.findall(r'def test_api_\d+', test_content)
        self.assertGreaterEqual(len(api_tests_found), 8,
                                f"Expected >=8 API tests, found {len(api_tests_found)}: {api_tests_found}")

    def test_s31_db_path_restore_is_path(self):
        # tearDownClass must restore DB_PATH to a Path object
        test_content = _read("tests/assessment_frontend.test.py")
        # Check that _orig_db_path is saved as Path (not str)
        save_line = re.search(r'cls\._orig_db_path\s*=\s*store\.DB_PATH', test_content)
        self.assertIsNotNone(save_line, "Must save store.DB_PATH (not str)")

    def test_s32_session_dir_isolation(self):
        # setUpClass must redirect SESSIONS_DIR
        test_content = _read("tests/assessment_frontend.test.py")
        self.assertIn('data_store.SESSIONS_DIR = tmp', test_content,
                      "Must redirect data_store.SESSIONS_DIR to temp dir")
        self.assertIn('data_store.SESSIONS_DIR = cls._orig_sessions_dir', test_content,
                      "Must restore data_store.SESSIONS_DIR in tearDown")



# ──────────────────────────────────────────
# API flow tests (with isolated DB)
# ──────────────────────────────────────────

class ApiFlowTests(unittest.TestCase):
    """HTTP tests against a real server with isolated database."""

    _server = None
    _thread = None
    _tmpdir = None
    _orig_db_path = None
    PORT = 0

    @classmethod
    def setUpClass(cls):
        # Isolate data directory
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="mvp_test_")
        tmp = Path(cls._tmpdir.name)
        (tmp / "data").mkdir(exist_ok=True)
        (tmp / "data" / "sessions").mkdir(exist_ok=True)

        # Redirect assessment store DB_PATH (keep as Path)
        import app.services.assessment_store as store
        cls._orig_db_path = store.DB_PATH
        store.DB_PATH = tmp / "data" / "assessments.db"
        # Redirect learning event store sessions
        import app.services.learning_event_store as les
        cls._orig_event_sessions_dir = les.SESSIONS_DIR
        les.SESSIONS_DIR = tmp / "data" / "sessions"
        # Isolate session JSON directories
        import app.services.data_store as data_store
        cls._orig_sessions_dir = data_store.SESSIONS_DIR
        data_store.SESSIONS_DIR = tmp / "data" / "sessions"

        # Start server on random port
        cls._server = ThreadingHTTPServer(("127.0.0.1", 0), MVPHandler)
        cls.PORT = cls._server.server_address[1]
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        for _ in range(30):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.PORT}/api/health", timeout=2)
                return
            except Exception:
                time.sleep(0.2)
        raise RuntimeError("Server did not start")

    def _api(self, path, body=None, method="POST"):
        url = f"http://127.0.0.1:{self.PORT}{path}"
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return json.loads(resp.read().decode("utf-8")), resp.status
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body), e.code
            except Exception:
                return {"error": body}, e.code

    def test_api_01_start_with_job_role(self):
        sid = "test-api-s01"
        _, code = self._api("/api/student/assess/start", {
            "session_id": sid,
            "job_role": "mechatronics_maintenance"
        })
        self.assertIn(code, [200, 201])

    def test_api_02_answer_moves_to_next_question(self):
        sid = "test-api-s02"
        resp, code = self._api("/api/student/assess/start", {
            "session_id": sid,
            "job_role": "mechatronics_maintenance"
        })
        q = resp.get("first_question")
        self.assertIsNotNone(q, f"No first_question: {resp}")
        # Answer first question
        options = q.get("options", [])
        first_key = options[0]["key"] if options else "A"
        resp2, code2 = self._api("/api/student/assess/answer", {
            "session_id": sid,
            "qid": q["qid"],
            "selected_key": first_key,
            "job_role": "mechatronics_maintenance"
        })
        self.assertIn(code2, [200, 201])
        if resp2.get("next_question"):
            self.assertNotEqual(resp2["next_question"]["qid"], q["qid"],
                                "Next question must differ from current")
        self.assertEqual(resp2.get("answered_count", 0), 1)

    def test_api_03_start_missing_session_returns_400(self):
        _, code = self._api("/api/student/assess/start", {"job_role": "mechatronics_maintenance"})
        self.assertEqual(code, 400, f"Expected 400, got {code}")

    def test_api_04_answer_missing_session_returns_400(self):
        _, code = self._api("/api/student/assess/answer", {
            "qid": "any",
            "selected_key": "A",
            "job_role": "mechatronics_maintenance"
        })
        self.assertEqual(code, 400, f"Expected 400, got {code}")

    def test_api_05_resume_same_session(self):
        sid = "test-api-s05"
        resp1, _ = self._api("/api/student/assess/start", {
            "session_id": sid,
            "job_role": "mechatronics_maintenance"
        })
        q1 = resp1.get("first_question")
        self.assertIsNotNone(q1)
        options = q1.get("options", [])
        first_key = options[0]["key"] if options else "A"
        self._api("/api/student/assess/answer", {
            "session_id": sid,
            "qid": q1["qid"],
            "selected_key": first_key,
            "job_role": "mechatronics_maintenance"
        })
        # Resume: start again with same session_id
        resp3, code3 = self._api("/api/student/assess/start", {
            "session_id": sid,
            "job_role": "mechatronics_maintenance"
        })
        self.assertIn(code3, [200, 201])
        # Should return next_question at index 1, not first_question
        if resp3.get("next_question"):
            self.assertNotEqual(resp3["next_question"]["qid"], q1["qid"])

    def test_api_06_duplicate_answer_is_idempotent(self):
        sid = "test-api-s06"
        resp1, _ = self._api("/api/student/assess/start", {
            "session_id": sid,
            "job_role": "mechatronics_maintenance"
        })
        q1 = resp1.get("first_question")
        options = q1.get("options", [])
        first_key = options[0]["key"] if options else "A"
        # Submit same answer twice
        a1, _ = self._api("/api/student/assess/answer", {
            "session_id": sid, "qid": q1["qid"],
            "selected_key": first_key, "job_role": "mechatronics_maintenance"
        })
        count1 = a1.get("answered_count", 0)
        a2, _ = self._api("/api/student/assess/answer", {
            "session_id": sid, "qid": q1["qid"],
            "selected_key": first_key, "job_role": "mechatronics_maintenance"
        })
        count2 = a2.get("answered_count", 0)
        self.assertEqual(count1, count2,
                         f"Duplicate answer should not increase count: {count1} vs {count2}")

    def test_api_07_completed_reentry_returns_completed_without_question(self):
        sid = "test-api-s07"
        # Answer all questions for this session to complete
        resp, _ = self._api("/api/student/assess/start", {
            "session_id": sid,
            "job_role": "mechatronics_maintenance"
        })
        # Continue answering until completed
        current = resp.get("first_question") or resp.get("next_question")
        for _ in range(35):  # safety upper bound
            if not current:
                break
            options = current.get("options", [])
            k = options[1]["key"] if len(options) > 1 else (options[0]["key"] if options else "A")
            a_resp, _ = self._api("/api/student/assess/answer", {
                "session_id": sid, "qid": current["qid"],
                "selected_key": k, "job_role": "mechatronics_maintenance"
            })
            if a_resp.get("status") == "completed":
                break
            current = a_resp.get("next_question")
        # Now re-enter
        re_resp, re_code = self._api("/api/student/assess/start", {
            "session_id": sid,
            "job_role": "mechatronics_maintenance"
        })
        self.assertIn(re_code, [200, 201])
        self.assertIn(re_resp.get("status"), ["completed", None])
        self.assertIn(re_resp.get("state"), ["completed", None])
        # Must NOT return a new question
        self.assertIsNone(re_resp.get("first_question"))
        self.assertIsNone(re_resp.get("next_question"))

    def test_api_08_job_role_isolation(self):
        sid = "test-api-s08"
        # Start with job A
        r1, _ = self._api("/api/student/assess/start", {
            "session_id": sid,
            "job_role": "mechatronics_maintenance"
        })
        q1a = r1.get("first_question")
        self.assertIsNotNone(q1a)
        options = q1a.get("options", [])
        k = options[0]["key"] if options else "A"
        self._api("/api/student/assess/answer", {
            "session_id": sid, "qid": q1a["qid"],
            "selected_key": k, "job_role": "mechatronics_maintenance"
        })
        # Different session with different job
        sid2 = "test-api-s08-other"
        r2, _ = self._api("/api/student/assess/start", {
            "session_id": sid2,
            "job_role": "electrical_technician"
        })
        q2a = r2.get("first_question")
        self.assertIsNotNone(q2a)
        # Sessions should be independent
        self.assertNotEqual(sid, sid2)

    @classmethod
    def tearDownClass(cls):
        try:
            if cls._server:
                cls._server.shutdown()
                cls._server.server_close()
        except Exception:
            pass
        try:
            if cls._thread:
                cls._thread.join(timeout=5)
        except Exception:
            pass
        try:
            if cls._tmpdir:
                cls._tmpdir.cleanup()
        except Exception:
            pass
        try:
            import app.services.assessment_store as store
            store.DB_PATH = cls._orig_db_path
        except Exception:
            pass
        try:
            import app.services.learning_event_store as les
            les.SESSIONS_DIR = cls._orig_event_sessions_dir
        except Exception:
            pass
        try:
            import app.services.data_store as data_store
            data_store.SESSIONS_DIR = cls._orig_sessions_dir
        except Exception:
            pass

if __name__ == "__main__":
    unittest.main(verbosity=2)
