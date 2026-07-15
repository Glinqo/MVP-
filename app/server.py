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
from app.services.graph import build_ability_graph, build_job_ability_graph, build_student_ability_graph, build_student_job_gap  # noqa: E402
from app.services.graph_update_engine import (  # noqa: E402
    confirm_job_graph_proposals,
    confirm_sqlite_job_graph_proposal,
    confirm_sqlite_job_graph_proposals,
    generate_job_graph_proposals,
    graph_update_timeline,
    record_student_graph_event,
)
from app.services.learner_context import student_bootstrap  # noqa: E402
from app.services.personalized_plan import personalized_plan  # noqa: E402
from app.services.quiz import personalized_quiz  # noqa: E402
from app.services.recommendation import diagnose  # noqa: E402
from app.services.retrieval import search_knowledge  # noqa: E402
from app.services.scenario import action_scenario, list_scenarios, start_scenario, step_scenario  # noqa: E402
from app.services.diagnostic_trace import build_diagnostic_trace  # noqa: E402
from app.services.conformance_engine import check_conformance  # noqa: E402
from app.services.process_metrics import compute_all_metrics  # noqa: E402
from app.services.strategy_profile import build_cumulative_strategy_profile  # noqa: E402
from app.services.cognitive_twin import build_cognitive_twin  # noqa: E402
from app.services.counterfactual_action import analyze_next_action  # noqa: E402
from app.services.model_tracer import model_for_scenario, state_flags_from_runtime  # noqa: E402
from app.services.scoring import score_answers  # noqa: E402
from app.services.student_dashboard import build_student_dashboard  # noqa: E402

from scripts.pipeline.evidence_store import list_snapshots, get_snapshot, version_diff, version_rollback
from scripts.pipeline.job_data_importer import ingest_job_text
from app.services.matching import compute_match
from app.services.learning_event_store import get_events, get_event_timeline, get_ability_events, append_normalized_event, list_sessions  # noqa: E402
from app.services.ability_state_engine import compute_ability_state  # noqa: E402
from app.services.next_action_recommender import recommend_next_actions  # noqa: E402
from app.services.device_state_handler import record_device_state  # noqa: E402



WEB_DIR = ROOT / "web"


def _compute_job_gap(session_id):
    from app.services.ability_state_engine import compute_ability_state as _cs
    from app.services.graph import build_job_ability_graph as _bjg
    state = _cs(session_id)
    abilities = state.get("abilities", {})
    job_graph = _bjg()
    job_nodes = {n["id"]: n for n in job_graph.get("nodes", [])}
    gaps = []
    for aid, astate in abilities.items():
        job_node = job_nodes.get(aid, {})
        demand_weight = job_node.get("demand_weight", 0)
        importance = min(100, demand_weight * 40) if demand_weight > 0 else 30
        student_mastery = astate.get("cognitive_mastery_score", 50)
        gap = max(0, importance - student_mastery) / 100.0
        if demand_weight > 0:
            gaps.append({
                "ability_id": aid,
                "ability_name": astate.get("ability_name", aid),
                "job_importance": round(importance / 100.0, 2),
                "student_mastery": student_mastery,
                "gap_score": round(gap, 3),
                "reason": "岗位要求高，当前掌握偏低。",
                "next_action": astate.get("recommended_action", {}).get("title", ""),
            })
    gaps.sort(key=lambda g: -g["gap_score"])
    return {
        "target_role": job_graph.get("role", "自动化生产线装调与运维技术员"),
        "top_gaps": gaps[:5],
        "total_gaps": len(gaps),
        "session_id": session_id,
    }



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
        query_params = parse_qs(parsed.query)

        if path == "/api/health":
            return self.send_json({"status": "ok", "app": "mechatronics-agent-mvp", "version": "0.1.0"})

        if path == "/api/quiz":
            return self.send_json({"questions": public_questions()})

        if path == "/api/job-profile":
            return self.send_json({"profile": primary_job_profile()})

        if path == "/api/job-data/documents":
            query = parse_qs(parsed.query)
            source_type = query.get("source_type", [None])[0]
            limit = int(query.get("limit", [50])[0])
            from scripts.pipeline.evidence_store import list_raw_documents
            return self.send_json({"documents": list_raw_documents(source_type, limit)})

        if path == "/api/job-data/posts":
            query = parse_qs(parsed.query)
            job_role = query.get("job_role", [None])[0]
            limit = int(query.get("limit", [50])[0])
            from scripts.pipeline.evidence_store import list_job_posts
            return self.send_json({"posts": list_job_posts(job_role, limit)})

        if path == "/api/graph/job":
            job_role = parse_qs(parsed.query).get("job_role", [None])[0]
            return self.send_json(build_job_ability_graph(job_role))

        if path == "/api/graph/student":
            session_id = parse_qs(parsed.query).get("session_id", [None])[0]
            return self.send_json(build_student_ability_graph(session_id))

        if path == "/api/graph/gap":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [None])[0]
            limit = int(query.get("limit", [5])[0])
            return self.send_json(build_student_job_gap(session_id, limit=limit))

        if path == "/api/student/bootstrap":
            session_id = parse_qs(parsed.query).get("session_id", [None])[0]
            return self.send_json(student_bootstrap(session_id))

        if path == "/api/student/dashboard":
            session_id = parse_qs(parsed.query).get("session_id", [None])[0]
            return self.send_json(build_student_dashboard(session_id))

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

        if path == "/api/graph/job/proposals/pending":
            job_role = parse_qs(parsed.query).get("job_role", [None])[0]
            from scripts.pipeline.evidence_store import get_pending_proposals
            return self.send_json({"proposals": get_pending_proposals(job_role)})

        if path == "/api/student/diagnostic-traces":
            session_id = parse_qs(parsed.query).get("session_id", [None])[0]
            if not session_id:
                return self.send_error_json(400, "session_id is required")
            return self.send_json(build_diagnostic_trace(session_id, parse_qs(parsed.query).get("scenario_id", [""])[0]))

        if path == "/api/student/strategy-profile":
            session_id = parse_qs(parsed.query).get("session_id", [None])[0]
            if not session_id:
                return self.send_error_json(400, "session_id is required")
            return self.send_json(build_cumulative_strategy_profile(session_id))

        if path == "/api/student/events":
            session_id = query_params.get("session_id", ["default"])[0]
            event_type = query_params.get("event_type", [None])[0]
            ability_id = query_params.get("ability_id", [None])[0]
            scenario_id = query_params.get("scenario_id", [None])[0]
            category = query_params.get("category", [None])[0]
            limit = int(query_params.get("limit", ["100"])[0])
            offset = int(query_params.get("offset", ["0"])[0])
            return self.send_json(get_events(
                session_id, event_type=event_type, ability_id=ability_id,
                scenario_id=scenario_id, category=category,
                limit=limit, offset=offset
            ))

        if path == "/api/student/events/timeline":
            session_id = query_params.get("session_id", ["default"])[0]
            return self.send_json(get_event_timeline(session_id))

        if path == "/api/student/ability-evidence":
            session_id = query_params.get("session_id", ["default"])[0]
            ability_id = query_params.get("ability_id", [None])[0]
            if not ability_id:
                return self.send_error_json(400, "ability_id is required")
            return self.send_json(get_ability_events(session_id, ability_id))

        if path == "/api/sessions":
            return self.send_json(list_sessions())

        if path == "/api/student/ability-state":
            session_id = query_params.get("session_id", ["default"])[0]
            ability_id = query_params.get("ability_id", [None])[0]
            return self.send_json(compute_ability_state(session_id, ability_id))

        if path == "/api/student/next-actions":
            session_id = query_params.get("session_id", ["default"])[0]
            count = int(query_params.get("count", ["5"])[0])
            return self.send_json(recommend_next_actions(session_id, count))

        if path == "/api/student/job-gap":
            session_id = query_params.get("session_id", ["default"])[0]
            return self.send_json(_compute_job_gap(session_id))

        if path == "/api/scenario/next-action":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [None])[0]
            scenario_id = query.get("scenario_id", [None])[0]
            if not scenario_id:
                return self.send_error_json(400, "scenario_id is required")
            model = model_for_scenario(scenario_id)
            if not model:
                return self.send_error_json(404, f"no model for {scenario_id}")
            # Get current state from action_scenario session if available
            from app.services.scenario import _session_state
            sess = _session_state(session_id or "default")
            current_state = sess.get("current_state", {"state_id": "STATE_INITIAL"})
            state_id = current_state.get("state_id", "STATE_INITIAL")
            action_history = sess.get("action_history", [])
            state_flags = state_flags_from_runtime(model, current_state)
            result = analyze_next_action(
                model, state_flags, action_history
            )
            result["current_state_id"] = state_id
            return self.send_json(result)

        if path == "/api/student/cognitive-twin":
            session_id = parse_qs(parsed.query).get("session_id", [None])[0]
            if not session_id:
                return self.send_error_json(400, "session_id is required")
            return self.send_json(build_cognitive_twin(session_id))

        if path == "/api/scenarios":
            return self.send_json(list_scenarios())

        if path == "/api/graph/job/versions":
            job_role = parse_qs(parsed.query).get("job_role", [None])[0]
            return self.send_json({"versions": list_snapshots(job_role)})

        if path == "/api/graph/job/versions/diff":
            v1 = parse_qs(parsed.query).get("v1", [""])[0]
            v2 = parse_qs(parsed.query).get("v2", [""])[0]
            job_role = parse_qs(parsed.query).get("job_role", [None])[0]
            return self.send_json(version_diff(v1, v2, job_role))

        if path == "/api/student/job-match":
            session_id = parse_qs(parsed.query).get("session_id", [None])[0]
            return self.send_json(compute_match(session_id))

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
            if path == "/api/scenario/action":
                return self.send_json(action_scenario(payload))
            if path == "/api/student/device-state":
                return self.send_json(record_device_state(payload))

            if path == "/api/graph/student/event":
                event_result = record_student_graph_event(payload)
                return self.send_json({**event_result, "student_graph": build_student_ability_graph(payload.get("session_id"))})
            if path == "/api/graph/job/proposals":
                return self.send_json(generate_job_graph_proposals(payload))
            if path == "/api/job-data/collect":
                from scripts.job_intelligence_update import DEFAULT_RUN_LOG, DEFAULT_SOURCES, run_update

                def optional_int(value):
                    if value in (None, ""):
                        return None
                    return int(value)

                args = argparse.Namespace(
                    sources=payload.get("sources", str(DEFAULT_SOURCES)),
                    source_id=payload.get("source_id"),
                    dry_run=bool(payload.get("dry_run", False)),
                    max_sources=optional_int(payload.get("max_sources")),
                    timeout=optional_int(payload.get("timeout")),
                    max_bytes=optional_int(payload.get("max_bytes")),
                    run_log=payload.get("run_log", str(DEFAULT_RUN_LOG)),
                    store=payload.get("store", "sqlite"),
                    use_llm=bool(payload.get("use_llm", False)),
                    max_abilities=int(payload.get("max_abilities", 5) or 5),
                )
                return self.send_json(run_update(args))
            if path == "/api/graph/job/ingest":
                text = (payload.get("text") or "").strip()
                if not text:
                    return self.send_error_json(400, "text is required")
                source_type = payload.get("source_type", "teacher_material")
                source_url = payload.get("source_url", "")
                source = payload.get("source", "ingest_" + source_type)
                use_llm = bool(payload.get("use_llm", False))
                job_role = payload.get("job_role") or primary_job_profile().get("role_name", "自动化生产线装调与运维技术员")
                max_abilities = int(payload.get("max_abilities", 5) or 5)
                return self.send_json(ingest_job_text(
                    text,
                    job_role=job_role,
                    source_type=source_type,
                    source=source,
                    source_url=source_url,
                    use_llm=use_llm,
                    max_abilities=max_abilities,
                ))
            if path == "/api/graph/job/proposals/confirm-sqlite":
                return self.send_json(confirm_sqlite_job_graph_proposal(payload))
            if path == "/api/graph/job/proposals/confirm-sqlite-batch":
                return self.send_json(confirm_sqlite_job_graph_proposals(payload))
            if path == "/api/graph/job/proposals/confirm":
                result = confirm_job_graph_proposals(payload)
                return self.send_json({**result, "job_graph": build_job_ability_graph()})
            if path == "/api/graph/job/versions/rollback":
                return self.send_json(version_rollback(payload.get("version"), payload.get("job_role")))
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
