"""V2 API Facade - unified entry point for all V2 engines.

server.py -> V2Facade -> Engine
Never let server.py directly access engine internals.
"""

import json
from typing import Any, Dict, List, Optional

# --- Evidence ---
def emit_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.evidence.event_bus import get_event_bus
    bus = get_event_bus()
    ok = bus.emit_raw(raw, raw.get("idempotency_key", ""))
    return {"ok": ok, "event_id": raw.get("event_id", "")}

def get_events(student_id: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    from app.services.evidence.event_query import EventQuery
    q = EventQuery()
    return q.by_student(student_id, limit) if student_id else []

def get_event_count(student_id: str = "") -> int:
    from app.services.evidence.event_query import EventQuery
    q = EventQuery()
    return q.event_count(student_id) if student_id else q.total_events()


def _candidate_session_ids(username: str, job_role: str = "") -> List[str]:
    from app.services.class_management import canonical_student_session_id
    candidates = []
    if job_role:
        candidates.append(canonical_student_session_id(username, job_role))
    candidates.extend([f"{username}-session", username])

    seen = set()
    ordered = []
    for sid in candidates:
        if sid and sid not in seen:
            seen.add(sid)
            ordered.append(sid)
    return ordered


def _state_from_ability_engine(username: str, job_role: str = "") -> Dict[str, Any]:
    from app.services.ability_state_engine import compute_ability_state

    best_state = None
    best_session_id = ""
    best_evidence_count = -1

    for session_id in _candidate_session_ids(username, job_role):
        try:
            state = compute_ability_state(session_id)
        except Exception:
            continue
        abilities = state.get("abilities", {}) if state else {}
        evidence_count = sum(
            int((ability.get("evidence_summary") or {}).get("total_evidence") or 0)
            for ability in abilities.values()
            if isinstance(ability, dict)
        )
        if evidence_count > best_evidence_count:
            best_state = state
            best_session_id = session_id
            best_evidence_count = evidence_count

    if not best_state:
        return {"student_id": username, "job_role": job_role, "abilities": {}, "event_count": 0}

    abilities_out = {}
    for ability_id, ability in (best_state.get("abilities") or {}).items():
        if not isinstance(ability, dict):
            continue
        score = ability.get("cognitive_mastery_score")
        try:
            mastery = max(0.0, min(1.0, float(score or 0) / 100.0))
        except (TypeError, ValueError):
            mastery = 0.0
        abilities_out[ability_id] = {
            **ability,
            "student_id": username,
            "mastery": mastery,
        }

    return {
        "student_id": username,
        "session_id": best_state.get("session_id") or best_session_id,
        "job_role": job_role,
        "abilities": abilities_out,
        "event_count": max(best_evidence_count, 0),
    }

# --- Learner State ---
def get_student_state(student_id: str, job_role: str = "") -> Dict[str, Any]:
    from app.services.state.learner_state import LearnerState
    state = LearnerState(student_id=student_id, job_role=job_role)
    return state.to_dict()

def get_ability_state(student_id: str, ability_id: str) -> Dict[str, Any]:
    state = LearnerState(student_id=student_id)
    a = state.get_ability(ability_id)
    return a.to_dict() if a else {"ability_id": ability_id, "status": "unknown"}

# --- Process Diagnosis ---
def get_student_patterns(student_id: str, scenario_id: str = "",
                         limit: int = 20) -> List[Dict[str, Any]]:
    from app.services.diagnosis.diagnostic_patterns import PatternClassifier
    from app.services.diagnosis.expert_graph import get_expert_graph
    from app.services.evidence.event_query import EventQuery
    g = get_expert_graph(scenario_id or "SCN_SENSOR_LED_ON_PLC_LED_OFF")
    pc = PatternClassifier(g)
    q = EventQuery()
    events = q.by_student(student_id, limit)
    if not events:
        return []
    patterns = []
    for ev in events:
        sid = ev.get("state_id", "") or ev.get("current_state", "")
        aid = ev.get("action_id", "") or ev.get("action", "")
        if not sid or not aid:
            continue
        hist = [h.get("action_id", "") for h in ev.get("history", []) if isinstance(h, dict)]
        pat = pc.classify(sid, aid, hist, student_id, scenario_id)
        if pat:
            patterns.append(pat.to_dict())
    return patterns

def classify_scenario_action(student_id: str, state_id: str, action_id: str,
                              scenario_id: str = "", history: List[str] = None) -> Optional[Dict[str, Any]]:
    from app.services.diagnosis.diagnostic_patterns import PatternClassifier
    from app.services.diagnosis.expert_graph import get_expert_graph
    g = get_expert_graph(scenario_id or "SCN_SENSOR_LED_ON_PLC_LED_OFF")
    pc = PatternClassifier(g)
    pat = pc.classify(state_id, action_id, history or [], student_id, scenario_id)
    return pat.to_dict() if pat else None

# --- Teaching Issue ---
def discover_issues(job_role: str = "", student_states: List[Dict] = None,
                    patterns: List[Dict] = None, class_id: int = None,
                    teacher_id: int = None) -> List[Dict[str, Any]]:
    from app.services.issues.issue_discovery import IssueDiscoveryEngine
    # P6-B: No silent demo fallback. If no class scope is provided, return empty.
    if not class_id or not teacher_id:
        return []
    from app.services.class_management import get_class_students
    cls = get_class_students(class_id, teacher_id)
    if not cls:
        return []
    effective_job_role = job_role or cls.get("job_role", "")
    try:
        from app.services.graph import build_job_ability_graph
        job_graph = build_job_ability_graph(effective_job_role)
    except Exception:
        job_graph = {}
    engine = IssueDiscoveryEngine(job_graph)
    class_student_ids = [s["username"] for s in cls.get("students", [])]
    if not student_states:
        student_states = []
        for sid in class_student_ids:
            try:
                student_states.append(_state_from_ability_engine(sid, effective_job_role))
            except Exception:
                pass
    if not patterns:
        from app.services.diagnosis.diagnostic_patterns import PatternClassifier
        from app.services.diagnosis.expert_graph import get_expert_graph
        from app.services.evidence.event_query import EventQuery
        patterns = []
        try:
            g = get_expert_graph("SCN_PLC_INPUT_NO_RESPONSE")
            pc = PatternClassifier(g)
            q2 = EventQuery()
            for sid in class_student_ids:
                events = q2.by_student(sid, limit=30)
                for ev in (events or []):
                    sid2 = ev.get("state_id", "") or ev.get("current_state", "")
                    aid = ev.get("action_id", "") or ev.get("action", "")
                    if sid2 and aid:
                        try:
                            pat = pc.classify(sid2, aid, [], sid, ev.get("scenario_id", ""))
                            if pat: patterns.append(pat.to_dict())
                        except Exception:
                            pass
        except Exception:
            pass
    issues = engine.discover_from_states(
        student_states or [],
        patterns or [],
        total_students=max(len(class_student_ids), 1),
    )

    # P10.2-A: Enrich each issue with evidence summary and top patterns
    enriched = []
    state_by_student = {s.get("student_id"): s for s in (student_states or [])}
    for issue in issues:
        d = issue.to_dict()
        affected = d.get("affected_students", []) or []
        # Aggregate patterns for affected students
        pattern_counts = {}
        pattern_students = {}
        total_events = 0
        for sid in affected:
            student_patterns = get_student_patterns(sid, limit=50)
            total_events += int((state_by_student.get(sid) or {}).get("event_count") or 0)
            total_events += len(get_events(sid, limit=100))
            for p in student_patterns:
                pid = p.get("pattern_id") or p.get("pattern_name") or p.get("name") or p.get("type") or "unknown"
                label = p.get("label") or p.get("pattern_name") or p.get("name") or str(pid)
                pattern_counts[label] = pattern_counts.get(label, 0) + 1
                if label not in pattern_students:
                    pattern_students[label] = set()
                pattern_students[label].add(sid)
        # Build top_patterns
        top_patterns = []
        for label, count in sorted(pattern_counts.items(), key=lambda x: -x[1])[:3]:
            top_patterns.append({
                "label": label,
                "count": count,
                "student_count": len(pattern_students.get(label, set())),
            })
        d["evidence_summary"] = {
            "student_count": len(affected),
            "event_count": total_events,
            "pattern_count": sum(pattern_counts.values()),
        }
        d["top_patterns"] = top_patterns
        enriched.append(d)
    return enriched

def get_issue(issue_id: str, class_id: int = None, teacher_id: int = None,
               job_role: str = "") -> Dict[str, Any]:
    """Get issue by ID, class-scoped when class_id/teacher_id provided."""
    issues = discover_issues(class_id=class_id, teacher_id=teacher_id, job_role=job_role)
    for i in issues:
        if i.get("issue_id") == issue_id:
            return i
    return {"issue_id": issue_id, "title": issue_id, "status": "not_found", "error": "ISSUE_NOT_FOUND", "message": "教学问题未找到"}

# --- Intervention Policy ---
def generate_candidates(issue_id: str, student_ids: List[str],
                        completed: List[str] = None, class_id: int = None,
                        teacher_id: int = None, job_role: str = "") -> List[Dict[str, Any]]:
    issue = get_issue(issue_id, class_id=class_id, teacher_id=teacher_id, job_role=job_role)
    if issue.get("status") == "not_found":
        return []
    if class_id and teacher_id:
        from app.services.class_management import get_class_students
        cls = get_class_students(class_id, teacher_id)
        roster = {s["username"] for s in (cls or {}).get("students", [])}
        student_ids = [sid for sid in (student_ids or []) if sid in roster]
        if not student_ids:
            return []
    ability_id = issue.get("primary_ability_id", "")
    if not ability_id:
        return []
    from app.services.policy.intervention_policy import InterventionPolicyEngine
    engine = InterventionPolicyEngine()
    candidates = engine.process(
        {"issue_id": issue_id, "primary_ability_id": ability_id, "issue_title": issue.get("title", "") if issue else ""},
        student_ids, completed
    )
    return [c.to_dict() for c in candidates]

def group_students(student_ids: List[str], patterns: List[Dict] = None) -> Dict[str, List[str]]:
    from app.services.policy.intervention_policy import InterventionPolicyEngine
    engine = InterventionPolicyEngine()
    return engine.group_students(student_ids, patterns)

# --- Teaching Workflow ---
def create_intervention(issue_id: str, candidate_id: str, student_ids: List[str],
                        teacher_id: str, scope_class: str = "", job_role: str = "",
                        plan_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from app.services.workflow.workflow_store import create_intervention as ws_create
    return ws_create(issue_id, candidate_id, student_ids, teacher_id,
                     scope_class=scope_class, job_role=job_role,
                     plan_snapshot=plan_snapshot)


def get_intervention(intervention_id: str) -> Dict[str, Any]:
    from app.services.workflow.workflow_store import get_intervention as ws_get
    result = ws_get(intervention_id)
    if not result:
        return {"intervention_id": intervention_id, "status": "not_found"}
    return result


def list_interventions(teacher_id: str = "", scope_class: str = "") -> List[Dict[str, Any]]:
    from app.services.workflow.workflow_store import list_interventions as ws_list
    return ws_list(teacher_id=teacher_id, scope_class=scope_class)


def update_intervention_plan(intervention_id: str, plan_snapshot: Dict[str, Any],
                             status: str = "draft", teacher_id: str = "") -> Dict[str, Any]:
    from app.services.workflow.workflow_store import update_intervention_plan as ws_update
    return ws_update(intervention_id, plan_snapshot, status=status, actor=teacher_id or "teacher")


def confirm_intervention(intervention_id: str, teacher_id: str) -> Dict[str, Any]:
    from app.services.workflow.workflow_store import transition_intervention
    return transition_intervention(intervention_id, "planned", teacher_id or "teacher")


def complete_intervention(intervention_id: str, teacher_id: str) -> Dict[str, Any]:
    from app.services.workflow.workflow_store import transition_intervention
    return transition_intervention(intervention_id, "completed", teacher_id or "teacher")

def review_intervention(intervention_id: str, approved: bool, teacher_id: str) -> Dict[str, Any]:
    from app.services.workflow.workflow_store import transition_intervention
    result = transition_intervention(intervention_id, "reviewed" if approved else "draft", teacher_id)
    if not result.get("ok"):
        return {"intervention_id": intervention_id, "status": "draft", "transition_ok": False, "error": result.get("error")}
    return result

def assign_intervention(intervention_id: str, candidate_id: str,
                        student_ids: List[str], teacher_id: str) -> Dict[str, Any]:
    from app.services.workflow.workflow_store import transition_intervention
    result = transition_intervention(intervention_id, "assigned", teacher_id)
    if not result.get("ok"):
        return {"intervention_id": intervention_id, "status": "draft", "transition_ok": False, "error": result.get("error")}
    return result

# --- Outcome ---
def evaluate_intervention(intervention_id: str, pre_states: List[Dict] = None,
                          post_states: List[Dict] = None) -> Dict[str, Any]:
    from app.services.outcome.outcome_model import OutcomeEvaluator
    from app.services.workflow.workflow_store import save_outcome, transition_intervention, get_intervention
    evaluator = OutcomeEvaluator()
    results = evaluator.batch_evaluate(pre_states or [], post_states or [])
    for result in results:
        save_outcome(
            intervention_id,
            result.student_id,
            pre_mastery=result.pre_mastery,
            post_mastery=result.post_mastery,
            delta=result.mastery_delta,
            pre_patterns=json.dumps([], ensure_ascii=False),
            post_patterns=json.dumps([], ensure_ascii=False),
            evidence_count=int(result.completion_rate * 3),
            status=result.outcome,
        )
    existing = get_intervention(intervention_id)
    if existing and existing.get("status") == "completed":
        transition_intervention(intervention_id, "evaluated", "system")
    summary = {
        "total": len(results),
        "improved": sum(1 for r in results if r.outcome == "improved"),
        "no_change": sum(1 for r in results if r.outcome == "no_change"),
        "worsened": sum(1 for r in results if r.outcome == "worsened"),
        "insufficient_evidence": sum(1 for r in results if r.outcome == "insufficient_evidence"),
    }
    return {"intervention_id": intervention_id, "outcomes": [r.to_dict() for r in results],
            "summary": summary}

def get_outcome(intervention_id: str) -> Dict[str, Any]:
    from app.services.workflow.workflow_store import get_outcome as ws_get_outcome
    return ws_get_outcome(intervention_id)

# --- Teacher AI V2 ---
def get_teacher_ai():
    from app.services.teacher_ai_v2 import get_teacher_ai_v2
    return get_teacher_ai_v2()
