"""pyBKT Adapter - Bayesian Knowledge Tracing.

Wraps pyBKT behind LearnerStateModel interface.
Priority: Rule V2 -> pyBKT -> CDM/Deep KT (experimental).
Fallback to Rule Model when pyBKT is not installed or training is insufficient.
"""

from typing import Any, Dict, List, Optional
from .learner_state import LearnerState, LearnerStateModel, AbilityState


class BKTAdapter(LearnerStateModel):
    """Adapter wrapping pyBKT with fallback to RuleBasedStateModel."""

    def __init__(self):
        self.rule_fallback = None
        self._bkt_available = False
        try:
            from pyBKT.models import Model
            self.Model = Model
            self._bkt_available = True
        except ImportError:
            pass

    def update(self, state: LearnerState, evidence: List[Dict[str, Any]]) -> LearnerState:
        if self._bkt_available and len(evidence) >= 10:
            return self._bkt_update(state, evidence)
        # Fallback to rule-based
        if self.rule_fallback is None:
            from .learner_state import RuleBasedStateModel
            self.rule_fallback = RuleBasedStateModel()
        return self.rule_fallback.update(state, evidence)

    def _bkt_update(self, state: LearnerState, evidence: List[Dict[str, Any]]) -> LearnerState:
        for ev in evidence:
            aid = ev.get("ability_id") or (ev.get("context") or {}).get("ability_ids", [None])[0]
            if not aid: continue
            correct = 1 if (ev.get("result") or {}).get("outcome") in ("correct", "completed") else 0
            try:
                model = self.Model(seed=42, num_fits=1)
                model.fit(data=[[aid, 1, correct]], defaults=[aid])
                mastery = model.params().get(aid, {}).get("learned", 0.5)
                state.update_ability(aid, mastery=round(min(1.0, max(0.0, mastery)), 2),
                                     model="pybkt", model_version="1.0",
                                     evidence_count=(state.get_ability(aid).evidence_count if state.get_ability(aid) else 0) + 1)
            except Exception:
                if self.rule_fallback is None:
                    from .learner_state import RuleBasedStateModel
                    self.rule_fallback = RuleBasedStateModel()
                return self.rule_fallback.update(state, [ev])
        return state

    def predict(self, state: LearnerState, ability_id: str) -> float:
        s = state.get_ability(ability_id)
        return s.mastery if s else 0.0
