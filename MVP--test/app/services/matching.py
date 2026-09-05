# -*- coding: utf-8 -*-
"""Student-Job matching service.
Calculates readiness score and gap analysis between student and job requirements.
Formula from research report:
  Readiness = sum(Weight_i * SkillLevel_i * Confidence_i) / sum(Weight_i)
  FitScore = 0.45 * Coverage + 0.35 * Readiness - 0.20 * CriticalGapPenalty
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.graph import (
    build_student_ability_graph,
    build_job_ability_graph,
    CORE_CHAIN
)
from app.services.data_loader import load_data

# Critical abilities that incur penalty if weak
CRITICAL_ABILITIES = {
    "electrical_safety_check": "电气安全不能薄弱",
    "power_isolation_confirmation": "断电隔离不能薄弱",
    "input_no_response_fault_scope": "排故能力不能薄弱",
}


def student_ability_map(session_id):
    """Build {ability_id: {mastery_score, confidence}} from student graph"""
    graph = build_student_ability_graph(session_id)
    result = {}
    for node in graph.get("nodes", []):
        aid = node.get("id")
        if not aid:
            continue
        result[aid] = {
            "mastery_score": float(node.get("mastery_score", 0) or 0),
            "confidence": float(node.get("confidence", 0.5) or 0.5),
            "status": node.get("status", "unknown"),
        }
    return result


def job_ability_map():
    """Build {ability_id: {weight, name}} from job graph"""
    graph = build_job_ability_graph()
    result = {}
    for node in graph.get("nodes", []):
        aid = node.get("id")
        if not aid:
            continue
        result[aid] = {
            "weight": float(node.get("demand_weight", 1.0) or 1.0),
            "name": node.get("name") or node.get("label") or aid,
            "status": node.get("status", "core"),
        }
    return result


def compute_match(session_id):
    """Compute student-job match scores"""
    student = student_ability_map(session_id)
    job = job_ability_map()
    data = load_data()
    ability_index = data.get("ability_by_id", {})

    weighted_sum = 0.0
    total_weight = 0.0
    covered_count = 0
    total_required = len(job)
    critical_penalty = 0.0
    gaps = []

    for aid, req in job.items():
        weight = req["weight"]
        total_weight += weight

        if aid in student:
            stu = student[aid]
            mastery = stu["mastery_score"]
            conf = stu["confidence"]
            covered_count += 1
            weighted_sum += weight * mastery * conf

            if aid in CRITICAL_ABILITIES and mastery < 0.4:
                critical_penalty += 0.15
                gaps.append({
                    "ability_id": aid,
                    "name": req["name"],
                    "type": "critical_gap",
                    "reason": CRITICAL_ABILITIES[aid],
                    "mastery": mastery,
                })
            elif mastery < 0.3:
                gaps.append({
                    "ability_id": aid,
                    "name": req["name"],
                    "type": "weak",
                    "reason": "掌握度低",
                    "mastery": mastery,
                })
        else:
            if aid in CRITICAL_ABILITIES:
                critical_penalty += 0.2
                gaps.append({
                    "ability_id": aid,
                    "name": req["name"],
                    "type": "critical_missing",
                    "reason": CRITICAL_ABILITIES[aid],
                    "mastery": 0,
                })
            else:
                gaps.append({
                    "ability_id": aid,
                    "name": req["name"],
                    "type": "missing",
                    "reason": "尚无学习证据",
                    "mastery": 0,
                })

    readiness = weighted_sum / max(total_weight, 0.01)
    coverage = covered_count / max(total_required, 1)
    critical_penalty = min(critical_penalty, 0.8)
    fit_score = max(0, min(1, 0.45 * coverage + 0.35 * readiness - 0.20 * critical_penalty))

    # Determine level
    if fit_score >= 0.8:
        level = "接近达标"
    elif fit_score >= 0.5:
        level = "需要补强"
    else:
        level = "差距较大"

    gaps.sort(key=lambda x: (0 if "critical" in x["type"] else 1, x["mastery"]))

    return {
        "fit_score": round(fit_score * 100, 1),
        "readiness": round(readiness * 100, 1),
        "coverage": round(coverage * 100, 1),
        "level": level,
        "critical_penalty": round(critical_penalty * 100, 1),
        "total_required": total_required,
        "covered": covered_count,
        "gaps": gaps[:8],
        "student_ability_count": len(student),
    }