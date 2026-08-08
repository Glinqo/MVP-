"""V2 Evidence Query Interface.

Provides structured access to learning events with provenance tracking.
"""

from typing import Any, Dict, List, Optional
from .event_store import EventStore, get_event_store


class EventQuery:
    def __init__(self, store: EventStore = None):
        self.store = store or get_event_store()

    def by_student(self, student_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        return self.store.query_events(actor_id=student_id, limit=limit)

    def by_ability(self, ability_id: str) -> List[Dict[str, Any]]:
        return self.store.query_events(limit=500)

    def by_student_ability(self, student_id: str, ability_id: str) -> List[Dict[str, Any]]:
        return self.store.query_events(actor_id=student_id, limit=200)

    def recent_by_student(self, student_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self.store.query_events(actor_id=student_id, limit=limit)

    def event_count(self, student_id: str) -> int:
        return self.store.count_events(actor_id=student_id)

    def total_events(self) -> int:
        return self.store.count_events()
