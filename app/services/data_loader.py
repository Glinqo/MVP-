import json
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_json(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_data():
    ability_data = read_json("knowledge/ability_nodes.json")
    job_profiles_data = read_json("knowledge/job_profiles.json")
    industry_demand_data = read_json("knowledge/industry_demand_snapshots.json")
    problem_patterns_data = read_json("knowledge/problem_patterns.json")
    troubleshooting_scenarios_data = read_json("knowledge/troubleshooting_scenarios.json")
    knowledge_data = read_json("knowledge/knowledge_50.json")
    resources_data = read_json("knowledge/resources.json")
    tasks_data = read_json("knowledge/training_tasks.json")
    errors_data = read_json("knowledge/common_errors.json")
    questions_data = read_json("diagnosis/diagnostic_questions.json")
    rules_data = read_json("diagnosis/scoring_rules.json")

    abilities = ability_data.get("nodes", [])
    knowledge = knowledge_data.get("items", [])
    resources = resources_data.get("resources", [])
    tasks = tasks_data.get("tasks", [])

    return {
        "root": ROOT,
        "ability_data": ability_data,
        "job_profiles_data": job_profiles_data,
        "industry_demand_data": industry_demand_data,
        "problem_patterns_data": problem_patterns_data,
        "troubleshooting_scenarios_data": troubleshooting_scenarios_data,
        "knowledge_data": knowledge_data,
        "resources_data": resources_data,
        "tasks_data": tasks_data,
        "errors_data": errors_data,
        "questions_data": questions_data,
        "rules_data": rules_data,
        "abilities": abilities,
        "job_profiles": job_profiles_data.get("profiles", []),
        "industry_demand_snapshots": industry_demand_data.get("snapshots", []),
        "problem_patterns": problem_patterns_data.get("patterns", []),
        "troubleshooting_scenarios": troubleshooting_scenarios_data.get("scenarios", []),
        "knowledge": knowledge,
        "resources": resources,
        "tasks": tasks,
        "ability_by_id": {item.get("id"): item for item in abilities},
        "job_profile_by_id": {item.get("id"): item for item in job_profiles_data.get("profiles", [])},
        "knowledge_by_id": {item.get("id"): item for item in knowledge},
        "resource_by_id": {item.get("id"): item for item in resources},
        "task_by_id": {item.get("id"): item for item in tasks},
    }


def primary_job_profile():
    profiles = load_data()["job_profiles"]
    return profiles[0] if profiles else {}


def public_questions():
    questions = []
    for question in load_data()["questions_data"].get("questions", []):
        questions.append(
            {
                "id": question.get("id"),
                "type": question.get("type"),
                "question": question.get("question"),
                "options": question.get("options", []),
                "ability_id": question.get("ability_id"),
                "remediation_resources": question.get("remediation_resources", []),
                "remediation_tasks": question.get("remediation_tasks", []),
                "source": question.get("source"),
            }
        )
    return questions

def job_profile_by_id(profile_id=None):
    """Return a job profile by id, or the primary profile if id is None."""
    profiles = load_data()["job_profiles"]
    if not profile_id:
        return profiles[0] if profiles else {}
    by_id = load_data()["job_profile_by_id"]
    return by_id.get(profile_id, profiles[0] if profiles else {})
