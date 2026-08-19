"""V2 Learning Event Bus - Processor Pipeline.

Inspired by Open edX event-tracking architecture.
Events flow: emit -> validate -> enrich -> normalize -> persist -> project.
"""

from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass
import logging

from .event_schema import LearningEvent, validate_event
from .event_store import EventStore, get_event_store

logger = logging.getLogger(__name__)


@dataclass
class Processor:
    name: str
    fn: Callable[[LearningEvent], LearningEvent]
    enabled: bool = True


class EventBus:
    def __init__(self, store: EventStore = None):
        self.store = store or get_event_store()
        self.processors: List[Processor] = []
        self.projectors: List[Callable[[LearningEvent], None]] = []
        self._setup_default_processors()

    def _setup_default_processors(self):
        self.processors = [
            Processor("validate", self._validate_processor),
            Processor("normalize_ids", self._normalize_ids_processor),
            Processor("enrich_context", self._enrich_context_processor),
        ]

    def _validate_processor(self, event: LearningEvent) -> LearningEvent:
        errors = validate_event(event)
        if errors:
            raise ValueError(f"Event validation failed: {errors}")
        return event

    def _normalize_ids_processor(self, event: LearningEvent) -> LearningEvent:
        import json, os as _os
        _aid_map = {}
        _ap = _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "..", "knowledge", "ability_id_aliases.json")
        try:
            with open(_ap, "r", encoding="utf-8") as _f:
                _aid_map = {m["old_id"]: m["canonical_id"] for m in json.load(_f).get("mappings", [])}
        except: pass
        def resolve_ability_id(aid): return _aid_map.get(aid, aid)
        if event.context and event.context.ability_ids:
            event.context.ability_ids = [resolve_ability_id(a) for a in event.context.ability_ids]
        return event

    def _enrich_context_processor(self, event: LearningEvent) -> LearningEvent:
        if event.context and not event.context.class_id:
            event.context.class_id = "default"
        return event

    def add_processor(self, name: str, fn: Callable[[LearningEvent], LearningEvent]):
        self.processors.append(Processor(name=name, fn=fn))

    def add_projector(self, fn: Callable[[LearningEvent], None]):
        self.projectors.append(fn)

    def emit(self, event: LearningEvent, idempotency_key: str = "") -> bool:
        """Emit a LearningEvent through the processor pipeline to the store."""
        try:
            for proc in self.processors:
                if proc.enabled:
                    event = proc.fn(event)

            inserted = self.store.insert_event(event, idempotency_key)
            if inserted:
                for projector in self.projectors:
                    try:
                        projector(event)
                    except Exception as e:
                        logger.error(f"Projector error: {e}")

            return inserted
        except Exception as e:
            logger.error(f"EventBus emit error for event {event.event_id}: {e}")
            return False

    def emit_raw(self, raw: Dict[str, Any], idempotency_key: str = "") -> bool:
        from .event_schema import normalize_event
        event = normalize_event(raw)
        return self.emit(event, idempotency_key)


# Singleton
_event_bus: Optional[EventBus] = None

def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
