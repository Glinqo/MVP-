"""Expert Behavior Graph for Scenario Training.

Models the correct troubleshooting sequence as a directed graph.
Each node represents a state/checkpoint; edges represent correct actions.
"""

from typing import Any, Dict, List, Optional


class ExpertNode:
    def __init__(self, state_id: str, label: str = "", description: str = "",
                 ability_ids: List[str] = None, safety_required: bool = False):
        self.state_id = state_id
        self.label = label
        self.description = description
        self.ability_ids = ability_ids or []
        self.safety_required = safety_required
        self.next_states: Dict[str, "ExpertNode"] = {}

    def add_edge(self, action_id: str, target: "ExpertNode"):
        self.next_states[action_id] = target


class ExpertBehaviorGraph:
    def __init__(self, scenario_id: str):
        self.scenario_id = scenario_id
        self.nodes: Dict[str, ExpertNode] = {}
        self.start_state: Optional[ExpertNode] = None

    def add_node(self, node: ExpertNode):
        self.nodes[node.state_id] = node
        if self.start_state is None:
            self.start_state = node

    def get_node(self, state_id: str) -> Optional[ExpertNode]:
        return self.nodes.get(state_id)

    def get_expected_action(self, current_state_id: str) -> Optional[str]:
        node = self.nodes.get(current_state_id)
        if node and node.next_states:
            return list(node.next_states.keys())[0]
        return None

    def get_available_actions(self, current_state_id: str) -> List[str]:
        node = self.nodes.get(current_state_id)
        return list(node.next_states.keys()) if node else []

    def is_correct_action(self, current_state_id: str, action_id: str) -> bool:
        node = self.nodes.get(current_state_id)
        return action_id in node.next_states if node else False


def build_default_graph() -> ExpertBehaviorGraph:
    g = ExpertBehaviorGraph("SCN_SENSOR_LED_ON_PLC_LED_OFF")

    s1 = ExpertNode("CHECK_SIGNAL_CHAIN", "信号链路检查",
                    "检查传感器到PLC输入端信号链路",
                    ["tr_signal_chain", "pl_fault_diag"])
    s2 = ExpertNode("CHECK_COMMON_TERMINAL", "公共端检查",
                    "检查PLC输入公共端与传感器输出线",
                    ["pl_common_terminal", "sn_wiring_diag"])
    s3 = ExpertNode("SAFE_REPAIR", "安全修复与验证",
                    "断电后修复并完成三联验证",
                    ["es_safety_rules", "es_power_isolation"], safety_required=True)
    s4 = ExpertNode("COMPLETED", "完成", "故障排除完成")

    s1.add_edge("check_signal_link", s2)
    s2.add_edge("check_common_terminal", s3)
    s3.add_edge("safe_repair_and_verify", s4)

    g.add_node(s1)
    g.add_node(s2)
    g.add_node(s3)
    g.add_node(s4)
    g.start_state = s1
    return g


# Singleton
_graphs: Dict[str, ExpertBehaviorGraph] = {}

def get_expert_graph(scenario_id: str) -> ExpertBehaviorGraph:
    if scenario_id not in _graphs:
        _graphs[scenario_id] = build_default_graph()
    return _graphs[scenario_id]
