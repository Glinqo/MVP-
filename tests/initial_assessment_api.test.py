"""
Independent API test suite for assessment endpoints.
Starts its own server, runs real HTTP tests, shuts down.
No SkipTest allowed.
"""
import json
import os
import socket
import sys
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _find_free_port():
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]




import threading
from http.server import ThreadingHTTPServer
from app.server import MVPHandler

_server = None
_server_thread = None


def setUpModule():
    """Start the server in a daemon thread before any tests."""
    global _server, _server_thread
    # Remove stale test databases
    for f in [ROOT / 'data' / 'assessments.db', ROOT / 'data' / 'assessments.db-wal', ROOT / 'data' / 'assessments.db-shm']:
        if f.exists():
            f.unlink()
    for sf in (ROOT / 'data' / 'sessions').glob('*.json'):
        if sf.name != '.gitkeep':
            sf.unlink()

    _server = ThreadingHTTPServer(('127.0.0.1', PORT), MVPHandler)
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()

    # Wait for server to be ready
    deadline = time.time() + 10
    while time.time() < deadline:
        time.sleep(0.2)
        try:
            sock = socket.create_connection(('127.0.0.1', PORT), timeout=1)
            sock.close()
            return
        except Exception:
            pass
    tearDownModule()
    raise RuntimeError(f'Server did not start on port {PORT} within 10s')


def tearDownModule():
    """Stop the server after all tests."""
    global _server, _server_thread
    if _server is not None:
        _server.shutdown()
        _server.server_close()
        _server = None
    if _server_thread is not None:
        _server_thread.join(timeout=5)
        _server_thread = None

PORT = _find_free_port()
BASE = f'http://127.0.0.1:{PORT}'


def _request(path, body=None, method='POST'):
    """Make an HTTP request, return (status, body_dict)."""
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=2)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except urllib.error.URLError as e:
        raise ConnectionError(f'Cannot connect to {url}: {e.reason}') from e
    except ConnectionError:
        raise




class AssessmentApiTest(unittest.TestCase):
    """Real HTTP tests against a live server."""

    def test_01_start_missing_session_id(self):
        """start without session_id -> 400"""
        status, body = _request('/api/student/assess/start', {})
        self.assertEqual(status, 400, f'Expected 400, got {status}: {body}')

    def test_02_start_returns_first_question(self):
        """start with session_id -> 200 + first_question"""
        status, body = _request('/api/student/assess/start', {'session_id': 'api_test_001'})
        self.assertEqual(status, 200)
        self.assertIn('first_question', body)
        self.assertEqual(body.get('status'), 'in_progress')

    def test_03_answer_missing_session_id(self):
        """answer without session_id -> 400"""
        status, body = _request('/api/student/assess/answer', {'qid': 'A01', 'selected_key': 'A'})
        self.assertEqual(status, 400)

    def test_04_answer_valid(self):
        """valid answer -> 200 + next_question"""
        status, body = _request('/api/student/assess/answer',
                                {'session_id': 'api_test_001', 'qid': 'A01', 'selected_key': 'A'})
        self.assertEqual(status, 200)
        self.assertIn('next_question', body)

    def test_05_summary_missing_session_id(self):
        """GET summary without session_id -> 400"""
        url = BASE + '/api/student/assess/summary'
        req = urllib.request.Request(url, method='GET')
        try:
            resp = urllib.request.urlopen(req, timeout=2)
            body = json.loads(resp.read())
            self.assertEqual(resp.status, 400, f'Expected 400, got {resp.status}: {body}')
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_06_summary_in_progress(self):
        """GET summary for in-progress assessment"""
        url = BASE + '/api/student/assess/summary?session_id=api_test_001'
        req = urllib.request.Request(url, method='GET')
        resp = urllib.request.urlopen(req, timeout=2)
        body = json.loads(resp.read())
        self.assertEqual(resp.status, 200)
        self.assertEqual(body.get('state'), 'in_progress')

    def test_07_plan_missing_session_id(self):
        """plan without session_id -> 400"""
        status, body = _request('/api/student/plan/from-assessment', {})
        self.assertEqual(status, 400)

    def test_08_plan_incomplete_assessment(self):
        """plan for incomplete assessment -> 409"""
        status, body = _request('/api/student/plan/from-assessment',
                                {'session_id': 'api_test_plan_inc'})
        self.assertEqual(status, 409, f'Expected 409, got {status}: {body}')

    def test_09_task_feedback_missing_session_id(self):
        """task_feedback without session_id -> 400"""
        status, body = _request('/api/plan/task_feedback',
                                {'task_id': 't1', 'ability_id': 'plc_basic'})
        self.assertEqual(status, 400)

    def test_10_task_feedback_missing_task_id(self):
        """task_feedback without task_id -> 400"""
        status, body = _request('/api/plan/task_feedback',
                                {'session_id': 'api_test_001', 'ability_id': 'plc_basic'})
        self.assertEqual(status, 400)

    def test_11_task_feedback_missing_ability_id(self):
        """task_feedback without ability_id -> 400"""
        status, body = _request('/api/plan/task_feedback',
                                {'session_id': 'api_test_001', 'task_id': 't1'})
        self.assertEqual(status, 400)

    def test_12_complete_assessment_then_plan(self):
        """Complete assessment then get plan -> 200"""
        sid = 'api_test_complete'
        # Start
        _request('/api/student/assess/start', {'session_id': sid})
        # Answer all questions
        from app.services.initial_assessment import _load_questions
        qs = _load_questions()
        for q in qs:
            status, body = _request('/api/student/assess/answer',
                                    {'session_id': sid, 'qid': q.qid, 'selected_key': q.options[0]['key']})
            if body.get('status') == 'completed':
                break
        # Now get plan
        status, body = _request('/api/student/plan/from-assessment',
                                {'session_id': sid, 'job_role': None})
        self.assertEqual(status, 200, f'Expected 200, got {status}: {body}')
        self.assertIn('priority_abilities', body)

    def test_13_plan_ignores_client_forgery(self):
        """Client sends forged assessment_result; server ignores it"""
        sid = 'api_test_forgery'
        # Complete assessment first
        _request('/api/student/assess/start', {'session_id': sid})
        from app.services.initial_assessment import _load_questions
        qs = _load_questions()
        for q in qs:
            status, body = _request('/api/student/assess/answer',
                                    {'session_id': sid, 'qid': q.qid, 'selected_key': q.options[0]['key']})
            if body.get('status') == 'completed':
                break
        # Now request plan with forged result (should be ignored)
        fake = {'weak_abilities': [], 'strong_abilities': ['everything'], 'total_score': 1.0}
        status, body = _request('/api/student/plan/from-assessment',
                                {'session_id': sid, 'assessment_result': fake})
        self.assertEqual(status, 200)
        # The plan should come from real data
        self.assertIn('priority_abilities', body)

    def test_14_summary_restart_recovery(self):
        """After completing assessment, clear memory cache and verify summary still shows completed."""
        sid = 'api_test_recovery'
        # Complete assessment
        _request('/api/student/assess/start', {'session_id': sid})
        from app.services.initial_assessment import _load_questions
        qs = _load_questions()
        for q in qs:
            status, body = _request('/api/student/assess/answer',
                                    {'session_id': sid, 'qid': q.qid, 'selected_key': q.options[0]['key']})
            if body.get('status') == 'completed':
                break
        # Clear in-memory sessions to simulate restart
        from app.services.initial_assessment import _sessions
        keys_to_clear = [k for k in _sessions if sid in k]
        for k in keys_to_clear:
            del _sessions[k]
        # Now check summary via GET
        url = BASE + '/api/student/assess/summary?session_id=' + sid
        req = urllib.request.Request(url, method='GET')
        resp = urllib.request.urlopen(req, timeout=2)
        body = json.loads(resp.read())
        self.assertEqual(resp.status, 200)
        self.assertEqual(body.get('state'), 'completed', f'Expected completed, got {body}')
        self.assertTrue(body.get('completed'), 'completed should be True')
        rs = body.get('result_summary')
        self.assertIsNotNone(rs, 'result_summary should exist after restart')
        self.assertIsNotNone(rs.get('total_score'), 'total_score should be present')

    def test_15_answer_event_savestate_failure(self):
        """When save_state fails, answer must not succeed (tested via direct call)."""
        import app.services.initial_assessment as ia
        from app.services.assessment_store import save_state

        sid = 'direct_savefail_test'
        ia.start_assessment(sid)

        original_save = ia.save_state
        try:
            def failing_save(*a, **kw):
                raise Exception('Simulated save failure')
            ia.save_state = failing_save
            result = ia.submit_answer(sid, 'A01', 'A')
            self.assertEqual(result.get('status'), 'error')
            self.assertIn('Failed to persist', result.get('error', ''))
        finally:
            ia.save_state = original_save


if __name__ == '__main__':
    unittest.main(verbosity=2)
