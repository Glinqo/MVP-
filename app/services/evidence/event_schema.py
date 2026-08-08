"""V2 LearningEvent Canonical Schema.

Inspired by xAPI Actor-Verb-Object structure.
Events are immutable facts; derivative conclusions belong in Projections.
"""

import uuid
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict

# Schema version for migration tracking
SCHEMA_VERSION = "2.0"

class EventVerb:
    SCENARIO_ACTION = "scenario_action"
    ASSESSMENT_ANSWER = "assessment_answer"
    QUIZ_ANSWER = "quiz_answer"
    FEEDBACK = "feedback"
    TRAINING_TASK_START = "training_task_start"
    TRAINING_TASK_COMPLETE = "training_task_complete"
    CONVERSATION_MESSAGE = "conversation_message"
    INTERVENTION_ASSIGNED = "intervention_assigned"
    INTERVENTION_COMPLETED = "intervention_completed"
    SELF_REPORT = "self_report"

class EventResult:
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

@dataclass
class EventContext:
    class_id: Optional[str] = None
    job_role: Optional[str] = None
    session_id: Optional[str] = None
    scenario_id: Optional[str] = None
    quiz_id: Optional[str] = None
    task_id: Optional[str] = None
    ability_ids: List[str] = field(default_factory=list)
    device_state: Optional[Dict[str, Any]] = None

@dataclass
class EvidenceBlock:
    classification: Optional[str] = None
    expected_state: Optional[str] = None
    observed_state: Optional[str] = None
    severity: Optional[str] = None
    norm_distance: Optional[float] = None

@dataclass
class LearningEvent:
    event_id: str
    actor_id: str          # student username or user_id
    verb: str              # one of EventVerb values
    object_id: str         # e.g., scenario step, question id, task id
    result: Optional[Dict[str, Any]] = None
    context: Optional[EventContext] = None
    evidence: Optional[EvidenceBlock] = None
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "direct"
    schema_version: str = SCHEMA_VERSION
    processor_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LearningEvent":
        ctx = d.get("context")
        ev = d.get("evidence")
        return cls(
            event_id=d.get("event_id", ""),
            actor_id=d.get("actor_id", ""),
            verb=d.get("verb", ""),
            object_id=d.get("object_id", ""),
            result=d.get("result"),
            context=EventContext(**ctx) if ctx else None,
            evidence=EvidenceBlock(**ev) if ev else None,
            occurred_at=d.get("occurred_at", ""),
            source=d.get("source", "direct"),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            processor_version=d.get("processor_version", "1.0"),
        )


def validate_event(event: LearningEvent) -> List[str]:
    """Return list of validation errors; empty list = valid."""
    errors = []
    if not event.event_id:
        errors.append("event_id is required")
    if not event.actor_id:
        errors.append("actor_id is required")
    if not event.verb:
        errors.append("verb is required")
    if event.schema_version != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    return errors


def normalize_event(raw: Dict[str, Any], ability_id_mapper=None) -> LearningEvent:
    """Normalize a raw event dict into a canonical LearningEvent."""
    event_id = raw.get("event_id") or str(uuid.uuid4())
    ctx_data = raw.get("context") or {}
    ability_ids = ctx_data.get("ability_ids") or raw.get("ability_ids") or []
    if ability_id_mapper:
        ability_ids = [ability_id_mapper(a) for a in ability_ids]

    return LearningEvent(
        event_id=event_id,
        actor_id=raw.get("actor_id") or raw.get("student_id") or "",
        verb=raw.get("verb") or "assessment_answer",
        object_id=raw.get("object_id") or raw.get("question_id") or raw.get("task_id") or "",
        result=raw.get("result") or {"outcome": raw.get("correct") if "correct" in raw else "unknown"},
        context=EventContext(
            class_id=ctx_data.get("class_id", ""),
            job_role=ctx_data.get("job_role") or raw.get("job_role", ""),
            session_id=ctx_data.get("session_id") or raw.get("session_id", ""),
            scenario_id=ctx_data.get("scenario_id", ""),
            quiz_id=ctx_data.get("quiz_id", ""),
            task_id=ctx_data.get("task_id", ""),
            ability_ids=ability_ids,
        ),
        evidence=EvidenceBlock(
            classification=raw.get("classification") or (raw.get("evidence") or {}).get("classification"),
        ) if (raw.get("classification") or raw.get("evidence")) else None,
        occurred_at=raw.get("occurred_at") or raw.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        source=raw.get("source", "direct"),
        schema_version=SCHEMA_VERSION,
        processor_version="1.0",
    )
