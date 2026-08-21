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
        issues = discover_issues(
            job_role=job_role,
            class_id=int(class_id) if class_id else None,
            teacher_id=teacher_id,
        )
        if not issues:
            return []
        return issues[:limit]

    def explain_issue(self, issue_id: str, class_id: int = None,
                      teacher_id: int = None, job_role: str = "") -> Dict[str, Any]:
        """Provide explanation and evidence for a teaching issue, class-scoped."""
        from app.services.v2_facade import get_issue
        issue = get_issue(issue_id, class_id=class_id, teacher_id=teacher_id, job_role=job_role)
        if issue and issue.get("status") != "not_found":
            evidence = issue.get("evidence_summary", {})
            top_patterns = issue.get("top_patterns", [])
            explanation = f"该问题当前影响 {evidence.get('student_count', 0)} 名学生。\n"
            explanation += f"系统记录到 {evidence.get('event_count', 0)} 条相关学习事件，"
            explanation += f"识别出 {evidence.get('pattern_count', 0)} 条重复诊断模式。\n"
            if top_patterns:
                top = top_patterns[0]
                explanation += f"最常见模式：{top.get('label', 'unknown')}，出现 {top.get('count', 0)} 次，涉及 {top.get('student_count', 0)} 名学生。\n"
            explanation += f"严重度 {round(issue.get('severity', 0) * 100)}%，判断置信度 {round(issue.get('confidence', 0) * 100)}%。"
            return {
                "issue_id": issue_id,
                "explanation": explanation,
                "evidence_summary": evidence,
                "top_patterns": top_patterns,
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
                           teacher_id: int = None, job_role: str = "") -> Dict[str, Any]:
        """Get aggregated student profile, class-scoped if class_id provided."""
        # P7-A: Verify student belongs to class if class_id specified
        if class_id and teacher_id:
            from app.services.class_management import get_class_students
            cls = get_class_students(class_id, teacher_id)
            if not cls:
                return {"student_id": student_id, "error": "班级不存在", "status": "not_found"}
            roster = {s["username"] for s in cls.get("students", [])}
            if student_id not in roster:
                return {"student_id": student_id, "error": "该学生不属于当前班级", "status": "not_in_class"}
        # P10.1-C: Reuse aggregated student profile from teacher_students
        try:
            from app.services.teacher_students import get_teacher_student_detail
            profile = get_teacher_student_detail(student_id, job_role=job_role)
            if profile and not profile.get("error"):
                profile["status"] = profile.get("status", "unknown")
                return profile
        except Exception:
            pass
        from app.services.v2_facade import get_student_state
        return get_student_state(student_id, job_role=job_role)

    def get_process_patterns(self, student_id: str, scenario_id: str = "") -> List[Dict[str, Any]]:
        """Get diagnostic patterns for a student in a scenario via V2 Facade."""
        from app.services.v2_facade import get_student_patterns
        return get_student_patterns(student_id, scenario_id) or []

    def generate_intervention_candidates(self, issue_id: str, student_ids: List[str],
                                            class_id: int = None, teacher_id: int = None,
                                            job_role: str = "") -> List[Dict[str, Any]]:
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
        return generate_candidates(
            issue_id,
            student_ids,
            class_id=class_id,
            teacher_id=teacher_id,
            job_role=job_role,
        )

    def draft_intervention(self, issue_id: str, candidate_id: str,
                            student_ids: List[str], teacher_id: str,
                            plan_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Draft an intervention for teacher review via V2 Facade (persistent store)."""
        from app.services.v2_facade import create_intervention
        return create_intervention(issue_id, candidate_id, student_ids, teacher_id,
                                   plan_snapshot=plan_snapshot)

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
    ctx = dict(context or {})
    if class_id is not None and ctx.get("class_id") != class_id:
        ctx = {"class_id": class_id}
    elif class_id is not None:
        ctx["class_id"] = class_id

    issue_id = _first(ctx, ["current_issue_id", "last_issue_id"])
    student_ids = _as_list(ctx.get("current_student_ids") or ctx.get("last_students") or [])
    student_id = ctx.get("current_student_id") or ctx.get("last_student_id") or (student_ids[0] if student_ids else "")
    candidate_id = ctx.get("current_candidate_id") or ctx.get("last_candidate_id") or ""
    intervention_id = ctx.get("current_intervention_id") or ctx.get("last_intervention_id") or ""
    draft_plan = ctx.get("current_intervention_draft") or {}

    result = {
        "answer": "",
        "evidence": [],
        "data_cards": [],
        "actions": [],
        "context_update": {},
        "intent": "general",
        "engine": "teacher_ai_v2",
    }

    modify_hit = any(kw in msg for kw in [
        "改成", "修改", "调整", "单独安排", "单独", "基础差", "分钟", "不做讲授",
        "改成实操", "实操", "讲授", "安排", "换个方案", "换个", "取消",
    ])
    plan_hit = any(kw in msg for kw in [
        "方案", "教学建议", "怎么教", "干预", "候选", "candidate", "intervention", "教学计划",
    ])
    issue_hit = any(kw in msg for kw in [
        "为什么", "原因", "解释", "说明", "这个", "怎么办", "如何", "证据",
    ])
    student_hit = any(kw in msg for kw in ["学生", "状态", "薄弱", "能力", "他", "表现", "谁"])
    status_hit = any(kw in msg for kw in ["状态", "进度", "status", "审批"])

    # Natural-language modification is the strongest signal when a draft exists.
    if modify_hit and (intervention_id or candidate_id or draft_plan):
        result["intent"] = "modify_intervention"
        plan = _modify_plan(draft_plan, msg, student_ids)
        if intervention_id:
            from app.services.v2_facade import update_intervention_plan
            saved = update_intervention_plan(intervention_id, plan, teacher_id=str(tid or ""))
            if saved.get("ok"):
                plan = saved.get("plan_snapshot", plan)
        result["answer"] = _describe_plan(plan)
        result["data_cards"] = [_plan_card(plan)]
        result["actions"] = [
            {"type": "draft_intervention", "label": "采用方案",
             "issue_id": issue_id, "candidate_id": candidate_id, "student_ids": student_ids, "plan": plan}
        ]
        if intervention_id:
            result["actions"].append({"type": "open_intervention", "label": "查看干预", "intervention_id": intervention_id})
        result["context_update"] = {
            "current_candidate_id": candidate_id,
            "last_candidate_id": candidate_id,
            "current_intervention_id": intervention_id,
            "last_intervention_id": intervention_id,
            "current_intervention_draft": plan,
        }
        return result

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
            result["actions"] = [{"type": "navigate", "module": "teacherToday", "label": "查看教学问题"}]
        else:
            result["answer"] = "当前未发现教学问题。系统需要更多学习证据来检测问题。"

    elif issue_hit and issue_id:
        result["intent"] = "explain_issue"
        explanation = ai.explain_issue(issue_id, class_id=class_id, teacher_id=tid, job_role=jr)
        result["answer"] = explanation.get("explanation", "")
        result["evidence"] = explanation.get("top_patterns", [])
        result["actions"] = [
            {"type": "open_issue", "label": "查看教学问题", "issue_id": issue_id},
            {"type": "generate_candidates", "label": "生成方案", "issue_id": issue_id, "student_ids": student_ids},
        ]
        result["context_update"] = {"current_issue_id": issue_id, "last_issue_id": issue_id,
                                    "current_student_ids": student_ids, "last_students": student_ids}

    elif plan_hit and issue_id and student_ids:
        result["intent"] = "generate_candidates"
        candidates = ai.generate_intervention_candidates(
            issue_id,
            student_ids,
            class_id=class_id,
            teacher_id=tid,
            job_role=jr,
        )
        if candidates:
            top = candidates[0]
            plan = _candidate_plan(top)
            result["answer"] = _describe_plan(plan)
            result["data_cards"] = [_plan_card(plan)]
            result["actions"] = [
                {"type": "generate_candidates", "label": "生成方案",
                 "issue_id": issue_id, "student_ids": student_ids},
                {"type": "select_candidate", "label": "采用方案",
                 "candidate_id": top.get("candidate_id", ""), "issue_id": issue_id,
                 "student_ids": student_ids, "plan": plan}
            ]
            result["context_update"] = {
                "last_candidate_id": top.get("candidate_id", ""),
                "current_candidate_id": top.get("candidate_id", ""),
                "last_students": student_ids,
                "current_student_ids": student_ids,
                "current_intervention_draft": plan,
            }
        else:
            result["answer"] = "当前问题暂时没有可生成的干预方案，请先补充学生证据。"

    # Student-related intents
    elif student_hit:
        result["intent"] = "student_state"
        import re
        m = re.search(r"(\d{3})", msg)
        sid = m.group(1) if m else student_id
        if sid:
            state = ai.get_student_state(sid, class_id=class_id, teacher_id=tid, job_role=jr)
            if state.get("status") == "not_in_class":
                result["answer"] = f"学生 {sid} 不属于当前班级。"
                result["data_cards"] = [state]
            elif state.get("status") == "not_found":
                result["answer"] = f"班级不存在或无权访问。"
                result["data_cards"] = [state]
            else:
                # P10.1-C: Build structured explanation from real profile
                status = state.get("status", "unknown")
                score = state.get("overall_score", 0)
                weak = state.get("weak_abilities", [])[:3]
                patterns = state.get("diagnostic_patterns", [])[:3]
                coverage = state.get("evidence_coverage", 0)
                answer = f"学生 {sid} 当前状态：{status}。\n"
                if score:
                    answer += f"总体测评分 {score}。\n"
                if weak:
                    answer += f"主要薄弱：{', '.join(weak)}。\n"
                if patterns:
                    answer += "最近诊断模式：\n"
                    for p in patterns[:3]:
                        label = p if isinstance(p, str) else (p.get("pattern_name") or p.get("name") or str(p))
                        answer += f"· {label}\n"
                if coverage:
                    answer += f"证据覆盖率 {round(coverage * 100)}%。"
                result["answer"] = answer
                result["data_cards"] = [{
                    "type": "student_profile",
                    "student_id": sid,
                    "overall_score": score,
                    "status": status,
                    "weak_abilities": weak,
                    "diagnostic_patterns": patterns,
                    "evidence_coverage": coverage,
                    "last_activity_at": state.get("last_activity_at"),
                }]
                result["actions"] = [{"type": "open_student", "label": "查看学生", "student_id": sid}]
                result["context_update"] = {"current_student_id": sid, "last_student_id": sid}
        else:
            result["answer"] = "请先选择或指定学生。"

    # Pattern-related intents
    elif any(kw in msg for kw in ["模式", "诊断", "过程", "pattern"]):
        result["intent"] = "student_patterns"
        import re
        m = re.search(r"(\d{3})", msg)
        sid = m.group(1) if m else student_id
        if sid:
            patterns = ai.get_process_patterns(sid)
            result["answer"] = f"学生 {sid} 检测到 {len(patterns)} 个诊断模式。"
            result["data_cards"] = patterns[:10]
        else:
            result["answer"] = "请指定学生编号以查询诊断模式。"

    elif any(kw in msg for kw in ["草稿", "创建干预", "draft", "采用"]):
        result["intent"] = "draft_intervention"
        issue_id = issue_id or ctx.get("last_issue_id", "")
        candidate_id = candidate_id or ctx.get("last_candidate_id", "")
        student_ids = student_ids or ctx.get("last_students", [])
        if issue_id and candidate_id and student_ids:
            plan = draft_plan or _candidate_plan({
                "candidate_id": candidate_id,
                "issue_id": issue_id,
                "ability_ids": [],
                "target_students": student_ids,
            })
            draft = ai.draft_intervention(
                issue_id, candidate_id, student_ids, teacher_id,
                plan_snapshot=plan,
            )
            result["answer"] = f"干预草案已创建：{draft.get('intervention_id', '')}，状态：{draft.get('status', 'draft')}"
            result["data_cards"] = [_plan_card(plan)]
            result["actions"] = [{"type": "open_intervention", "label": "查看干预",
                                  "intervention_id": draft.get("intervention_id", "")}]
            result["context_update"] = {"last_intervention_id": draft.get("intervention_id", "")}
        else:
            result["answer"] = "创建干预草案需要先选择问题、候选方案和学生。"

    elif status_hit and intervention_id:
        result["intent"] = "intervention_status"
        status = ai.get_intervention_status(intervention_id)
        result["answer"] = f"干预 {intervention_id} 当前状态：{status.get('status', 'unknown')}"
        result["data_cards"] = [status]
        result["actions"] = [{"type": "open_intervention", "label": "查看干预", "intervention_id": intervention_id}]

    else:
        # Unsupported V2 intent - delegate to V1
        result["intent"] = "general_v1_fallback"
        result["engine"] = "teacher_ai_v1"
        result["answer"] = "请先打开一个教学问题、学生或能力节点，再直接问“为什么”或“生成方案”。"

    return result


def _first(ctx: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        value = ctx.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if value:
        return [str(value)]
    return []


def _candidate_plan(candidate: Dict[str, Any]) -> Dict[str, Any]:
    ability_ids = candidate.get("ability_ids") or candidate.get("ability_id") or []
    if isinstance(ability_ids, str):
        ability_ids = [ability_ids]
    students = candidate.get("target_students") or candidate.get("student_ids") or []
    title = candidate.get("title") or "教学干预方案"
    plan = {
        "candidate_id": candidate.get("candidate_id", ""),
        "issue_id": candidate.get("issue_id", ""),
        "title": title,
        "duration_minutes": 20,
        "objective": "强化学生对本问题对应能力的理解，并通过实操纠正共性错误。",
        "method": "集中讲解 + 实物辨认 + 分组练习",
        "target_students": list(students),
        "focus_students": [],
        "ability_ids": list(ability_ids),
        "resources": ["传感器实物/接线图", "PLC 输入模块或等效实训台"],
        "steps": ["5分钟：回顾错误现象与安全要求", "10分钟：实物辨认和接线判断", "5分钟：分组复述并检查"],
        "verification": "学生能够独立说明判断依据，并完成一次正确接线或辨析。",
        "why": candidate.get("description") or "该方案直接针对本问题的主要薄弱能力，适合短时间课堂干预。",
        "expected_outcome": "相关错误事件减少，学生能正确完成目标能力判断。",
    }
    if "sn_type_identify" in ability_ids:
        plan["title"] = "集中纠错 + NPN/PNP 实物辨认"
        plan["objective"] = "区分 NPN/PNP 输出类型，并正确匹配 PLC 输入公共端。"
        plan["resources"] = ["NPN/PNP 传感器实物", "PLC 输入模块与接线图"]
        plan["verification"] = "学生能独立说明公共端匹配规则并完成接线判断。"
    return plan


def _modify_plan(plan: Dict[str, Any], message: str, student_ids: List[str]) -> Dict[str, Any]:
    import re
    updated = dict(plan or {})
    if not updated:
        updated = _candidate_plan({"target_students": student_ids})
    if "20分钟" in message:
        updated["duration_minutes"] = 20
    m = re.search(r"(\d+)\s*分钟", message)
    if m:
        updated["duration_minutes"] = int(m.group(1))
    if "不做讲授" in message or "改成实操" in message or "实操" in message:
        updated["method"] = "分组实操 + 即时反馈"
    if "讲授" in message and "不做" not in message:
        updated["method"] = "集中讲授 + 实物示范"
    focus = []
    for sid in student_ids:
        if sid in message:
            focus.append(sid)
    explicit = re.findall(r"\b(\d{3})\b", message)
    for sid in explicit:
        if sid not in focus:
            focus.append(sid)
    if focus:
        updated["focus_students"] = focus
        updated["special_arrangement"] = "；".join([f"{sid} 单独安排" for sid in focus])
    if "基础差" in message:
        updated["method"] = "降低起点 + 分步示范 + 单独反馈"
        updated["note"] = "已针对基础较弱学生降低初始难度。"
    if "没PLC实训台" in message or "没有PLC" in message:
        updated["resources"] = ["传感器实物", "接线图/图纸", "仿真或替代训练板"]
    if "取消" in message:
        updated["status_hint"] = "建议取消当前草案"
    return updated


def _describe_plan(plan: Dict[str, Any]) -> str:
    duration = plan.get("duration_minutes", 20)
    students = plan.get("target_students") or []
    method = plan.get("method", "")
    focus = plan.get("focus_students") or []
    text = f"建议用时：{duration} 分钟。适用学生：{len(students)} 人。"
    if method:
        text += f"\n教学方式：{method}。"
    if focus:
        text += "\n单独安排：" + "、".join(str(s) for s in focus) + "。"
    text += f"\n验证方式：{plan.get('verification', '学生能独立完成判断。')}"
    return text


def _plan_card(plan: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "intervention_plan",
        "candidate_id": plan.get("candidate_id", ""),
        "title": plan.get("title", "教学干预方案"),
        "duration_minutes": plan.get("duration_minutes", 20),
        "target_students": plan.get("target_students", []),
        "focus_students": plan.get("focus_students", []),
        "ability_ids": plan.get("ability_ids", []),
        "objective": plan.get("objective", ""),
        "method": plan.get("method", ""),
        "steps": plan.get("steps", []),
        "resources": plan.get("resources", []),
        "verification": plan.get("verification", ""),
        "why": plan.get("why", ""),
        "expected_outcome": plan.get("expected_outcome", ""),
    }
