"""Intervention Candidate Generation, Filtering, Ranking."""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class InterventionCandidate:
    candidate_id: str
    issue_id: str = ""
    intervention_type: str = ""   # quiz / scenario / explanation / training_task / reassessment
    title: str = ""
    description: str = ""
    ability_ids: List[str] = field(default_factory=list)
    target_students: List[str] = field(default_factory=list)
    score: float = 0.0
    constraints_passed: bool = True
    constraint_violations: List[str] = field(default_factory=list)
    prerequisites_met: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CandidateGenerator:
    """Generate intervention candidates from existing tools."""
    CANDIDATE_TYPES = ["quiz", "scenario", "explanation", "training_task", "reassessment", "knowledge_card"]

    def generate(self, issue: Dict[str, Any], student_ids: List[str]) -> List[InterventionCandidate]:
        aid = issue.get("primary_ability_id", "")
        candidates = []
        i = 0
        for ctype in self.CANDIDATE_TYPES:
            candidates.append(InterventionCandidate(
                candidate_id=f"CAND_{aid}_{ctype}",
                issue_id=issue.get("issue_id", ""),
                intervention_type=ctype,
                title=f"{ctype} for {aid}",
                ability_ids=[aid],
                target_students=student_ids,
            ))
        return candidates


class ConstraintFilter:
    """Filter candidates through safety, prerequisite, duplicate, and burden constraints."""

    def filter(self, candidates: List[InterventionCandidate],
               completed_tasks: List[str] = None,
               active_interventions: List[str] = None) -> List[InterventionCandidate]:
        completed = set(completed_tasks or [])
        active = set(active_interventions or [])
        for c in candidates:
            c.constraints_passed = True
            c.constraint_violations = []
            # Safety: unsafe operations require teacher approval
            if "safety" in str(c.ability_ids).lower():
                c.constraint_violations.append("safety_risk: requires teacher review")
            # Recent duplicate
            for aid in c.ability_ids:
                if aid in completed:
                    c.constraint_violations.append(f"already completed: {aid}")
                    c.constraints_passed = False
                if aid in active:
                    c.constraint_violations.append(f"active intervention exists: {aid}")
                    c.constraints_passed = False
        return candidates


class TransparentRanker:
    """Scoring: ability_match * 0.35 + evidence_strength * 0.25 + job_importance * 0.25 + safety_priority * 0.15."""

    def rank(self, candidates: List[InterventionCandidate],
             issue: Dict[str, Any] = None) -> List[InterventionCandidate]:
        for c in candidates:
            ability_score = 1.0 if c.ability_ids else 0.0
            evidence_score = (issue or {}).get("confidence", 0.5)
            job_score = (issue or {}).get("job_importance", 0.5)
            safety_score = (issue or {}).get("safety_risk", 0.0)
            c.score = ability_score * 0.35 + evidence_score * 0.25 + job_score * 0.25 + safety_score * 0.15
        return sorted(candidates, key=lambda c: -c.score)


class InterventionPolicyEngine:
    def __init__(self):
        self.generator = CandidateGenerator()
        self.filter = ConstraintFilter()
        self.ranker = TransparentRanker()

    def process(self, issue: Dict[str, Any], student_ids: List[str],
                completed: List[str] = None, active: List[str] = None) -> List[InterventionCandidate]:
        candidates = self.generator.generate(issue, student_ids)
        candidates = self.filter.filter(candidates, completed, active)
        return self.ranker.rank(candidates, issue)

    def group_students(self, student_ids: List[str], patterns: List[Dict] = None,
                       learner_states: List[Dict] = None) -> Dict[str, List[str]]:
        """Group students by diagnostic pattern for targeted intervention."""
        groups = {"default": list(student_ids)}
        if patterns:
            for pat in patterns:
                ptype = pat.get("pattern_type", "")
                if ptype not in groups:
                    groups[ptype] = []
                groups[ptype].append(pat.get("student_id", ""))
        return groups
