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

        # Redirect assessment store DB_PATH
        import app.services.assessment_store as store
        cls._orig_db_path = str(store.DB_PATH) if hasattr(store, "DB_PATH") else None
        store.DB_PATH = tmp / "data" / "assessments.db"
        # Also redirect learning event store
        import app.services.learning_event_store as les
        if hasattr(les, "EVENTS_DB_PATH"):
            les.EVENTS_DB_PATH = tmp / "data" / "learning_events.db"

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
            if cls._orig_db_path:
                store.DB_PATH = cls._orig_db_path
        except Exception:
            pass

if __name__ == "__main__":
    unittest.main(verbosity=2)
