"""TeachingIssue model - formal teaching decision object."""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class TeachingIssue:
    issue_id: str
    class_id: str = ""
    title: str = ""
    primary_ability_id: str = ""
    affected_students: List[str] = field(default_factory=list)
    affected_ratio: float = 0.0
    severity: float = 0.0      # 0.0 - 1.0
    job_importance: float = 0.0
    safety_risk: float = 0.0
    confidence: float = 0.0
    priority: float = 0.0      # computed composite
    evidence_refs: List[str] = field(default_factory=list)
    pattern_refs: List[str] = field(default_factory=list)
    status: str = "open"       # open / acknowledged / in_progress / resolved
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TeachingIssue":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
