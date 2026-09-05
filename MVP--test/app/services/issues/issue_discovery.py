"""Teaching Issue Discovery Engine.

Fuses: LearnerState + Diagnostic Patterns + Job Graph + Safety into formal TeachingIssues.
"""

import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from .teaching_issue import TeachingIssue


class IssueDiscoveryEngine:
    def __init__(self, job_graph_data: Dict[str, Any] = None):
        self.job_graph = job_graph_data or {}

    def discover_from_states(self, learner_states: Dict[str, Any],
                              patterns: List[Dict[str, Any]] = None,
                              total_students: int = 1) -> List[TeachingIssue]:
        issues = []
        patterns = patterns or []

        # Group states by ability_id
        ability_states: Dict[str, List[Dict]] = {}
        for state in learner_states:
            for aid, astate in state.get("abilities", {}).items():
                ability_states.setdefault(aid, []).append(astate)

        for aid, states in ability_states.items():
            weak_count = sum(1 for s in states if s.get("status") == "weak")
            affected_ratio = weak_count / max(1, total_students)
            affected_students = [s.get("student_id", "") for s in states if s.get("status") == "weak"]

            if weak_count >= 2 and affected_ratio >= 0.15:
                job_info = self._get_job_info(aid)
                severity = self._compute_severity(states)
                priority = self._compute_priority(severity, affected_ratio, job_info)

                issues.append(TeachingIssue(
                    issue_id=f"ISSUE_{aid}_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                    primary_ability_id=aid,
                    affected_students=affected_students[:10],
                    affected_ratio=round(affected_ratio, 2),
                    severity=round(severity, 2),
                    job_importance=round(job_info.get("importance", 0.5), 2),
                    safety_risk=round(job_info.get("safety_risk", 0.0), 2),
                    confidence=round(min(1.0, weak_count * 0.15), 2),
                    priority=round(priority, 2),
                    title=f"能力 {aid} 薄弱",
                ))

        return sorted(issues, key=lambda i: -i.priority)

    def _get_job_info(self, ability_id: str) -> Dict[str, float]:
        for node in self.job_graph.get("nodes", []):
            if node.get("id") == ability_id:
                return {
                    "importance": node.get("demand_weight", 0.5),
                    "safety_risk": 0.3 if "safety" in (node.get("name", "") or "").lower() else 0.0,
                }
        return {"importance": 0.5, "safety_risk": 0.0}

    def _compute_severity(self, states: List[Dict]) -> float:
        avg_mastery = sum(s.get("mastery", 0) for s in states) / max(1, len(states))
        return 1.0 - avg_mastery

    def _compute_priority(self, severity: float, affected_ratio: float, job_info: Dict) -> float:
        return 0.30 * severity + 0.25 * affected_ratio + 0.25 * job_info.get("importance", 0.5) + 0.20 * job_info.get("safety_risk", 0.0)
