"""V2 Learner State Contract & Models.

Each student × ability maintains: mastery, uncertainty, trend, status.
Priority: Rule V2 -> pyBKT -> CDM/Deep KT (experimental).
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AbilityState:
    ability_id: str
    ability_name: str = ""
    mastery: float = 0.0          # 0.0 - 1.0
    uncertainty: float = 0.0       # 0.0 - 1.0
    trend: str = "unknown"         # improving / stable / declining / unknown
    status: str = "unknown"        # mastered / learning / weak / unknown
    evidence_count: int = 0
    evidence_refs: List[str] = field(default_factory=list)
    model: str = "rule_v2"
    model_version: str = "1.0"
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ability_id": self.ability_id,
            "ability_name": self.ability_name,
            "mastery": self.mastery,
            "uncertainty": self.uncertainty,
            "trend": self.trend,
            "status": self.status,
            "evidence_count": self.evidence_count,
            "evidence_refs": self.evidence_refs,
            "model": self.model,
            "model_version": self.model_version,
            "last_updated": self.last_updated,
        }


@dataclass
class LearnerState:
    student_id: str
    job_role: str = ""
    abilities: Dict[str, AbilityState] = field(default_factory=dict)
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def get_ability(self, ability_id: str) -> Optional[AbilityState]:
        return self.abilities.get(ability_id)

    def update_ability(self, ability_id: str, **kwargs):
        if ability_id not in self.abilities:
            self.abilities[ability_id] = AbilityState(ability_id=ability_id)
        state = self.abilities[ability_id]
        for k, v in kwargs.items():
            if hasattr(state, k):
                setattr(state, k, v)
        state.last_updated = datetime.now(timezone.utc).isoformat()
        self.last_updated = state.last_updated

    def to_dict(self) -> Dict[str, Any]:
        return {
            "student_id": self.student_id,
            "job_role": self.job_role,
            "abilities": {k: v.to_dict() for k, v in self.abilities.items()},
            "last_updated": self.last_updated,
        }


class LearnerStateModel:
    """Abstract base for learner state estimation models."""
    def update(self, state: LearnerState, evidence: List[Dict[str, Any]]) -> LearnerState:
        raise NotImplementedError
    def predict(self, state: LearnerState, ability_id: str) -> float:
        raise NotImplementedError


class RuleBasedStateModel(LearnerStateModel):
    """Deterministic rule-based state model using evidence accumulation."""

    def update(self, state: LearnerState, evidence: List[Dict[str, Any]]) -> LearnerState:
        for ev in evidence:
            aid = ev.get("ability_id") or (ev.get("context") or {}).get("ability_ids", [None])[0]
            if not aid:
                continue
            correct = (ev.get("result") or {}).get("outcome") in ("correct", "completed", True)
            current = state.get_ability(aid)
            mastery = (current.mastery if current else 0.0)
            count = (current.evidence_count if current else 0) + 1
            new_mastery = self._update_mastery(mastery, correct, count)
            state.update_ability(
                aid,
                mastery=new_mastery,
                evidence_count=count,
                trend=self._compute_trend(mastery, new_mastery),
                status=self._compute_status(new_mastery, count),
                evidence_refs=(current.evidence_refs if current else []) + [ev.get("event_id", "")],
            )
        return state

    def _update_mastery(self, current: float, correct: bool, count: int) -> float:
        alpha = 1.0 / max(1, count)
        target = 1.0 if correct else 0.0
        new = current + alpha * (target - current)
        return min(1.0, max(0.0, new))

    def _compute_trend(self, old: float, new: float) -> str:
        delta = new - old
        if delta > 0.05: return "improving"
        if delta < -0.05: return "declining"
        return "stable"

    def _compute_status(self, mastery: float, count: int) -> str:
        if count < 3: return "unknown"
        if mastery >= 0.85: return "mastered"
        if mastery >= 0.60: return "learning"
        return "weak"

    def predict(self, state: LearnerState, ability_id: str) -> float:
        s = state.get_ability(ability_id)
        return s.mastery if s else 0.0


# Singleton
_state_model: Optional[LearnerStateModel] = None

def get_state_model() -> LearnerStateModel:
    global _state_model
    if _state_model is None:
        _state_model = RuleBasedStateModel()
    return _state_model
