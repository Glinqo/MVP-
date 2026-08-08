"""Outcome Integration - connects Outcome Engine to Evidence Store."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from .outcome_model import OutcomeEvaluator, InterventionOutcome


class OutcomeIntegrator:
    """Snapshot-based outcome evaluation bridged to Evidence Engine."""

    def __init__(self):
        self.evaluator = OutcomeEvaluator()

    def capture_pre_snapshot(self, student_id: str, ability_id: str,
                              mastery: float, error_count: int,
                              intervention_id: str = "", treatment: str = "") -> Dict[str, Any]:
        return {
            "student_id": student_id,
            "ability_id": ability_id,
            "mastery": mastery,
            "error_count": error_count,
            "intervention_id": intervention_id,
            "treatment": treatment,
            "context": {"time": datetime.now(timezone.utc).isoformat()},
            "snapshot_type": "pre",
        }

    def capture_post_snapshot(self, student_id: str, ability_id: str,
                               mastery: float, error_count: int,
                               intervention_id: str = "") -> Dict[str, Any]:
        return {
            "student_id": student_id,
            "ability_id": ability_id,
            "mastery": mastery,
            "error_count": error_count,
            "intervention_id": intervention_id,
            "snapshot_type": "post",
        }

    def evaluate_from_snapshots(self, pre: Dict, post: Dict,
                                 pre_events: List[Dict] = None,
                                 post_events: List[Dict] = None) -> InterventionOutcome:
        pre_state = {
            "student_id": pre.get("student_id", ""),
            "intervention_id": pre.get("intervention_id", ""),
            "mastery": pre.get("mastery", 0),
            "treatment": pre.get("treatment", ""),
            "context": pre.get("context", {}),
        }
        post_state = {
            "student_id": post.get("student_id", ""),
            "mastery": post.get("mastery", 0),
        }
        return self.evaluator.evaluate(pre_state, post_state, pre_events or [], post_events or [])

    def summary_stats(self, outcomes: List[InterventionOutcome]) -> Dict[str, Any]:
        total = len(outcomes)
        if total == 0: return {"total": 0}
        improved = sum(1 for o in outcomes if o.outcome == "improved")
        no_change = sum(1 for o in outcomes if o.outcome == "no_change")
        worsened = sum(1 for o in outcomes if o.outcome == "worsened")
        insufficient = sum(1 for o in outcomes if o.outcome == "insufficient_evidence")
        avg_delta = sum(o.mastery_delta for o in outcomes) / total
        return {
            "total": total, "improved": improved, "no_change": no_change,
            "worsened": worsened, "insufficient_evidence": insufficient,
            "avg_mastery_delta": round(avg_delta, 3),
            "improvement_rate": round(improved / total, 2),
        }
