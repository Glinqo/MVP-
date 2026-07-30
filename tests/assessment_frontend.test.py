#!/usr/bin/env python3
"""Frontend assessment flow regression tests (v2)."""
import unittest
import json
import threading
import time
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import sys
sys.path.insert(0, ".")
from app.server import MVPHandler

PORT = 19877
BASE = f"http://127.0.0.1:{PORT}"
_server = None
_server_thread = None

def setUpModule():
    global _server, _server_thread
    _server = ThreadingHTTPServer(("127.0.0.1", PORT), MVPHandler)
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{BASE}/api/health", timeout=2)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Server did not start")

def tearDownModule():
    global _server, _server_thread
    if _server:
        _server.shutdown()
        _server.server_close()
    if _server_thread:
        _server_thread.join(timeout=5)

def _req(path, data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=body,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else "{}"
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"error": body}

class FrontendFlowTests(unittest.TestCase):

    def test_01_start_with_job_role(self):
        s, r = _req("/api/student/assess/start", {"session_id":"ff01","job_role":"mechanical_electrical_maintenance_worker"})
        self.assertEqual(s, 200)
        self.assertIn("first_question", r)
        self.assertNotEqual(r["first_question"]["qid"], "")

    def test_02_answer_moves_to_next(self):
        _req("/api/student/assess/start", {"session_id":"ff02","job_role":"mechanical_electrical_maintenance_worker"})
        _, r1 = _req("/api/student/assess/start", {"session_id":"ff02","job_role":"mechanical_electrical_maintenance_worker"})
        qid = r1["first_question"]["qid"]
        key = r1["first_question"]["options"][0]["key"]
        s, r = _req("/api/student/assess/answer", {"session_id":"ff02","qid":qid,"selected_key":key,"job_role":"mechanical_electrical_maintenance_worker"})
        self.assertEqual(s, 200)
        self.assertIn("next_question", r)

    def test_03_start_missing_session_id(self):
        s, _ = _req("/api/student/assess/start", {"job_role":"test"})
        self.assertEqual(s, 400)

    def test_04_answer_missing_session_id(self):
        s, _ = _req("/api/student/assess/answer", {"qid":"A01","selected_key":"A","job_role":"test"})
        self.assertEqual(s, 400, f"Expected 400, got {s}")

    def test_05_resume_same_session(self):
        sid = "ff05_r"
        _req("/api/student/assess/start", {"session_id":sid,"job_role":"mechanical_electrical_maintenance_worker"})
        _, r1 = _req("/api/student/assess/start", {"session_id":sid,"job_role":"mechanical_electrical_maintenance_worker"})
        q1 = r1["first_question"]["qid"]
        k1 = r1["first_question"]["options"][0]["key"]
        _req("/api/student/assess/answer", {"session_id":sid,"qid":q1,"selected_key":k1,"job_role":"mechanical_electrical_maintenance_worker"})
        _, r2 = _req("/api/student/assess/start", {"session_id":sid,"job_role":"mechanical_electrical_maintenance_worker"})
        q2 = r2.get("first_question",{}).get("qid","")
        self.assertNotEqual(q2, q1, f"Resumed should not return same qid: {q2} == {q1}")

    def test_06_answer_ignores_fake_answers_so_far(self):
        sid = "ff06"
        _, r1 = _req("/api/student/assess/start", {"session_id":sid,"job_role":"mechanical_electrical_maintenance_worker"})
        qid = r1["first_question"]["qid"]
        key = r1["first_question"]["options"][0]["key"]
        s, r = _req("/api/student/assess/answer", {"session_id":sid,"qid":qid,"selected_key":key,"job_role":"mechanical_electrical_maintenance_worker","answers_so_far":[{"qid":"FAKE_X","selected":"Z"}]})
        self.assertEqual(s, 200)
        self.assertIn("next_question", r)

    def test_07_idempotent_duplicate_answer(self):
        sid = "ff07"
        _, r1 = _req("/api/student/assess/start", {"session_id":sid,"job_role":"mechanical_electrical_maintenance_worker"})
        qid = r1["first_question"]["qid"]
        key = r1["first_question"]["options"][0]["key"]
        s1, _ = _req("/api/student/assess/answer", {"session_id":sid,"qid":qid,"selected_key":key,"job_role":"mechanical_electrical_maintenance_worker"})
        self.assertEqual(s1, 200)
        s2, _ = _req("/api/student/assess/answer", {"session_id":sid,"qid":qid,"selected_key":key,"job_role":"mechanical_electrical_maintenance_worker"})
        self.assertIn(s2, (200,400), f"Dup answer got {s2}")

    def test_08_completed_reentry(self):
        sid = "ff08_c"
        _, r = _req("/api/student/assess/start", {"session_id":sid,"job_role":"mechanical_electrical_maintenance_worker"})
        qid = r["first_question"]["qid"]
        key = r["first_question"]["options"][0]["key"]
        for _ in range(60):
            s, r = _req("/api/student/assess/answer", {"session_id":sid,"qid":qid,"selected_key":key,"job_role":"mechanical_electrical_maintenance_worker"})
            if s != 200: break
            if r.get("status") == "completed": break
            qid = r.get("next_question",{}).get("qid","")
            if not qid: break
            key = r["next_question"]["options"][0]["key"]
        # Re-start: should error or return without first_question
        s2, r2 = _req("/api/student/assess/start", {"session_id":sid,"job_role":"mechanical_electrical_maintenance_worker"})
        ok = (s2 in (400,409)) or (s2==200 and "first_question" not in r2)
        self.assertTrue(ok, f"Re-start after completion: {s2} {r2}")

    def test_09_summary_needs_session_id(self):
        s, _ = _req("/api/student/assess/summary")
        self.assertEqual(s, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
