import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORT = 8766
BASE_URL = f"http://127.0.0.1:{PORT}"
PYTHON = sys.executable


def request_json(path, payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_server(process):
    for _ in range(40):
        if process.poll() is not None:
            raise RuntimeError("server exited early")
        try:
            health = request_json("/api/health")
            if health.get("status") == "ok":
                return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    raise TimeoutError("server did not become ready")


def main():
    session_file = ROOT / "data" / "sessions" / "api-smoke-test.json"
    if session_file.exists():
        session_file.unlink()
    runtime_files = [
        ROOT / "data" / "graph_update_events.json",
        ROOT / "data" / "job_graph_update_proposals.json",
        ROOT / "data" / "job_graph_confirmed_snapshots.json",
    ]
    runtime_backups = {path: path.read_text(encoding="utf-8") if path.exists() else None for path in runtime_files}

    env = os.environ.copy()
    env.pop("LLM_API_KEY", None)
    env.pop("LLM_BASE_URL", None)
    env.pop("LLM_MODEL", None)

    process = subprocess.Popen(
        [PYTHON, str(ROOT / "app" / "server.py"), "--port", str(PORT)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server(process)

        quiz = request_json("/api/quiz")
        assert len(quiz["questions"]) == 20
        assert "correct_answer" not in quiz["questions"][0]

        job = request_json("/api/job-profile")
        assert job["profile"]["role_name"] == "自动化生产线装调与运维技术员"
        assert "sensor_type_identification" in job["profile"]["ability_chain"]

        graph = request_json("/api/graph")
        assert graph["mermaid"].startswith("flowchart TD")
        assert len(graph["nodes"]) >= 6

        job_graph = request_json("/api/graph/job")
        assert job_graph["graph_type"] == "job_ability"
        assert job_graph["job_role"] == "自动化生产线装调与运维技术员"
        assert job_graph["demand_sources"]
        assert any(node["status"] == "industry_hot" for node in job_graph["nodes"])

        student_graph = request_json("/api/graph/student?session_id=api-smoke-test")
        assert student_graph["graph_type"] == "student_ability"
        assert student_graph["event_count"] == 0
        assert "mastery_profile" in student_graph
        first_student_node = student_graph["nodes"][0]
        for key in [
            "knowledge_mastery",
            "procedure_mastery",
            "transfer_score",
            "safety_score",
            "cognitive_mastery_score",
            "uncertainty",
        ]:
            assert key in first_student_node

        student_events = request_json("/api/student/events?session_id=api-smoke-test")
        assert student_events["session_id"] == "api-smoke-test"
        assert "events" in student_events

        student_timeline = request_json("/api/student/events/timeline?session_id=api-smoke-test")
        assert student_timeline["session_id"] == "api-smoke-test"
        assert "stats" in student_timeline

        ability_state = request_json("/api/student/ability-state?session_id=api-smoke-test")
        assert ability_state["session_id"] == "api-smoke-test"
        assert ability_state["abilities"]

        next_actions = request_json("/api/student/next-actions?session_id=api-smoke-test&count=2")
        assert next_actions["session_id"] == "api-smoke-test"
        assert 1 <= len(next_actions["actions"]) <= 2

        student_job_gap = request_json("/api/student/job-gap?session_id=api-smoke-test")
        assert student_job_gap["session_id"] == "api-smoke-test"
        assert "top_gaps" in student_job_gap

        chat_start = request_json("/api/chat/start", {"session_id": "api-smoke-test"})
        assert "自动化生产线装调与运维技术员" in chat_start["welcome"]
        assert chat_start["llm_configured"] is False
        assert len(chat_start["suggested_questions"]) >= 2
        assert chat_start["learner_context"]["session_id"] == "api-smoke-test"

        bootstrap = request_json("/api/student/bootstrap?session_id=api-smoke-test")
        assert bootstrap["session_id"] == "api-smoke-test"
        assert bootstrap["learner_context"]["event_count"] == 0
        assert bootstrap["student_graph"]["graph_type"] == "student_ability"
        assert bootstrap["tool_suggestions"]

        dashboard = request_json("/api/student/dashboard?session_id=api-smoke-test")
        assert dashboard["session_id"] == "api-smoke-test"
        assert dashboard["dashboard_title"] == "学生学习驾驶舱"
        assert dashboard["readiness_score"] >= 0
        assert dashboard["today_actions"]
        assert dashboard["tool_suggestions"]

        chat_reply = request_json(
            "/api/chat/message",
            {
                "session_id": "api-smoke-test",
                "message": "传感器动作灯亮但 PLC 没输入，为什么？",
                "context": {
                    "sensor_led": "on",
                    "plc_input_led": "off",
                    "online_monitor": "off",
                },
                "history": [],
            },
        )
        assert chat_reply["fallback_used"] is True
        assert "安全提醒" in chat_reply["safety_notice"]
        assert chat_reply["answer"]
        chat_ids = {item["id"] for item in chat_reply["highlighted_abilities"]}
        assert "sensor_wiring_judgement" in chat_ids
        assert chat_reply["tool_suggestions"]
        assert chat_reply["suggested_questions"]
        assert chat_reply["evidence_used"]
        assert chat_reply["reasoning_steps"]
        assert chat_reply["knowledge_refs"]
        assert chat_reply["next_questions"]
        assert chat_reply["student_graph"]["event_count"] >= 1
        assert chat_reply["learner_context"]["event_count"] >= 1

        student_after_chat = request_json("/api/graph/student?session_id=api-smoke-test")
        student_status = {item["id"]: item["status"] for item in student_after_chat["nodes"]}
        assert student_status["sensor_wiring_judgement"] in {"touched", "recommended_next", "weak"}

        gap_after_chat = request_json("/api/graph/gap?session_id=api-smoke-test&limit=3")
        assert gap_after_chat["graph_type"] == "student_job_gap"
        assert gap_after_chat["top_gaps"]
        assert "gap_score" in gap_after_chat["top_gaps"][0]

        device_state = request_json(
            "/api/student/device-state",
            {
                "session_id": "api-smoke-test",
                "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
                "sensor_led": "on",
                "plc_input_led": "off",
                "online_monitor": "off",
                "note": "api smoke 三联状态记录",
            },
        )
        assert device_state["saved"] is True
        assert "input_led_compare" in device_state["mapped_abilities"]

        device_events = request_json("/api/student/events?session_id=api-smoke-test&event_type=device_state_recorded")
        assert device_events["total"] >= 1

        input_led_evidence = request_json("/api/student/ability-evidence?session_id=api-smoke-test&ability_id=input_led_compare")
        assert input_led_evidence["event_count"] >= 1

        bootstrap_after_chat = request_json("/api/student/bootstrap?session_id=api-smoke-test")
        assert bootstrap_after_chat["learner_context"]["next_best_actions"]

        dashboard_after_chat = request_json("/api/student/dashboard?session_id=api-smoke-test")
        assert dashboard_after_chat["event_count"] >= 1
        assert dashboard_after_chat["immediate_focus"]
        assert dashboard_after_chat["evidence_summary"]["recent_events"]
        assert dashboard_after_chat["self_critique"]

        personalized_quiz = request_json(
            "/api/quiz/personalized",
            {
                "session_id": "api-smoke-test",
                "user_input": "传感器动作灯亮但 PLC 没输入，为什么？",
                "highlighted_abilities": chat_reply["highlighted_abilities"],
                "limit": 4,
            },
        )
        assert personalized_quiz["mode"] == "personalized"
        assert personalized_quiz["generation_mode"] == "knowledge_rule_template"
        assert 1 <= len(personalized_quiz["questions"]) <= 4
        assert personalized_quiz["questions"][0]["knowledge_id"].startswith("K")
        assert personalized_quiz["questions"][0]["ask_prompts"]
        assert personalized_quiz["preset_available"] is True

        explained_question = request_json(
            "/api/explain",
            {
                "session_id": "api-smoke-test",
                "type": "question",
                "question_id": personalized_quiz["questions"][0]["id"],
                "knowledge_id": personalized_quiz["questions"][0]["knowledge_id"],
                "ability_id": personalized_quiz["questions"][0]["ability_id"],
                "question": personalized_quiz["questions"][0]["question"],
                "selected_answer": "A",
                "event_type": "question_explained",
                "source": "api_smoke",
            },
        )
        assert explained_question["explain_type"] == "question"
        assert explained_question["explanation"]
        assert explained_question["evidence_used"]
        assert explained_question["reasoning_steps"]
        assert explained_question["ability_hits"]
        assert explained_question["knowledge_refs"]

        explained_ability = request_json(
            "/api/explain",
            {
                "session_id": "api-smoke-test",
                "type": "ability",
                "ability_id": "plc_input_common_terminal",
                "source": "api_smoke",
            },
        )
        assert explained_ability["explain_type"] == "ability"
        assert explained_ability["knowledge_refs"]
        assert explained_ability["task_refs"]

        scenarios = request_json("/api/scenarios")
        assert len(scenarios["scenarios"]) >= 4
        scenario_started = request_json(
            "/api/scenario/start",
            {
                "session_id": "api-smoke-test",
                "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
            },
        )
        assert scenario_started["status"] == "in_progress"
        assert scenario_started["current_step"]["options"]
        wrong_step = request_json(
            "/api/scenario/step",
            {
                "session_id": "api-smoke-test",
                "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
                "step_id": "S1",
                "choice_id": "B",
            },
        )
        assert wrong_step["is_correct"] is False
        assert wrong_step["current_step"]["id"] == "S1"
        wrong_graph_status = {item["id"]: item["status"] for item in wrong_step["student_graph"]["nodes"]}
        assert wrong_graph_status["electrical_safety_check"] == "weak"
        correct_step = request_json(
            "/api/scenario/step",
            {
                "session_id": "api-smoke-test",
                "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
                "step_id": "S1",
                "choice_id": "A",
            },
        )
        assert correct_step["is_correct"] is True
        assert correct_step["current_step"]["id"] == "S2"

        assist_clarify = request_json(
            "/api/assist",
            {
                "user_input": "传感器动作灯亮，但 PLC 输入点和在线监控都没有变化。",
                "context": {},
            },
        )
        assert assist_clarify["status"] == "need_clarification"
        assert "安全提醒" in assist_clarify["safety_notice"]
        assert 1 <= len(assist_clarify["clarifying_questions"]) <= 3

        assist_wiring = request_json(
            "/api/assist",
            {
                "user_input": "传感器动作灯亮，但 PLC 输入点和在线监控都没有变化。",
                "context": {
                    "sensor_led": "on",
                    "plc_input_led": "off",
                    "online_monitor": "off",
                    "sensor_type": "unknown",
                    "common_terminal": "unknown",
                },
            },
        )
        assert assist_wiring["status"] == "answered"
        wiring_ids = {item["id"] for item in assist_wiring["highlighted_abilities"]}
        assert "sensor_wiring_judgement" in wiring_ids
        assert "plc_input_common_terminal" in wiring_ids
        assert "plc_input_monitoring" in wiring_ids
        assert assist_wiring["direct_answer"]
        assert assist_wiring["knowledge_gaps"]
        assert assist_wiring["remediation_cards"]

        assist_mapping = request_json(
            "/api/assist",
            {
                "user_input": "PLC 输入灯亮，但在线监控地址不变化。",
                "context": {
                    "sensor_led": "on",
                    "plc_input_led": "on",
                    "online_monitor": "off",
                },
            },
        )
        mapping_ids = {item["id"] for item in assist_mapping["highlighted_abilities"]}
        assert "plc_io_address_mapping" in mapping_ids
        assert "program_variable_lookup" in mapping_ids

        assist_sensor = request_json(
            "/api/assist",
            {
                "user_input": "传感器动作灯不亮。",
                "context": {
                    "sensor_led": "off",
                },
            },
        )
        sensor_ids = {item["id"] for item in assist_sensor["highlighted_abilities"]}
        assert "sensor_type_identification" in sensor_ids
        assert "sensor_led_observation" in sensor_ids

        score = request_json(
            "/api/score",
            {
                "answers": {
                    "Q01": "B",
                    "Q02": "ABCD",
                    "Q03": "C",
                    "Q04": "ABCDE",
                    "Q05": "A,B,C,D,E,F",
                    "Q06": "A",
                    "Q07": "B",
                    "Q08": "A B C D",
                    "Q09": "A",
                    "Q10": "B",
                    "Q11": "A",
                    "Q12": "C",
                    "Q13": "ABCD",
                    "Q14": "B",
                    "Q15": "A,B,C,D,E,F",
                    "Q16": "B",
                    "Q17": "ABCD",
                    "Q18": "ABCD",
                    "Q19": "ABCD",
                    "Q20": "C",
                }
            },
        )
        assert score["score"] == 90
        assert score["weak_abilities"][0]["ability_id"] == "A02"

        diagnosis = request_json(
            "/api/diagnose",
            {
                "session_id": "api-smoke-test",
                "user_input": "传感器动作灯亮，但 PLC 输入点没有变化。",
                "answers": {
                    "Q01": "B",
                    "Q02": "ABCD",
                    "Q03": "C",
                    "Q04": "ABCDE",
                    "Q05": "A,B,C,D,E,F",
                    "Q06": "A",
                    "Q07": "B",
                    "Q08": "A B C D",
                    "Q09": "A",
                    "Q10": "B",
                    "Q11": "A",
                    "Q12": "C",
                    "Q13": "ABCD",
                    "Q14": "B",
                    "Q15": "A,B,C,D,E,F",
                    "Q16": "B",
                    "Q17": "ABCD",
                    "Q18": "ABCD",
                    "Q19": "ABCD",
                    "Q20": "C",
                },
            },
        )
        assert "安全提醒" in diagnosis["safety_notice"]
        assert diagnosis["score_result"]["score"] == 90
        assert diagnosis["job_profile"]["learner_stage"] == "职业新人"
        assert diagnosis["task_recommendations"]
        assert diagnosis["ability_graph"]["mermaid"].startswith("flowchart TD")
        assert diagnosis["student_graph"]["event_count"] >= 2

        student_after_diagnosis = request_json("/api/graph/student?session_id=api-smoke-test")
        diagnosis_status = {item["id"]: item["status"] for item in student_after_diagnosis["nodes"]}
        assert diagnosis_status["sensor_type_identification"] == "weak"

        explained = request_json(
            "/api/graph/student/event",
            {
                "session_id": "api-smoke-test",
                "event_type": "question_explained",
                "ability_id": "sensor_type_identification",
                "question_id": "Q001",
                "note": "学生请求讲解 NPN/PNP 题目",
                "source": "api_smoke",
            },
        )
        explained_status = {item["id"]: item["status"] for item in explained["student_graph"]["nodes"]}
        assert explained_status["sensor_type_identification"] == "improving"

        updates = request_json("/api/graph/updates?session_id=api-smoke-test")
        assert any(item["ability_id"] == "sensor_type_identification" for item in updates["updates"])

        mastered_feedback = request_json(
            "/api/feedback",
            {
                "session_id": "api-smoke-test",
                "feedback": "已掌握",
                "user_input": "请讲解 NPN/PNP。",
                "weak_abilities": [{"id": "sensor_type_identification", "name": "NPN/PNP 传感器类型识别"}],
                "recommended_path": ["NPN/PNP 传感器类型识别"],
            },
        )
        assert mastered_feedback["saved"] is True
        mastered_graph = request_json("/api/graph/student?session_id=api-smoke-test")
        mastered_status = {item["id"]: item["status"] for item in mastered_graph["nodes"]}
        assert mastered_status["sensor_type_identification"] in {"improving", "mastered"}

        proposals = request_json(
            "/api/graph/job/proposals",
            {
                "material": "企业岗位要求：新人需要能完成传感器 NPN/PNP 接线、PLC 输入公共端判断、在线监控和输入点无响应故障排查。",
                "source_type": "teacher_curated",
                "source": "api_smoke_material",
            },
        )
        assert proposals["proposals"]
        pending_job_graph = request_json("/api/graph/job")
        assert pending_job_graph["pending_proposals"]

        confirmed = request_json(
            "/api/graph/job/proposals/confirm",
            {
                "confirm_all": True,
                "confirmed_by": "api_smoke_teacher",
            },
        )
        assert confirmed["confirmed"] is True
        assert any(item["source_type"] == "teacher_confirmed_update" for item in confirmed["job_graph"]["demand_sources"])

        plan = request_json("/api/plan/personalized", {"session_id": "api-smoke-test"})
        assert 3 <= len(plan["learning_plan"]) <= 5
        assert plan["priority_abilities"]
        assert plan["learner_context"]["event_count"] >= 1
        assert plan["today_training_sheet"]["steps"]
        assert plan["today_training_sheet"]["estimated_minutes"] >= 20
        assert len(plan["seven_day_plan"]) == 7
        assert plan["learning_plan"][0]["knowledge_cards"]
        assert "video_resources" in plan["learning_plan"][0]
        assert "practice_tasks" in plan["learning_plan"][0]
        assert "checkpoint_questions" in plan["learning_plan"][0]

        today_plan = request_json("/api/plan/personalized", {"session_id": "api-smoke-test", "plan_mode": "today"})
        assert today_plan["plan_mode"] == "today"
        assert today_plan["today_training_sheet"]["title"] == "今日训练单"

        seven_day_plan = request_json("/api/plan/personalized", {"session_id": "api-smoke-test", "plan_mode": "7_day"})
        assert seven_day_plan["plan_mode"] == "7_day"
        assert len(seven_day_plan["seven_day_plan"]) == 7

        feedback = request_json(
            "/api/feedback",
            {
                "session_id": "api-smoke-test",
                "feedback": "仍不会",
                "user_input": "传感器动作灯亮，但 PLC 输入点没有变化。",
                "score_result": diagnosis["score_result"],
                "weak_abilities": diagnosis["weak_abilities"],
                "recommended_path": diagnosis["recommended_path"],
            },
        )
        assert feedback["saved"] is True

        summary = request_json("/api/teacher/summary")
        assert summary["session_count"] >= 1
        assert summary["feedback_counts"].get("仍不会", 0) >= 1

    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        if session_file.exists():
            session_file.unlink()
        for path, content in runtime_backups.items():
            if content is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_text(content, encoding="utf-8")

    print("api_smoke.test.py passed")


if __name__ == "__main__":
    main()
