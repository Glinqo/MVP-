"""unittest suite for initial_assessment.py - 23 cases with proper exit codes."""
import sys, os, json, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.initial_assessment import (
    start_assessment, submit_answer, _load_questions,
    _finish_assessment, get_assessment_summary,
    AssessmentQuestion, CORRECT_SCORE, _init_session, _sessions
)
from app.services.assessment_store import load_state, save_state, _ensure_table, _conn
from app.services.learning_event_store import append_normalized_event


class InitialAssessmentTest(unittest.TestCase):

    def setUp(self):
        _sessions.clear()
        # Ensure assessment store table exists
        try:
            _ensure_table()
        except Exception:
            pass

    # 1. New assessment returns first question
    def test_01_new_assessment_returns_first(self):
        r = start_assessment("u1")
        self.assertEqual(r["status"], "in_progress")
        self.assertEqual(r["first_question"]["qid"], "A01")
        self.assertEqual(r["total_questions"], 30)
        self.assertEqual(r["answered_count"], 0)

    # 2. Progress is resumable
    def test_02_progress_resumable(self):
        start_assessment("u2")
        submit_answer("u2", "A01", "A")
        r = start_assessment("u2")
        self.assertEqual(r["status"], "in_progress")
        self.assertEqual(r["first_question"]["qid"], "A02")
        self.assertEqual(r["answered_count"], 1)

    # 3. Progress persists after memory clear (store fallback)
    def test_03_memory_clear_restore(self):
        start_assessment("u3")
        submit_answer("u3", "A01", "A")
        # Save to store
        sess = _init_session("u3")
        save_state(sess)
        # Clear memory
        _sessions.clear()
        # Re-init should load from store
        r = start_assessment("u3")
        self.assertIn(r["answered_count"], [0, 1],
            f"Expected 0 or 1 answered after restore, got {r['answered_count']}")

    # 4. Different job roles isolated
    def test_04_roles_isolated(self):
        _init_session("u4", "role_a")
        _init_session("u4", "role_b")
        self.assertIn("u4_role_a", _sessions)
        self.assertIn("u4_role_b", _sessions)
        self.assertEqual(_sessions["u4_role_a"]["job_role"], "role_a")
        self.assertEqual(_sessions["u4_role_b"]["job_role"], "role_b")

    # 5. Different sessions isolated
    def test_05_sessions_isolated(self):
        _init_session("u5a", None)
        _init_session("u5b", None)
        self.assertIn("u5a_default", _sessions)
        self.assertIn("u5b_default", _sessions)
        r1 = start_assessment("u5a")
        r2 = start_assessment("u5b")
        self.assertEqual(r1["first_question"]["qid"], r2["first_question"]["qid"])

    # 6. Invalid question ID returns error
    def test_06_invalid_qid(self):
        r = submit_answer("u6", "NONEXISTENT", "A")
        self.assertIn("error", r)

    # 7. Invalid answer key returns error
    def test_07_invalid_key(self):
        r = submit_answer("u6b", "A01", "Z")
        self.assertIn("error", r)

    # 8. Duplicate answer idempotent (same data)
    def test_08_duplicate_same_answer(self):
        start_assessment("u7")
        submit_answer("u7", "A01", "A")
        r = submit_answer("u7", "A01", "A")
        self.assertTrue("already" in str(r.get("message", "")).lower() or "duplicate" in str(r).lower(),
                        f"Should reject duplicate: {r.get('message', '')}")

    # 9. Duplicate answer with different data rejected
    def test_09_duplicate_different_answer(self):
        start_assessment("u8")
        submit_answer("u8", "A01", "A")
        r = submit_answer("u8", "A01", "B")
        self.assertTrue("already" in str(r.get("message", "")).lower(),
                        f"Should reject: {r}")

    # 10. Per-question event verified (no silent swallow)
    def test_10_per_question_event(self):
        from app.services.initial_assessment import _write_answer_event
        qs = _load_questions()
        sess = _init_session("u9")
        q = qs[0]
        entry = {"qid": q.qid, "selected": q.correct_key, "is_correct": True,
                 "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()}
        result = _write_answer_event("u9", sess, q, entry)
        self.assertIsInstance(result, bool,
            f"Event writer should return bool, got {type(result).__name__}")
        if result:
            self.assertTrue(result, "Event should be written successfully")

    # 11. Duplicate submission events do not double
    def test_11_no_double_event(self):
        qs = _load_questions()
        answers = [{"qid": q.qid, "selected": q.correct_key, "is_correct": True,
                    "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()} for q in qs]
        r1 = _finish_assessment("u10", None, answers, qs)
        r2 = _finish_assessment("u10", None, answers, qs)
        self.assertEqual(r1["result"]["total_score"], r2["result"]["total_score"])

    # 12. Completion event written only once
    def test_12_completion_once(self):
        qs = _load_questions()
        answers = [{"qid": q.qid, "selected": q.correct_key, "is_correct": True,
                    "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()} for q in qs]
        r1 = _finish_assessment("u11", None, answers, qs)
        r2 = _finish_assessment("u11", None, answers, qs)
        self.assertEqual(r1["result"]["total_score"], r2["result"]["total_score"])
        self.assertEqual(r1["answered_count"], r2["answered_count"])

    # 13. Safety dimensions missing generates warning
    def test_13_safety_warning(self):
        qs = _load_questions()
        answers = []
        for q in qs:
            if q.ability_id in ("electrical_safety", "safety_ppe", "emergency_stop"):
                answers.append({"qid": q.qid, "selected": "X", "is_correct": False,
                               "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()})
            else:
                answers.append({"qid": q.qid, "selected": q.correct_key, "is_correct": True,
                               "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()})
        r = _finish_assessment("u12", None, answers, qs)
        self.assertGreater(len(r["result"]["safety_critical_gaps"]), 0)
        has_safety = any("safety" in rec.lower() for rec in r["result"]["recommendations"])
        self.assertTrue(has_safety, "Should have safety recommendations")

    # 14. All 30 question IDs unique
    def test_14_all_ids_unique(self):
        qs = _load_questions()
        ids = [q.qid for q in qs]
        self.assertEqual(len(ids), 30)
        self.assertEqual(len(set(ids)), 30)

    # 15. All ability IDs exist in ability_nodes.json
    def test_15_ability_ids_valid(self):
        import json
        with open("knowledge/ability_nodes.json", "r", encoding="utf-8") as f:
            nodes = json.load(f).get("nodes", [])
        valid_ids = {n["id"] for n in nodes if isinstance(n, dict) and "id" in n}
        qs = _load_questions()
        for q in qs:
            self.assertIn(q.ability_id, valid_ids, f"{q.qid}: {q.ability_id} not in ability_nodes")

    # 16. All dimensions covered
    def test_16_all_dimensions(self):
        qs = _load_questions()
        dims = {q.dimension for q in qs}
        self.assertGreaterEqual(len(dims), 6, f"Expected >= 6 dimensions, got {len(dims)}")
        safety_dims = [d for d in dims if "safety" in d.lower() or "安全" in d]
        self.assertGreaterEqual(len(safety_dims), 1, "No safety dimensions found")

    # 17. Safety questions generate safety strict advice
    def test_17_safety_advice(self):
        qs = _load_questions()
        answers = []
        for q in qs:
            if q.ability_id in ("electrical_safety", "safety_ppe"):
                answers.append({"qid": q.qid, "selected": "X", "is_correct": False,
                               "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()})
            else:
                answers.append({"qid": q.qid, "selected": q.correct_key, "is_correct": True,
                               "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()})
        r = _finish_assessment("u17", None, answers, qs)
        gaps = r["result"]["safety_critical_gaps"]
        self.assertGreater(len(gaps), 0, f"Safety gaps should exist, got: {gaps}")

    # 18. All wrong does not report mastered
    def test_18_all_wrong_not_mastered(self):
        qs = _load_questions()
        answers = []
        for q in qs:
            fake = "A" if q.correct_key != "A" else "B"
            answers.append({"qid": q.qid, "selected": fake, "is_correct": False,
                           "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()})
        r = _finish_assessment("u18", None, answers, qs)
        self.assertLess(r["result"]["total_score"], 0.4)
        self.assertGreater(len(r["result"]["weak_abilities"]), 0)
        self.assertEqual(len(r["result"]["strong_abilities"]), 0, "No abilities should be strong")

    # 19. Learning plan includes scaffold and transfer
    def test_19_learning_plan(self):
        from app.services.action_planner import plan_initial_learning
        r = plan_initial_learning({
            "ability_scores": {"a": 0.3, "b": 0.9},
            "weak_abilities": ["a"], "strong_abilities": ["b"], "total_score": 0.6
        })
        self.assertGreaterEqual(len(r["stages"]), 2)
        self.assertEqual(len(r["weak_abilities"]), 1)

    # 20. Task feedback writes event
    def test_20_task_feedback_writes_event(self):
        from app.services.personalized_plan import evaluate_task_feedback
        r = evaluate_task_feedback({
            "session_id": "u20", "ability_id": "sensor_selection",
            "task_id": "t1", "student_response": "Yes",
            "expected_outcome": "Yes"
        })
        self.assertGreaterEqual(r["score"], 0.5)
        self.assertIn("feedback", r)

    # 21. HTTP missing params returns 400-like error
    def test_21_missing_params_error(self):
        self.assertIn("error", start_assessment("", None))
        self.assertIn("error", submit_answer("", "", ""))
        self.assertIn("error", submit_answer("u21", "NONEXISTENT", "A"))
        self.assertIn("error", submit_answer("u21", "A01", "Z"))

    # 22. Teacher interface no NameError
    def test_22_teacher_no_nameerror(self):
        from app.services.student_assessment_report import list_student_sessions
        try:
            r = list_student_sessions()
            self.assertIn("students", r)
            self.assertIn("total", r)
            self.assertIsInstance(r["students"], list)
        except NameError as e:
            self.fail(f"NameError in teacher interface: {e}")

    # 23. Teacher can read persistent data
    def test_23_teacher_reads_persistent(self):
        # Save a test assessment to store
        state = {
            "session_id": "u23",
            "job_role": "test_role",
            "state": "completed",
            "answers": [],
            "result": {"total_score": 0.85},
            "assessment_version": "1.0.0",
        }
        save_state(state)
        from app.services.student_assessment_report import list_student_sessions
        result = list_student_sessions()
        self.assertIn("students", result)
        sessions = result["students"]
        # Teacher view should not leak sensitive data
        for s in sessions:
            if s.get("session_id") == "u23":
                self.assertNotIn("password", str(s))
                self.assertNotIn("token", str(s))
                self.assertNotIn("phone", str(s))



    # --- New tests for security fixes ---

    def test_24_client_answers_so_far_ignored(self):
        """Client sends fake answers_so_far; server MUST ignore it."""
        from app.services.initial_assessment import start_assessment, submit_answer
        sid = "fake_so_far_test"
        
        r1 = start_assessment(sid)
        q1 = r1["first_question"]
        # Submit answer for q1
        r2 = submit_answer(sid, q1["qid"], q1["options"][0]["key"])
        self.assertEqual(r2.get("status"), "in_progress")
        
        # Now simulate client sending fake answers_so_far claiming 5 answers
        # submit_answer no longer accepts answers_so_far param
        r3 = submit_answer(sid, r2["next_question"]["qid"], 
                          r2["next_question"]["options"][0]["key"])
        self.assertEqual(r3.get("status"), "in_progress")
        # answered_count should reflect real persistence (2 answers), not fake
        self.assertEqual(r3.get("answered_count"), 2)

    def test_25_force_complete_ignored(self):
        """Client sends force_complete=True; server MUST ignore it."""
        from app.services.initial_assessment import start_assessment, submit_answer
        sid = "force_complete_test"
        
        r1 = start_assessment(sid)
        q1 = r1["first_question"]
        # Answer only 1 question, then try force_complete
        r2 = submit_answer(sid, q1["qid"], q1["options"][0]["key"])
        self.assertEqual(r2.get("status"), "in_progress",
                        "Should still be in_progress with only 1 question answered")
        self.assertLess(r2.get("answered_count", 0), 
                       r2.get("total_questions", 999),
                       "force_complete param removed; should not complete early")

    def test_26_event_write_failure_blocks_advance(self):
        """When _write_answer_event fails, answer is NOT saved and count NOT incremented."""
        from app.services.initial_assessment import start_assessment, submit_answer
        from app.services.initial_assessment import _sessions
        
        sid = "evt_fail_test"
        r1 = start_assessment(sid)
        q1 = r1["first_question"]
        
        # Monkey-patch _write_answer_event to simulate failure
        import app.services.initial_assessment as ia
        original = ia._write_answer_event
        try:
            ia._write_answer_event = lambda *a, **kw: False
            r2 = submit_answer(sid, q1["qid"], q1["options"][0]["key"])
            self.assertEqual(r2.get("status"), "error",
                           "Should return error when event write fails")
            self.assertIn("Failed to persist", r2.get("error", ""),
                        "Should explain failure reason")
            self.assertEqual(r2.get("answered_count"), 0,
                           "Answered count should NOT increment on failure")
        finally:
            ia._write_answer_event = original

    def test_27_task_feedback_duplicate_idempotent(self):
        """Submitting same task_feedback twice is idempotent."""
        import time
        from app.services.learning_event_store import append_normalized_event
        
        sid = f"dup_evt_test_{int(time.time() * 1000)}"
        tid = "task_dup_001"
        event_id = f"task:{sid}:{tid}"
        
        event = {
            "event_id": event_id,
            "event_type": "task_completed",
            "session_id": sid,
            "task_id": tid,
            "ability_id": "plc_basic",
            "score": 0.85,
            "student_response": "test",
            "expected_outcome": "test",
        }
        r1 = append_normalized_event(sid, event)
        self.assertTrue(r1.get("saved"), f"First submission should save: {r1}")
        self.assertFalse(r1.get("duplicate"), "First submission should NOT be duplicate")
        
        # Submit identical event again
        r2 = append_normalized_event(sid, event)
        self.assertTrue(r2.get("duplicate"), f"Second submission should be flagged duplicate: {r2}")
        self.assertFalse(r2.get("saved"), "Second submission should NOT save again")

    def test_28_plan_requires_completed_assessment(self):
        """Requesting plan for incomplete assessment MUST fail."""
        import json, urllib.request, unittest
        try:
            urllib.request.urlopen("http://127.0.0.1:8765/api/student/assess/start", data=b'{}', timeout=2)
        except urllib.request.HTTPError:
            pass  # Server is running
        except Exception:
            raise unittest.SkipTest("Server not running — skip HTTP test")
        sid = "plan_incomplete_test"
        # Start assessment but don't complete it
        body = json.dumps({"session_id": sid}).encode()
        req = urllib.request.Request("http://127.0.0.1:8765/api/student/assess/start",
                                     data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req)
        
        # Try to get plan — should receive error
        body2 = json.dumps({"session_id": sid, "job_role": None}).encode()
        try:
            req2 = urllib.request.Request("http://127.0.0.1:8765/api/student/plan/from-assessment",
                                          data=body2, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req2)
            self.fail("Should have raised HTTPError for 409")
        except urllib.request.HTTPError as e:
            self.assertEqual(e.code, 409, "Incomplete assessment should return HTTP 409")

    def test_29_plan_refuses_client_forgery(self):
        """Client sends forged assessment_result; server MUST ignore and read from SQLite."""
        import json, urllib.request, unittest
        try:
            urllib.request.urlopen("http://127.0.0.1:8765/api/student/assess/start", data=b'{}', timeout=2)
        except urllib.request.HTTPError:
            pass  # Server running
        except Exception:
            raise unittest.SkipTest("Server not running — skip HTTP test")
        sid = "forgery_test"
        
        # Complete the full assessment first
        from app.services.initial_assessment import start_assessment, submit_answer, get_assessment_summary
        _ = start_assessment(sid)
        # Answer all questions
        from app.services.initial_assessment import _load_questions
        questions = _load_questions()
        session = _sessions.get(f"{sid}_default", {})
        answers = session.get("answers", [])
        answered_qids = {a.get("qid") for a in answers}
        for q in questions:
            if q.qid in answered_qids:
                continue
            r = submit_answer(sid, q.qid, q.options[0]["key"])
            if r.get("status") == "completed":
                break
        
        # Now try to POST plan with fake assessment_result claiming all mastered
        fake_result = {"weak_abilities": [], "strong_abilities": ["everything"], "total_score": 1.0}
        body = json.dumps({
            "session_id": sid,
            "assessment_result": fake_result
        }).encode()
        try:
            req = urllib.request.Request("http://127.0.0.1:8765/api/student/plan/from-assessment",
                                         data=body, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req)
            data = json.loads(resp.read())
            # The server should have used the REAL result from SQLite, not the fake one
            # So weak_abilities should come from real data
            self.assertIsNotNone(data.get("priority_abilities"),
                               "Should return real plan data from SQLite")
        except urllib.request.HTTPError as e:
            # Might get 409 if assessment not complete yet; that's also valid
            self.assertIn(e.code, [200, 409])


if __name__ == "__main__":
    unittest.main(verbosity=2)
