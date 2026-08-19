"""V2 API Facade - unified entry point for all V2 engines.

server.py -> V2Facade -> Engine
Never let server.py directly access engine internals.
"""

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
    engine = IssueDiscoveryEngine()
    # P6-B: No silent demo fallback. If no class scope is provided, return empty.
    if not class_id or not teacher_id:
        return []
    from app.services.class_management import get_class_students
    cls = get_class_students(class_id, teacher_id)
    if not cls:
        return []
    _DEMO_STUDENTS = [s["username"] for s in cls.get("students", [])]
    if not student_states:
        from app.services.state.learner_state import LearnerState
        student_states = []
        for sid in _DEMO_STUDENTS:
            try:
                st = LearnerState(student_id=sid, job_role=job_role)
                student_states.append(st.to_dict())
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
            for sid in _DEMO_STUDENTS:
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
    issues = engine.discover_from_states(student_states or [], patterns or [])
    return [i.to_dict() for i in issues]

def get_issue(issue_id: str) -> Dict[str, Any]:
    issues = discover_issues()
    for i in issues:
        if i.get("issue_id") == issue_id:
            return i
    return {"issue_id": issue_id, "title": issue_id, "status": "not_found", "error": "ISSUE_NOT_FOUND", "message": "教学问题未找到"}

# --- Intervention Policy ---
def generate_candidates(issue_id: str, student_ids: List[str],
                        completed: List[str] = None) -> List[Dict[str, Any]]:
    issue = get_issue(issue_id)
    ability_id = issue.get("primary_ability_id", "") if issue else ""
    if not ability_id:
        ability_id = "PLC_INPUT_NO_RESPONSE"
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
                        teacher_id: str) -> Dict[str, Any]:
    from app.services.workflow.workflow_store import create_intervention as ws_create
    return ws_create(issue_id, candidate_id, student_ids, teacher_id)

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
    evaluator = OutcomeEvaluator()
    results = evaluator.batch_evaluate(pre_states or [], post_states or [])
    return {"intervention_id": intervention_id, "outcomes": [r.to_dict() for r in results],
            "summary": {"total": len(results)}}

def get_outcome(intervention_id: str) -> Dict[str, Any]:
    from app.services.workflow.workflow_store import get_outcome as ws_get_outcome
    return ws_get_outcome(intervention_id)

# --- Teacher AI V2 ---
def get_teacher_ai():
    from app.services.teacher_ai_v2 import get_teacher_ai_v2
    return get_teacher_ai_v2()
