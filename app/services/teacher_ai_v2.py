"""Teacher AI V2 Orchestrator.

Calls formal V2 Engine APIs instead of raw data queries.
Natural language orchestration layer over Evidence/Diagnosis/Issue/Policy engines.
All methods route through V2 Facade for unified engine access.
"""

from typing import Any, Dict, List, Optional


class TeacherAIV2:
    """V2 Teacher AI - orchestrates all V2 engines through V2 Facade."""

    def get_class_state(self, class_id: str, job_role: str = "") -> Dict[str, Any]:
        """Return class-level state summary from V2 engines."""
        return {
            "class_id": class_id,
            "job_role": job_role,
            "engines_available": ["evidence", "state", "diagnosis", "issue", "policy", "workflow", "outcome"],
        }

    def find_teaching_issues(self, class_id: str = "", job_role: str = "",
                              limit: int = 10, teacher_id: int = None) -> List[Dict[str, Any]]:
        """Find and rank teaching issues, strictly scoped to class roster."""
        from app.services.v2_facade import discover_issues
        issues = discover_issues(class_id=int(class_id) if class_id else None, teacher_id=teacher_id)
        if not issues:
            return []
        return issues[:limit]

    def explain_issue(self, issue_id: str) -> Dict[str, Any]:
        """Provide explanation and evidence for a teaching issue via V2 Facade."""
        from app.services.v2_facade import get_issue
        issue = get_issue(issue_id)
        if issue and issue.get("status") != "unknown":
            return {
                "issue_id": issue_id,
                "explanation": issue.get("description", "基于学生学习证据自动发现的共性问题"),
                "evidence_summary": issue.get("evidence_refs", []),
                "recommended_actions": ["查看班级洞察", "生成教学评语", "创建针对性训练"],
                "issue": issue,
            }
        return {
            "issue_id": issue_id,
            "explanation": "未找到该问题的详细信息",
            "evidence_summary": [],
            "recommended_actions": [],
        }

    def get_student_state(self, student_id: str, class_id: int = None,
                           teacher_id: int = None) -> Dict[str, Any]:
        """Get learner state for a specific student, class-scoped if class_id provided."""
        from app.services.v2_facade import get_student_state
        # P7-A: Verify student belongs to class if class_id specified
        if class_id and teacher_id:
            from app.services.class_management import get_class_students
            cls = get_class_students(class_id, teacher_id)
            if not cls:
                return {"student_id": student_id, "error": "班级不存在", "status": "not_found"}
            roster = {s["username"] for s in cls.get("students", [])}
            if student_id not in roster:
                return {"student_id": student_id, "error": "该学生不属于当前班级", "status": "not_in_class"}
        return get_student_state(student_id)

    def get_process_patterns(self, student_id: str, scenario_id: str = "") -> List[Dict[str, Any]]:
        """Get diagnostic patterns for a student in a scenario via V2 Facade."""
        from app.services.v2_facade import get_student_patterns
        return get_student_patterns(student_id, scenario_id) or []

    def generate_intervention_candidates(self, issue_id: str, student_ids: List[str],
                                            class_id: int = None, teacher_id: int = None) -> List[Dict[str, Any]]:
        """Generate ranked intervention candidates, restricted to class roster."""
        # P7-A: Filter student_ids to class roster
        if class_id and teacher_id:
            from app.services.class_management import get_class_students
            cls = get_class_students(class_id, teacher_id)
            if not cls:
                return []
            roster = {s["username"] for s in cls.get("students", [])}
            student_ids = [s for s in (student_ids or []) if s in roster]
            if not student_ids:
                return []
        from app.services.v2_facade import generate_candidates
        return generate_candidates(issue_id, student_ids)

    def draft_intervention(self, issue_id: str, candidate_id: str,
                            student_ids: List[str], teacher_id: str) -> Dict[str, Any]:
        """Draft an intervention for teacher review via V2 Facade (persistent store)."""
        from app.services.v2_facade import create_intervention
        return create_intervention(issue_id, candidate_id, student_ids, teacher_id)

    def get_intervention_status(self, intervention_id: str) -> Dict[str, Any]:
        """Get current status of an intervention from persistent Workflow Store."""
        from app.services.workflow.workflow_store import get_intervention
        result = get_intervention(intervention_id)
        if result:
            return {
                "intervention_id": intervention_id,
                "status": result.get("status", "draft"),
                "detail": result,
            }
        return {"intervention_id": intervention_id, "status": "not_found"}

    def evaluate_intervention(self, intervention_id: str,
                               pre_states: List[Dict] = None,
                               post_states: List[Dict] = None) -> Dict[str, Any]:
        """Evaluate intervention outcomes via V2 Facade."""
        from app.services.v2_facade import evaluate_intervention, get_outcome
        result = evaluate_intervention(intervention_id, pre_states, post_states)
        outcome = get_outcome(intervention_id)
        result["outcome_store"] = outcome
        return result


# Singleton
_teacher_ai_v2: Optional[TeacherAIV2] = None


def get_teacher_ai_v2() -> TeacherAIV2:
    global _teacher_ai_v2
    if _teacher_ai_v2 is None:
        _teacher_ai_v2 = TeacherAIV2()
    return _teacher_ai_v2


def handle_teacher_message_v2(message: str, job_role: str = None, teacher_id: str = "",
                               history: List = None, ui_context: Dict = None,
                               context: Dict = None, class_id: int = None) -> Dict[str, Any]:
    """V2 Teacher message handler - routes all intents through V2 Facade.
    
    Supported V2 intents:
    - find_issues / teaching_issues: Real IssueDiscoveryEngine
    - explain_issue: Real get_issue
    - student_state: Real LearnerState
    - student_patterns: Real PatternClassifier
    - generate_candidates: Real InterventionPolicyEngine
    - draft_intervention: Real persistent Workflow Store
    - intervention_status: Real persistent status
    
    Unsupported intents fall back to V1 handler.
    """
    ai = get_teacher_ai_v2()
    jr = job_role or ""
    msg = message.strip()
    tid = int(teacher_id) if str(teacher_id).isdigit() else None

    # P7-B: Bind context to class_id; reset if class_id mismatch
    ctx = context or {}
    if class_id is not None and ctx.get("class_id") != class_id:
        ctx = {"class_id": class_id}
    elif class_id is None:
        ctx = dict(ctx)
    else:
        ctx = dict(ctx)

    result = {
        "answer": "",
        "evidence": [],
        "data_cards": [],
        "actions": [],
        "context_update": {},
        "intent": "general",
        "engine": "teacher_ai_v2",
    }

    # Issue-related intents
    if any(kw in msg for kw in ["教学问题", "问题列表", "发现问题", "共有问题", "common issue"]):
        result["intent"] = "find_issues"
        issues = ai.find_teaching_issues(class_id=class_id, job_role=jr, teacher_id=tid)
        if issues:
            result["answer"] = f"当前识别到 {len(issues)} 个教学问题：\n"
            for i, issue in enumerate(issues[:5], 1):
                title = issue.get("title", issue.get("issue_id", ""))
                priority = issue.get("priority", "medium")
                students = len(issue.get("affected_students", []))
                result["answer"] += f"{i}. {title} (优先级: {priority}, 影响 {students} 名学生)\n"
            result["data_cards"] = issues[:5]
            result["actions"] = [{"type": "navigate", "module": "teacherIssues", "label": "查看教学问题"}]
        else:
            result["answer"] = "当前未发现教学问题。系统需要更多学习证据来检测问题。"

    elif any(kw in msg for kw in ["解释", "说明", "这个"]):
        result["intent"] = "explain_issue"
        issue_id = context.get("last_issue_id", "") if context else ""
        if issue_id:
            explanation = ai.explain_issue(issue_id)
            result["answer"] = explanation.get("explanation", "")
            result["evidence"] = explanation.get("evidence_summary", [])

    # Student-related intents
    elif any(kw in msg for kw in ["学生", "状态", "薄弱", "能力"]):
        result["intent"] = "student_state"
        import re
        m = re.search(r"(\d{3})", msg)
        sid = m.group(1) if m else ""
        if sid:
            state = ai.get_student_state(sid, class_id=class_id, teacher_id=tid)
            if state.get("status") == "not_in_class":
                result["answer"] = f"学生 {sid} 不属于当前班级。"
                result["data_cards"] = [state]
            elif state.get("status") == "not_found":
                result["answer"] = f"班级不存在或无权访问。"
                result["data_cards"] = [state]
            else:
                result["answer"] = f"学生 {sid} 的学习状态已加载。"
                result["data_cards"] = [state]

    # Pattern-related intents
    elif any(kw in msg for kw in ["模式", "诊断", "过程", "pattern"]):
        result["intent"] = "student_patterns"
        import re
        m = re.search(r"(\d{3})", msg)
        sid = m.group(1) if m else ""
        if sid:
            patterns = ai.get_process_patterns(sid)
            result["answer"] = f"学生 {sid} 检测到 {len(patterns)} 个诊断模式。"
            result["data_cards"] = patterns[:10]
        else:
            result["answer"] = "请指定学生编号以查询诊断模式。"

    # Intervention-related intents
    elif any(kw in msg for kw in ["干预", "候选", "方案", "candidate", "intervention"]):
        result["intent"] = "generate_candidates"
        issue_id = (context or {}).get("last_issue_id", "")
        student_ids = (context or {}).get("last_students", [])
        if issue_id and student_ids:
            candidates = ai.generate_intervention_candidates(issue_id, student_ids, class_id=class_id, teacher_id=tid)
            result["answer"] = f"为问题 {issue_id} 生成了 {len(candidates)} 个干预候选方案。"
            result["data_cards"] = candidates[:5]
            if candidates:
                result["context_update"] = {"last_candidate_id": candidates[0].get("candidate_id", "")}

    elif any(kw in msg for kw in ["草稿", "创建干预", "draft"]):
        result["intent"] = "draft_intervention"
        ctx = context or {}
        issue_id = ctx.get("last_issue_id", "")
        candidate_id = ctx.get("last_candidate_id", "")
        student_ids = ctx.get("last_students", [])
        if issue_id and candidate_id and student_ids:
            draft = ai.draft_intervention(issue_id, candidate_id, student_ids, teacher_id)
            result["answer"] = f"干预草案已创建：{draft.get('intervention_id', '')}，状态：{draft.get('status', 'draft')}"
            result["context_update"] = {"last_intervention_id": draft.get("intervention_id", "")}
        else:
            result["answer"] = "创建干预草案需要先选择问题、候选方案和学生。"

    elif any(kw in msg for kw in ["状态", "进度", "status", "审批"]):
        result["intent"] = "intervention_status"
        ctx = context or {}
        intervention_id = ctx.get("last_intervention_id", "")
        if intervention_id:
            status = ai.get_intervention_status(intervention_id)
            result["answer"] = f"干预 {intervention_id} 当前状态：{status.get('status', 'unknown')}"
            result["data_cards"] = [status]

    else:
        # Unsupported V2 intent - delegate to V1
        result["intent"] = "general_v1_fallback"
        result["engine"] = "teacher_ai_v1"
        result["answer"] = "V2引擎暂不支持此查询。请使用教学问题、学生状态、干预管理等V2功能。"

    return result
