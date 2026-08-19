"""Intervention Outcome Model - Pre/Post + Evidence."""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class InterventionOutcome:
    outcome_id: str
    intervention_id: str
    student_id: str
    pre_mastery: float = 0.0
    post_mastery: float = 0.0
    mastery_delta: float = 0.0
    pre_error_count: int = 0
    post_error_count: int = 0
    completion_rate: float = 0.0
    outcome: str = "unknown"  # improved / no_change / worsened / insufficient_evidence
    confidence: float = 0.0
    treatment: str = ""       # for causal analysis
    context: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OutcomeEvaluator:
    def evaluate(self, pre_state: Dict[str, Any], post_state: Dict[str, Any],
                 pre_events: List[Dict] = None, post_events: List[Dict] = None) -> InterventionOutcome:
        pre_m = pre_state.get("mastery", 0.0)
        post_m = post_state.get("mastery", 0.0)
        pre_err = len([e for e in (pre_events or []) if e.get("result", {}).get("outcome") == "incorrect"])
        post_err = len([e for e in (post_events or []) if e.get("result", {}).get("outcome") == "incorrect"])
        delta = post_m - pre_m

        outcome = "unknown"
        if post_events and len(post_events) >= 3:
            if delta > 0.08:
                outcome = "improved"
            elif delta < -0.05:
                outcome = "worsened"
            else:
                outcome = "no_change"
        elif not post_events:
            outcome = "insufficient_evidence"

        confidence = min(1.0, len(post_events or []) * 0.15)

        return InterventionOutcome(
            outcome_id=f"OUT_{pre_state.get('student_id','')}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            intervention_id=pre_state.get("intervention_id", ""),
            student_id=pre_state.get("student_id", ""),
            pre_mastery=round(pre_m, 3),
            post_mastery=round(post_m, 3),
            mastery_delta=round(delta, 3),
            pre_error_count=pre_err,
            post_error_count=post_err,
            completion_rate=1.0 if post_events and len(post_events) >= 3 else 0.5,
            outcome=outcome,
            confidence=round(confidence, 2),
            treatment=pre_state.get("treatment", ""),
            context=pre_state.get("context", {}),
        )

    def batch_evaluate(self, pre_states: List[Dict], post_states: List[Dict],
                       pre_events_map: Dict = None, post_events_map: Dict = None) -> List[InterventionOutcome]:
        results = []
        for ps in post_states:
            sid = ps.get("student_id", "")
            pre = next((p for p in pre_states if p.get("student_id") == sid), {})
            pre_ev = (pre_events_map or {}).get(sid, [])
            post_ev = (post_events_map or {}).get(sid, [])
            results.append(self.evaluate(pre, ps, pre_ev, post_ev))
        return results
