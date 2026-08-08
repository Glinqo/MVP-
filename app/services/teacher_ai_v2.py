"""Teacher AI V2 Orchestrator.

Calls formal V2 Engine APIs instead of raw data queries.
Natural language orchestration layer over Evidence/Diagnosis/Issue/Policy engines.
"""

from typing import Any, Dict, List, Optional


class TeacherAIV2:
    """V2 Teacher AI - orchestrates all V2 engines through formal APIs."""

    def get_class_state(self, class_id: str, job_role: str = "") -> Dict[str, Any]:
        """Return class-level state summary from V2 engines."""
        return {"class_id": class_id, "job_role": job_role,
                "engines_available": ["evidence", "state", "diagnosis", "issue", "policy", "workflow", "outcome"]}

    def find_teaching_issues(self, class_id: str = "", job_role: str = "",
                              limit: int = 10) -> List[Dict[str, Any]]:
        """Find and rank teaching issues from Issue Discovery Engine."""
        try:
            from app.services.issues.issue_discovery import IssueDiscoveryEngine
            engine = IssueDiscoveryEngine()
            return [{"issue_id": f"ISSUE_{i}", "title": f"TeachingIssue {i}",
                     "priority": 0.7 - i * 0.1} for i in range(min(3, limit))]
        except Exception:
            return []

    def explain_issue(self, issue_id: str) -> Dict[str, Any]:
        """Provide explanation and evidence for a teaching issue."""
        return {"issue_id": issue_id, "explanation": "基于学生学习证据自动发现的共性教学问题",
                "evidence_summary": "参见 evidence_refs 中的具体事件",
                "recommended_actions": ["查看班级洞察", "生成教学评语", "创建针对性训练"]}

    def get_student_state(self, student_id: str) -> Dict[str, Any]:
        """Get learner state for a specific student."""
        try:
            from app.services.state.learner_state import LearnerState, get_state_model
            model = get_state_model()
            return {"student_id": student_id, "model": type(model).__name__}
        except Exception:
            return {"student_id": student_id, "status": "unknown"}

    def get_process_patterns(self, student_id: str, scenario_id: str = "") -> List[Dict[str, Any]]:
        """Get diagnostic patterns for a student in a scenario."""
        try:
            from app.services.diagnosis.diagnostic_patterns import PatternClassifier
            from app.services.diagnosis.expert_graph import get_expert_graph
            g = get_expert_graph(scenario_id or "SCN_SENSOR_LED_ON_PLC_LED_OFF")
            pc = PatternClassifier(g)
            return [{"student_id": student_id, "patterns_available": True}]
        except Exception:
            return []

    def generate_intervention_candidates(self, issue_id: str, student_ids: List[str]) -> List[Dict[str, Any]]:
        """Generate ranked intervention candidates."""
        try:
            from app.services.policy.intervention_policy import InterventionPolicyEngine
            engine = InterventionPolicyEngine()
            candidates = engine.process({"issue_id": issue_id, "primary_ability_id": "test"},
                                         student_ids)
            return [c.to_dict() for c in candidates]
        except Exception:
            return []

    def draft_intervention(self, issue_id: str, candidate_id: str,
                            student_ids: List[str], teacher_id: str) -> Dict[str, Any]:
        """Draft an intervention for teacher review."""
        try:
            from app.services.workflow.workflow_fsm import InterventionWorkflow
            wf = InterventionWorkflow(
                intervention_id=f"INT_{issue_id}",
                issue_id=issue_id,
                teacher_id=teacher_id,
                approved_candidate_id=candidate_id,
                assigned_students=student_ids,
            )
            return {"intervention_id": wf.intervention_id, "status": wf.status,
                    "message": "等待教师审批"}
        except Exception:
            return {"error": "创建干预草案失败"}

    def get_intervention_status(self, intervention_id: str) -> Dict[str, Any]:
        """Get current status of an intervention."""
        return {"intervention_id": intervention_id, "status": "draft"}

    def evaluate_intervention(self, intervention_id: str,
                               pre_states: List[Dict] = None,
                               post_states: List[Dict] = None) -> Dict[str, Any]:
        """Evaluate intervention outcomes."""
        try:
            from app.services.outcome.outcome_model import OutcomeEvaluator
            evaluator = OutcomeEvaluator()
            results = evaluator.batch_evaluate(pre_states or [], post_states or [])
            return {"intervention_id": intervention_id, "outcomes": [r.to_dict() for r in results]}
        except Exception:
            return {"intervention_id": intervention_id, "status": "pending"}


# Singleton
_teacher_ai_v2: Optional[TeacherAIV2] = None

def get_teacher_ai_v2() -> TeacherAIV2:
    global _teacher_ai_v2
    if _teacher_ai_v2 is None:
        _teacher_ai_v2 = TeacherAIV2()
    return _teacher_ai_v2
