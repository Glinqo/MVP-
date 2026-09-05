"""Teaching Workflow FSM with Teacher-in-the-loop."""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


VALID_TRANSITIONS = {
    "draft": ["reviewed"],
    "reviewed": ["draft", "assigned"],
    "assigned": ["in_progress"],
    "in_progress": ["completed", "abandoned"],
    "completed": ["evaluated"],
    "evaluated": ["closed"],
    "closed": [],
    "abandoned": [],
}


@dataclass
class InterventionWorkflow:
    intervention_id: str
    issue_id: str = ""
    teacher_id: str = ""
    status: str = "draft"
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    approved_candidate_id: str = ""
    assigned_students: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    transition_log: List[Dict[str, str]] = field(default_factory=list)

    def transition(self, new_status: str, actor: str = "system") -> bool:
        if new_status not in VALID_TRANSITIONS.get(self.status, []):
            return False
        self.transition_log.append({
            "from": self.status, "to": new_status,
            "actor": actor, "at": datetime.now(timezone.utc).isoformat()
        })
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return True

    def can_teacher_approve(self) -> bool:
        return self.status in ("draft", "reviewed")

    def teacher_approve(self, candidate_id: str, student_ids: List[str], teacher_id: str):
        if not self.can_teacher_approve():
            return False
        self.approved_candidate_id = candidate_id
        self.assigned_students = student_ids
        self.teacher_id = teacher_id
        return self.transition("assigned", teacher_id)

    def mark_completed(self):
        return self.transition("completed")

    def mark_evaluated(self):
        return self.transition("evaluated")

    def close(self):
        return self.transition("closed")

    def send_back_to_draft(self, reason: str):
        self.transition_log.append({"note": f"sent back: {reason}"})
        return self.transition("draft")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InterventionWorkflow":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
