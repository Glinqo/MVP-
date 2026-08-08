"""Diagnostic Pattern Classifiers - CTAT-inspired.

6 high-value, interpretable patterns from V2-0 plan:
  skipped_prerequisite, premature_action, repeated_ineffective_action,
  unsafe_action, wrong_branch, closure_missing.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from .expert_graph import ExpertBehaviorGraph, get_expert_graph


@dataclass
class DiagnosticPattern:
    pattern_id: str
    pattern_type: str  # one of the 6 types
    student_id: str = ""
    scenario_id: str = ""
    expected_state: str = ""
    actual_action: str = ""
    missing_prerequisites: List[str] = field(default_factory=list)
    ability_ids: List[str] = field(default_factory=list)
    severity: str = "medium"   # low / medium / high
    evidence_refs: List[str] = field(default_factory=list)
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PatternClassifier:
    def __init__(self, graph: ExpertBehaviorGraph = None):
        self.graph = graph or get_expert_graph("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    def classify(self, current_state: str, action: str, history: List[str] = None,
                 student_id: str = "", scenario_id: str = "") -> Optional[DiagnosticPattern]:
        history = history or []
        pattern_type = self._classify_pattern(current_state, action, history)
        if not pattern_type:
            return None

        return DiagnosticPattern(
            pattern_id=f"PAT_{student_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            pattern_type=pattern_type,
            student_id=student_id,
            scenario_id=scenario_id,
            expected_state=current_state,
            actual_action=action,
            severity=self._severity(pattern_type),
            ability_ids=self._get_ability_ids(current_state),
            description=self._describe(pattern_type, current_state, action),
            evidence_refs=[],
        )

    def _classify_pattern(self, current_state: str, action: str, history: List[str]) -> Optional[str]:
        node = self.graph.get_node(current_state)
        if node and node.safety_required and "power_off" not in str(action).lower():
            return "unsafe_action"
        if action in ("edit_program", "modify_program"):
            return "premature_action"
        if node and action not in node.next_states:
            return "wrong_branch"
        if history.count(action) >= 3:
            return "repeated_ineffective_action"
        if node and node.safety_required and "complete" == action:
            return "closure_missing"
        return None

    def _severity(self, pattern_type: str) -> str:
        return {"unsafe_action": "high", "premature_action": "high",
                "wrong_branch": "medium", "closure_missing": "medium",
                "skipped_prerequisite": "high", "repeated_ineffective_action": "low"}.get(pattern_type, "medium")

    def _get_ability_ids(self, state_id: str) -> List[str]:
        node = self.graph.get_node(state_id)
        return node.ability_ids if node else []

    def _describe(self, pattern_type: str, state: str, action: str) -> str:
        desc_map = {
            "premature_action": f"在{state}状态下提前执行了{action}",
            "unsafe_action": f"在需要安全确认的{state}状态下执行了未断电操作",
            "wrong_branch": f"在{state}下选择了错误分支{action}",
            "closure_missing": f"缺少闭环验证操作",
            "repeated_ineffective_action": f"重复执行了无效操作{action}",
            "skipped_prerequisite": f"跳过了{state}的必要前置步骤",
        }
        return desc_map.get(pattern_type, f"在{state}下执行{action}")
