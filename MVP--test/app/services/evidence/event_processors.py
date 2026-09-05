"""V2 Event Processors - Schema, Normalization, and Classification.

Processors transform raw events into canonical LearningEvents.
"""

from typing import Any, Dict
from .event_schema import LearningEvent, normalize_event


class LegacyEventAdapter:
    """Adapter to convert V1 legacy events to V2 LearningEvent format."""

    @staticmethod
    def adapt(event: Dict[str, Any]) -> LearningEvent:
        v1_type = event.get("type") or event.get("event_type") or ""
        mapping = {
            "assessment_answer": "assessment_answer",
            "scenario_step": "scenario_action",
            "quiz_answer": "quiz_answer",
            "feedback": "feedback",
        }
        verb = mapping.get(v1_type, v1_type or "assessment_answer")
        raw = {**event, "verb": verb}
        return normalize_event(raw)

    @staticmethod
    def adapt_batch(events: list) -> list:
        return [LegacyEventAdapter.adapt(e) for e in events]


class EventClassifier:
    """Classify scenario events into diagnostic patterns."""

    @staticmethod
    def classify_scenario_event(event: LearningEvent, expected_action: str = "") -> str:
        if not expected_action:
            return ""
        if event.object_id == expected_action:
            return "correct_action"
        return EventClassifier._classify_deviation(event, expected_action)

    @staticmethod
    def _classify_deviation(event: LearningEvent, expected: str) -> str:
        obj = (event.object_id or "").lower()
        if "edit" in obj or "modify" in obj or "program" in obj:
            return "premature_program_edit"
        if "replace" in obj or "change" in obj or "module" in obj:
            return "premature_component_replacement"
        if "power" in obj and "off" not in obj and "disconnect" not in obj:
            return "unsafe_live_operation"
        return "incorrect_action"
