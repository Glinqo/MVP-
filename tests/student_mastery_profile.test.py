"""
Focused regression test for the upgraded personal ability graph.

It validates the path:
diagnostic actions -> diagnostic trace -> four-dimensional mastery profile
-> student graph node fields -> student/job gap API service.
"""

import sys
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.diagnostic_trace import list_student_traces
from app.services.graph import build_student_ability_graph, build_student_job_gap
from app.services.scenario import action_scenario
from app.services.student_mastery_profile import build_student_mastery_profile


SESSION = "test-student-mastery-profile"
SCENARIO = "SCN_SENSOR_LED_ON_PLC_LED_OFF"
GRAPH_EVENTS_FILE = ROOT / "data" / "graph_update_events.json"


def cleanup():
    session_file = ROOT / "data" / "sessions" / f"{SESSION}.json"
    if session_file.exists():
        session_file.unlink()
    if GRAPH_EVENTS_FILE.exists():
        data = json.loads(GRAPH_EVENTS_FILE.read_text(encoding="utf-8"))
        events = data.get("events", [])
        filtered = [event for event in events if event.get("session_id") != SESSION]
        if len(filtered) != len(events):
            data["events"] = filtered
            GRAPH_EVENTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def seed_diagnostic_trace():
    for action_id in ["CHECK_SAFETY", "CHECK_COMMON_TERMINAL", "VERIFY_TRIPLE_STATE"]:
        result = action_scenario({
            "session_id": SESSION,
            "scenario_id": SCENARIO,
            "action_id": action_id,
        })
        assert result["action_id"] == action_id


def node_by_id(graph, ability_id):
    for node in graph.get("nodes", []):
        if node.get("id") == ability_id:
            return node
    raise AssertionError(f"missing graph node: {ability_id}")


def assert_score(value, label):
    assert isinstance(value, int), f"{label} should be integer, got {type(value)}"
    assert 0 <= value <= 100, f"{label} out of range: {value}"


def test_trace_to_mastery_profile():
    seed_diagnostic_trace()

    traces = list_student_traces(SESSION)
    assert traces
    assert any(trace.get("events") for trace in traces)
    assert any(trace.get("activities") for trace in traces)

    graph = build_student_ability_graph(SESSION)
    assert graph["graph_type"] == "student_ability"
    assert graph["mastery_profile"]["trace_count"] >= 1
    assert graph["mastery_profile"]["aggregated_process_metrics"]

    safety_node = node_by_id(graph, "electrical_safety_check")
    for key in [
        "knowledge_mastery",
        "procedure_mastery",
        "transfer_score",
        "safety_score",
        "cognitive_mastery_score",
    ]:
        assert_score(safety_node[key], key)

    assert "uncertainty" in safety_node
    assert 0 <= safety_node["uncertainty"] <= 1
    assert safety_node["process_metrics"]
    assert safety_node["safety_gate"]
    assert safety_node["recommended_intervention"]
    assert safety_node["why_next"]
    assert safety_node["normalized_events"] or safety_node["process_evidence"]

    profile = build_student_mastery_profile(SESSION, graph["nodes"])
    assert profile["abilities"]["electrical_safety_check"]["cognitive_mastery_score"] == safety_node["cognitive_mastery_score"]
    print(
        "  PASS: electrical_safety_check",
        safety_node["knowledge_mastery"],
        safety_node["procedure_mastery"],
        safety_node["transfer_score"],
        safety_node["safety_score"],
        safety_node["cognitive_mastery_score"],
    )


def test_student_job_gap_uses_cognitive_mastery():
    gap = build_student_job_gap(SESSION, limit=5)
    assert gap["graph_type"] == "student_job_gap"
    assert gap["top_gaps"]
    first = gap["top_gaps"][0]
    for key in ["ability_id", "ability_name", "student_mastery", "uncertainty", "gap_score", "next_best_action"]:
        assert key in first
    assert 0 <= first["student_mastery"] <= 100
    print(f"  PASS: gap top={first['ability_id']} score={first['gap_score']}")


def main():
    print("=== Student mastery profile ===")
    test_trace_to_mastery_profile()

    print("\n=== Student/job gap ===")
    test_student_job_gap_uses_cognitive_mastery()

    print("\n=== ALL STUDENT MASTERY PROFILE TESTS PASSED ===")


if __name__ == "__main__":
    try:
        cleanup()
        main()
    finally:
        cleanup()
