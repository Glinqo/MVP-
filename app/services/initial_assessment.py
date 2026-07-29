"""
Initial student assessment engine. Stage 1 (deepened).
Evaluates baseline abilities on first entry via structured questions.
Integrates with ability_state_engine, learning_event_store, and student_mastery_profile.

Features:
- State tracking (not_started, in_progress, completed)
- Per-job-role isolation
- Resumable progress
- Question ID validation
- Duplicate answer prevention
- Per-question learning events
- Safety dimension scoring
- Idempotency guard
- Proper error responses
"""
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from app.services.ability_state_engine import compute_ability_state
from app.services.learning_event_store import append_normalized_event
from app.services.assessment_store import load_state, save_state, list_sessions as list_assessment_sessions

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = ROOT / "knowledge" / "assessment_questions.json"
ABILITY_NODES_PATH = ROOT / "knowledge" / "ability_nodes.json"

CORRECT_SCORE = 1.0
PARTIAL_SCORE = 0.5
INCORRECT_SCORE = 0.0

WEAK_THRESHOLD = 0.5
STRONG_THRESHOLD = 0.8
SAFETY_ABILITY_IDS = {"electrical_safety", "safety_ppe", "emergency_stop"}

# In-memory assessment session store (resets on server restart)
_sessions: Dict[str, Dict[str, Any]] = {}


@dataclass
class AssessmentQuestion:
    qid: str
    ability_id: str
    ability_label: str
    dimension: str
    text: str
    options: List[Dict[str, str]]
    correct_key: str
    difficulty: str = "medium"
    explanation: str = ""


@dataclass
class AssessmentResult:
    session_id: str
    job_role: str
    completed_at: str
    answers: List[Dict] = field(default_factory=list)
    ability_scores: Dict[str, float] = field(default_factory=dict)
    weak_abilities: List[str] = field(default_factory=list)
    strong_abilities: List[str] = field(default_factory=list)
    safety_critical_gaps: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    total_score: float = 0.0
    dimension_scores: Dict[str, float] = field(default_factory=dict)


def _load_questions(job_role: str = None) -> List[AssessmentQuestion]:
    """Load assessment questions from JSON, optionally filtered by job role."""
    if not QUESTIONS_PATH.exists():
        logger.error("Assessment questions file not found: %s", QUESTIONS_PATH)
        return []
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    questions = []
    for item in data.get("questions", []):
        q = AssessmentQuestion(
            qid=item["qid"],
            ability_id=item["ability_id"],
            ability_label=item.get("ability_label", ""),
            dimension=item.get("dimension", ""),
            text=item["text"],
            options=item["options"],
            correct_key=item["correct_key"],
            difficulty=item.get("difficulty", "medium"),
            explanation=item.get("explanation", ""),
        )
        if job_role is None or item.get("job_role") in (None, job_role):
            questions.append(q)
    return questions


def _build_qid_map(questions: List[AssessmentQuestion]) -> Dict[str, AssessmentQuestion]:
    """Build qid -> question lookup map."""
    return {q.qid: q for q in questions}


def _init_session(session_id: str, job_role: str = None) -> Dict[str, Any]:
    """Initialize or retrieve a session's assessment state from persistent store.
    Falls back to memory cache if persistence is unavailable."""
    key = f"{session_id}_{job_role or 'default'}"
    # Try persistent store first
    try:
        stored = load_state(session_id, job_role)
        if stored and stored.get("state") != "not_started":
            _sessions[key] = stored
            return _sessions[key]
    except Exception:
        logger.debug("Assessment store unavailable, using memory fallback")
    # Memory fallback
    if key not in _sessions:
        _sessions[key] = {
            "id": key,
            "session_id": session_id,
            "job_role": job_role or "default",
            "state": "not_started",
            "answers": [],
            "result": None,
            "completed": False,
            "created_at": time.time(),
            "assessment_id": f"ASSESS-{session_id}-{int(time.time())}",
            "assessment_version": "1.0.0",
        }
    return _sessions[key]


def start_assessment(session_id: str, job_role: str = None) -> Dict[str, Any]:
    """
    Start or resume an assessment session. Returns the first unanswered question.

    Returns: {
        "session_id": str, "status": str, "total_questions": int,
        "dimensions": [str, ...], "first_question" / "next_question": {...},
        "current_index": int, "answered_count": int, "state": str
    }
    """
    if not session_id:
        return {"error": "session_id is required", "session_id": ""}

    questions = _load_questions(job_role)
    if not questions:
        return {"error": "No assessment questions available", "session_id": session_id}

    session = _init_session(session_id, job_role)

    if session.get("completed"):
        return {
            "session_id": session_id,
            "status": "completed",
            "state": "completed",
            "message": "Assessment already completed for this job role.",
            "total_questions": len(questions),
            "answered_count": len(session.get("answers", [])),
            "dimensions": list(dict.fromkeys(q.dimension for q in questions)),
        }

    answered_qids = {a["qid"] for a in session.get("answers", [])}
    dimensions = list(dict.fromkeys(q.dimension for q in questions))

    # Find the first unanswered question
    first_unanswered = None
    first_idx = 0
    for idx, q in enumerate(questions):
        if q.qid not in answered_qids:
            first_unanswered = q
            first_idx = idx
            break

    if first_unanswered is None:
        return {
            "session_id": session_id,
            "status": "completed",
            "state": "completed",
            "message": "All questions have been answered.",
            "total_questions": len(questions),
            "answered_count": len(answered_qids),
            "dimensions": dimensions,
        }

    session["state"] = "in_progress"

    return {
        "session_id": session_id,
        "status": "in_progress",
        "state": "in_progress",
        "total_questions": len(questions),
        "dimensions": dimensions,
        "first_question": {
            "qid": first_unanswered.qid,
            "ability_id": first_unanswered.ability_id,
            "ability_label": first_unanswered.ability_label,
            "dimension": first_unanswered.dimension,
            "text": first_unanswered.text,
            "options": first_unanswered.options,
            "difficulty": first_unanswered.difficulty,
        },
        "current_index": first_idx,
        "answered_count": len(answered_qids),
    }


def submit_answer(
    session_id: str,
    qid: str,
    selected_key: str,
    job_role: str = None,
) -> Dict[str, Any]:
    """
    Submit an answer and return either the next question or the final result.

    Validates: session_id, qid, duplicate prevention, idempotent completion.
    Writes per-question learning events.

    Returns either: { "status": "in_progress", "next_question": {...}, ... }
              or:   { "status": "completed", "result": AssessmentResult, ... }
              or:   { "error": str, "session_id": str }
    """
    if not session_id:
        return {"error": "session_id is required", "session_id": ""}
    if not qid or not selected_key:
        return {"error": "qid and selected_key are required", "session_id": session_id}

    questions = _load_questions(job_role)
    if not questions:
        return {"error": "No questions loaded", "session_id": session_id}

    session = _init_session(session_id, job_role)
    q_map = _build_qid_map(questions)

    # Validate question ID
    target_q = q_map.get(qid)
    if target_q is None:
        return {"error": f"Invalid question ID: {qid}", "session_id": session_id}

    # Validate selected_key is a valid option
    valid_keys = {o["key"] for o in target_q.options}
    if selected_key not in valid_keys:
        return {
            "error": f"Invalid answer key: {selected_key}. Valid: {sorted(valid_keys)}",
            "session_id": session_id,
        }

    # Use ONLY persisted answers as source of truth — never accept client answers_so_far
    answers = list(session.get("answers", []))

    # Prevent duplicate submission for the same qid
    answered_qids = {a.get("qid", a.get("question_id", "")) for a in answers}
    if qid in answered_qids:
        # Return current state without re-counting — force_complete is NOT supported
        if len(answers) >= len(questions):
            return _finish_assessment(session_id, job_role, answers, questions)
        next_idx = len(answers)
        if next_idx >= len(questions):
            return _finish_assessment(session_id, job_role, answers, questions)
        nq = questions[next_idx]
        return {
            "session_id": session_id,
            "status": "in_progress",
            "message": f"Question {qid} already answered. Moving to next.",
            "next_question": {
                "qid": nq.qid, "ability_id": nq.ability_id,
                "ability_label": nq.ability_label, "dimension": nq.dimension,
                "text": nq.text, "options": nq.options, "difficulty": nq.difficulty,
            },
            "current_index": next_idx,
            "total_questions": len(questions),
            "answered_count": len(answers),
        }

    # Record the answer
    answer_entry = {"qid": qid, "selected": selected_key, "correct": target_q.correct_key,
                    "is_correct": selected_key == target_q.correct_key,
                    "ability_id": target_q.ability_id, "dimension": target_q.dimension,
                    "answered_at": time.time()}
    answers.append(answer_entry)

    # Write per-question learning event — MUST succeed before saving
    event_ok = _write_answer_event(session_id, session, target_q, answer_entry)
    if not event_ok:
        # Rollback: do NOT save answer, do NOT increment count, do NOT advance
        answers.pop()  # remove the answer we just appended
        return {
            "session_id": session_id,
            "status": "error",
            "error": "Failed to persist learning event for this answer. Please retry.",
            "answered_count": len(answers),
            "total_questions": len(questions),
        }

    # Update session state and persist
    session["answers"] = answers
    session["state"] = "in_progress"
    try:
        save_state(session)
    except Exception:
        logger.debug("Save state skipped (store unavailable)")

    current_index = len(answers)
    if current_index >= len(questions):
        session["completed"] = True
        session["state"] = "completed"
        return _finish_assessment(session_id, job_role, answers, questions)

    next_q = questions[current_index]
    return {
        "session_id": session_id,
        "status": "in_progress",
        "next_question": {
            "qid": next_q.qid,
            "ability_id": next_q.ability_id,
            "ability_label": next_q.ability_label,
            "dimension": next_q.dimension,
            "text": next_q.text,
            "options": next_q.options,
            "difficulty": next_q.difficulty,
        },
        "current_index": current_index,
        "total_questions": len(questions),
        "answered_count": len(answers),
    }


def _write_answer_event(session_id, session, question, answer_entry):
    """Write a learning event for a single answered question.
    Returns True on success, False on failure. Does NOT swallow exceptions silently."""
    assessment_id = session.get("assessment_id", f"ASSESS-{session_id}")
    event = {
        "session_id": session_id,
        "event_type": "initial_quiz_answered",
        "assessment_id": assessment_id,
        "question_id": question.qid,
        "ability_id": question.ability_id,
        "selected_key": answer_entry["selected"],
        "correct_key": question.correct_key,
        "is_correct": answer_entry["is_correct"],
        "dimension": question.dimension,
        "difficulty": question.difficulty,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        append_normalized_event(session_id, event)
        return True
    except Exception as e:
        logger.warning("Failed to write answer event for qid=%s: %s", question.qid, e)
        return False


def _finish_assessment(
    session_id: str,
    job_role: str,
    answers: List[Dict],
    questions: List[AssessmentQuestion],
) -> Dict[str, Any]:
    """Complete the assessment, compute multi-dimensional scores, and return results."""
    session = _init_session(session_id, job_role)

    # Idempotency guard: only compute once
    if session.get("_result_cached"):
        return session["_result_cached"]

    q_map = _build_qid_map(questions)

    ability_answers: Dict[str, List[float]] = {}
    ability_labels: Dict[str, str] = {}
    dimension_scores: Dict[str, List[float]] = {}

    for ans in answers:
        q = q_map.get(ans.get("qid", ans.get("question_id", "")))
        if q is None:
            continue
        aid = q.ability_id
        if aid not in ability_answers:
            ability_answers[aid] = []
            ability_labels[aid] = q.ability_label

        score = CORRECT_SCORE if ans.get("is_correct") or ans.get("selected") == q.correct_key else INCORRECT_SCORE
        ability_answers[aid].append(score)

        dim = q.dimension
        if dim not in dimension_scores:
            dimension_scores[dim] = []
        dimension_scores[dim].append(score)

    # Per-ability scores
    ability_scores = {}
    for aid, scores in ability_answers.items():
        ability_scores[aid] = sum(scores) / len(scores) if scores else 0.0

    # Per-dimension scores
    dim_scores = {}
    for dim, scores in dimension_scores.items():
        dim_scores[dim] = sum(scores) / len(scores) if scores else 0.0

    # Weak/strong identification
    weak = [aid for aid, s in ability_scores.items() if s < WEAK_THRESHOLD]
    strong = [aid for aid, s in ability_scores.items() if s >= STRONG_THRESHOLD]

    # Safety-critical gap identification
    safety_gaps = [aid for aid in weak if aid in SAFETY_ABILITY_IDS]
    if not safety_gaps:
        weak_safety = [aid for aid, s in ability_scores.items() if aid in SAFETY_ABILITY_IDS and s < 0.7]
        safety_gaps = weak_safety

    # Recommendations
    recommendations = []
    if safety_gaps:
        recommendations.append("WARNING: Safety knowledge gaps detected. Prioritize safety training before hands-on practice.")
        for gap in safety_gaps:
            recommendations.append(f"Complete mandatory safety module: {ability_labels.get(gap, gap)}")
    for aid in weak:
        label = ability_labels.get(aid, aid)
        if aid not in safety_gaps:
            recommendations.append(f"Strengthen {label} through targeted learning")
    if not weak:
        recommendations.append("All assessment areas passed. Ready for scenario-based training.")
    if strong:
        strong_labels = [ability_labels.get(a, a) for a in strong[:3]]
        recommendations.append(f"Strong areas to build upon: {', '.join(strong_labels)}")

    total_score = sum(ability_scores.values()) / len(ability_scores) if ability_scores else 0.0

    result_data = {
        "total_score": round(total_score, 2),
        "ability_scores": ability_scores,
        "dimension_scores": dim_scores,
        "weak_abilities": weak,
        "strong_abilities": strong,
        "safety_critical_gaps": safety_gaps,
        "recommendations": recommendations,
        "next_steps": [
            "Review your ability graph to understand current baseline",
            "Start recommended learning path for weak areas",
            "Complete safety training before hands-on practice" if safety_gaps else "Proceed to scenario training",
        ],
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_id": session_id,
        "job_role": job_role or "unknown",
        "answered_count": len(answers),
        "total_questions": len(questions),
    }

    # Persist result for SQLite storage (so plan route can read it)
    session["result"] = result_data
    # Cache result for idempotency
    try:
        save_state(session)
    except Exception:
        logger.debug("Save state skipped (store unavailable)")
    session["_result_cached"] = {
        "session_id": session_id,
        "status": "completed",
        "state": "completed",
        "result": result_data,
        "total_questions": len(questions),
        "answered_count": len(answers),
    }

    return session["_result_cached"]


def get_assessment_summary(session_id: str, job_role: str = None) -> Dict[str, Any]:
    """Retrieve assessment state for a session, including progress and recommendations."""
    questions = _load_questions(job_role)
    session = _init_session(session_id, job_role)

    state = session.get("state", "not_started")
    answered = len(session.get("answers", []))

    summary = {
        "session_id": session_id,
        "state": state,
        "job_role": job_role or session.get("job_role"),
        "available_dimensions": list(dict.fromkeys(q.dimension for q in questions)),
        "total_questions_available": len(questions),
        "answered_count": answered,
        "progress_pct": round(answered / len(questions) * 100, 1) if questions else 0,
        "completed": session.get("completed", False),
    }

    if state == "not_started":
        summary["message"] = "Assessment not yet started. Call POST /api/student/assess/start to begin."
    elif state == "in_progress":
        summary["message"] = f"Assessment in progress: {answered}/{len(questions)} questions answered."
    elif state == "completed":
        summary["message"] = "Assessment completed. Review results and begin personalized learning."
        cached = session.get("_result_cached", {})
        if cached:
            summary["result_summary"] = {
                "total_score": cached.get("result", {}).get("total_score"),
                "weak_count": len(cached.get("result", {}).get("weak_abilities", [])),
                "strong_count": len(cached.get("result", {}).get("strong_abilities", [])),
                "safety_gaps": len(cached.get("result", {}).get("safety_critical_gaps", [])),
            }

    return summary
