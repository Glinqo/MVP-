import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.data_loader import primary_job_profile, public_questions  # noqa: E402
from app.services.assist import assist  # noqa: E402
from app.services.chat import chat_message, chat_start  # noqa: E402
from app.services.explanation import explain  # noqa: E402
from app.services.feedback import append_session_event, save_feedback, teacher_summary  # noqa: E402
from app.services.graph import build_ability_graph, build_job_ability_graph, build_student_ability_graph  # noqa: E402
from app.services.graph_update_engine import (  # noqa: E402
    confirm_job_graph_proposals,
    generate_job_graph_proposals,
    graph_update_timeline,
    record_student_graph_event,
)
from app.services.learner_context import student_bootstrap  # noqa: E402
from app.services.personalized_plan import personalized_plan  # noqa: E402
from app.services.quiz import personalized_quiz  # noqa: E402
from app.services.recommendation import diagnose  # noqa: E402
from app.services.retrieval import search_knowledge  # noqa: E402
from app.services.scenario import list_scenarios, start_scenario, step_scenario  # noqa: E402
from app.services.scoring import score_answers  # noqa: E402


WEB_DIR = ROOT / "web"


class MVPHandler(BaseHTTPRequestHandler):
    server_version = "MechatronicsMVP/0.1"

    def log_message(self, format, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        self.send_json({"error": message}, status=status)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON body: {exc}") from exc

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            return self.send_json({"status": "ok", "app": "mechatronics-agent-mvp", "version": "0.1.0"})

        if path == "/api/quiz":
            return self.send_json({"questions": public_questions()})

        if path == "/api/job-profile":
            return self.send_json({"profile": primary_job_profile()})

        if path == "/api/graph/job":
            return self.send_json(build_job_ability_graph())

        if path == "/api/graph/student":
            session_id = parse_qs(parsed.query).get("session_id", [None])[0]
            return self.send_json(build_student_ability_graph(session_id))

        if path == "/api/student/bootstrap":
            session_id = parse_qs(parsed.query).get("session_id", [None])[0]
            return self.send_json(student_bootstrap(session_id))

        if path == "/api/graph/updates":
            session_id = parse_qs(parsed.query).get("session_id", [None])[0]
            return self.send_json(graph_update_timeline(session_id))

        if path == "/api/graph":
            return self.send_json(build_ability_graph())

        if path == "/api/knowledge/search":
            query = parse_qs(parsed.query).get("query", [""])[0]
            return self.send_json({"query": query, "results": search_knowledge(query)})

        if path == "/api/teacher/summary":
            return self.send_json(teacher_summary())

        if path == "/api/scenarios":
            return self.send_json(list_scenarios())

        return self.serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            payload = self.read_json_body()
            if path == "/api/chat/start":
                return self.send_json(chat_start(payload))
            if path == "/api/chat/message":
                return self.send_json(chat_message(payload))
            if path == "/api/student/bootstrap":
                return self.send_json(student_bootstrap(payload.get("session_id")))
            if path == "/api/quiz/personalized":
                return self.send_json(personalized_quiz(payload))
            if path == "/api/plan/personalized":
                return self.send_json(personalized_plan(payload))
            if path == "/api/explain":
                return self.send_json(explain(payload))
            if path == "/api/scenario/start":
                return self.send_json(start_scenario(payload))
            if path == "/api/scenario/step":
                return self.send_json(step_scenario(payload))
            if path == "/api/graph/student/event":
                event_result = record_student_graph_event(payload)
                return self.send_json({**event_result, "student_graph": build_student_ability_graph(payload.get("session_id"))})
            if path == "/api/graph/job/proposals":
                return self.send_json(generate_job_graph_proposals(payload))
            if path == "/api/graph/job/proposals/confirm":
                result = confirm_job_graph_proposals(payload)
                return self.send_json({**result, "job_graph": build_job_ability_graph()})
            if path == "/api/assist":
                return self.send_json(assist(payload))
            if path == "/api/score":
                score_result = score_answers(payload)
                if payload.get("session_id"):
                    append_session_event(
                        payload.get("session_id"),
                        {
                            "event_type": "score",
                            "answers": payload.get("answers", {}),
                            "score_result": score_result,
                            "weak_abilities": score_result.get("weak_abilities", []),
                            "recommended_path": score_result.get("recommended_path", []),
                        },
                    )
                return self.send_json(score_result)
            if path == "/api/diagnose":
                return self.send_json(diagnose(payload))
            if path == "/api/feedback":
                return self.send_json(save_feedback(payload))
        except ValueError as exc:
            return self.send_error_json(400, str(exc))
        except Exception as exc:  # pragma: no cover - defensive boundary for demo server
            return self.send_error_json(500, str(exc))

        return self.send_error_json(404, "API endpoint not found")

    def serve_static(self, request_path):
        relative = "index.html" if request_path in ("/", "") else request_path.lstrip("/")
        target = (WEB_DIR / relative).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            return self.send_error_json(404, "Not found")

        content = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix in {".html", ".css", ".js"}:
            content_type += "; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def run(host="127.0.0.1", port=8765):
    server = ThreadingHTTPServer((host, port), MVPHandler)
    print(f"Mechatronics MVP running at http://{host}:{port}", flush=True)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Run the local mechatronics MVP server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run(args.host, args.port)


if __name__ == "__main__":
    main()
