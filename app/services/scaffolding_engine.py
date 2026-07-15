"""
Scaffolding engine: determines hint level and generates hints based on
student performance deviations.

Hint levels:
- level_0: no hint (student is on track)
- level_1: nudge toward goal (remind what to focus on)
- level_2: suggest which fault layer to check
- level_3: suggest what evidence to gather next
- level_4: explicit next action suggestion (or safety block)

Escalation rules (deterministic, no LLM):
- First ordinary deviation -> level_1
- Two consecutive same-type deviations -> level_2
- Three consecutive deviations or repeated low-value -> level_3
- Safety violation -> immediate level_4, block dangerous action
"""

from .troubleshooting_constraints import (
    check_safety_constraints,
    check_action_preconditions,
    check_hypothesis_support,
    check_completion_constraints,
    count_consecutive_deviations,
    get_deviation_trend,
    SAFETY_GATE_ACTIONS,
    UNSAFE_ACTIONS,
)


# --- Hint templates (content comes from model data) ---

HINT_TEMPLATES = {
    1: {
        "preamble": "提示：",
        "templates": {
            "safety_first": "排故前请先确认安全状态。",
            "focus_on_evidence": "请关注已有的现场证据，不要过早下结论。",
            "check_remaining": "还有 {count} 个故障假设未排除，请继续收集证据。",
            "common_error": "常见错误：{error}",
        }
    },
    2: {
        "preamble": "方向提示：",
        "templates": {
            "check_safety_layer": "当前问题在 {layer} 层，请先确认安全条件。",
            "check_hardware_first": "传感器灯不亮时，优先排查传感器侧（供电/检测距离/目标）。",
            "check_common_terminal": "PLC 输入灯不亮时，优先检查公共端接线。",
            "check_address_mapping": "输入灯已亮但监控不变时，核对 I/O 地址映射。",
            "layered_approach": "请按 {layer1} -> {layer2} -> {layer3} 的分层顺序排查。",
        }
    },
    3: {
        "preamble": "步骤提示：",
        "templates": {
            "need_evidence": "当前需要获取的证据：{evidence}",
            "suggest_action": "建议下一步：{action_label}",
            "skip_step": "你跳过了 {step} 步骤，这可能影响排故效率。",
            "repeated_warning": "你已经重复执行了 {action_label}，建议转向其他检查。",
        }
    },
    4: {
        "preamble": "⚠ 安全警告：",
        "templates": {
            "safety_block": "此动作违反安全规程，已被阻止。请先断电并确认急停、气源、电源状态。",
            "urgent_redirect": "请立即停止当前操作，执行安全检查：{action_label}。",
        }
    }
}


# --- Hint level determination ---

def determine_hint_level(trace_result, student_trace, action_category, state_flags):
    """
    Determine the appropriate scaffolding hint level.

    Rules (deterministic):
    - Safety violation -> level_4 (block)
    - 3+ consecutive deviations -> level_3
    - Repeated low-value action -> level_3
    - 2 consecutive same-type deviations -> level_2
    - 1 ordinary deviation -> level_1
    - On track -> level_0

    Returns:
        (level, reason_string)
    """
    classification = action_category

    # Safety: immediate level_4 and block
    if classification == "unsafe":
        return 4, "检测到不安全动作，立即阻止"

    # Repeated low-value
    if classification == "repeated_low_value":
        return 3, f"重复执行低价值动作"

    # Premature or unsupported_hypothesis
    if classification in ("premature", "unsupported_hypothesis"):
        consecutive = count_consecutive_deviations(student_trace) + 1  # +1 for current action
        if consecutive >= 3:
            return 3, f"连续 {consecutive} 次偏差动作"
        elif consecutive >= 2:
            return 2, f"连续 {consecutive} 次同类偏差"
        else:
            return 1, "动作时机不当，请重新评估"

    # Closure missing
    if classification == "closure_missing":
        return 2, "修复后缺少闭环验证"

    # Valid but inefficient
    if classification == "valid_but_inefficient":
        return 1, "动作有效但存在更高效路径"

    # On track
    return 0, "动作合理，无需提示"


# --- Hint generation ---

def generate_hint(model, trace_result, student_trace, state_flags, state_id, action_id):
    """
    Generate a structured scaffolding hint.

    Returns:
        dict with: level, message, reason, blocked (bool)
    """
    classification = trace_result.get("classification", "optimal")
    is_unsafe = classification == "unsafe"

    # Check safety constraints
    safety = check_safety_constraints(state_flags, action_id, is_unsafe)

    # Check preconditions
    missing_preconditions = check_action_preconditions(model, action_id, state_flags)

    # Check hypothesis support
    hypothesis_check = check_hypothesis_support(model, action_id, state_flags, state_id)

    # Determine level
    level, reason = determine_hint_level(trace_result, student_trace, classification, state_flags)

    # Safety override
    if safety["blocked"]:
        level = 4
        reason = "安全违规，动作被阻止"

    # Generate message
    message = _build_hint_message(model, level, reason, trace_result, state_flags,
                                   state_id, action_id, missing_preconditions,
                                   hypothesis_check)

    return {
        "level": level,
        "message": message,
        "reason": reason,
        "blocked": safety["blocked"],
        "safety_check": safety,
        "precondition_check": {"missing": missing_preconditions},
        "hypothesis_check": hypothesis_check,
    }


def _build_hint_message(model, level, reason, trace_result, state_flags, state_id,
                        action_id, missing_preconditions, hypothesis_check):
    """Build the hint message text from templates and model data."""

    if level == 0:
        return None

    templates = HINT_TEMPLATES.get(level, HINT_TEMPLATES[1])

    # Level 4: safety block
    if level == 4:
        if trace_result.get("classification") == "unsafe":
            return templates["templates"]["safety_block"]
        return templates["templates"]["urgent_redirect"].format(action_label="确认安全状态")

    # Level 3: specific step guidance
    if level == 3:
        # Check if it's a repeated action
        if trace_result.get("repeated_action"):
            action_label = _action_label(model, action_id)
            return templates["templates"]["repeated_warning"].format(action_label=action_label or action_id)

        # Suggest next optimal action
        current_strategy_id = trace_result.get("matched_strategy_id")
        if current_strategy_id:
            strategy = _find_strategy(model, current_strategy_id)
            if strategy:
                done_action_ids = [e.get("action_id") for e in student_trace]
                optimal_seq = strategy.get("optimal_sequence", [])
                for aid in optimal_seq:
                    if aid not in done_action_ids:
                        action_label = _action_label(model, aid)
                        return templates["templates"]["suggest_action"].format(action_label=action_label or aid)

        # General evidence suggestion
        if missing_preconditions:
            return f"请先完成前置条件：{'、'.join(missing_preconditions)}"

        return f"当前排故效率可优化。{reason}"

    # Level 2: direction
    if level == 2:
        # Check remaining hypotheses
        state = None
        for s in model.get("states", []):
            if s["id"] == state_id:
                state = s
                break
        if state:
            remaining = state.get("remaining_hypotheses", [])
            if remaining:
                count = len(remaining)
                return f"?? {count} ?????????????????"

        return f"建议重新审视排故方向。{reason}"

    # Level 1: gentle nudge
    if level == 1:
        if not state_flags.get("safety_confirmed") and not state_flags.get("power_off_safety"):
            return templates["templates"]["safety_first"]
        return f"{reason}。请继续按排故逻辑推进。"

    return reason


def _action_label(model, action_id):
    """Get the human-readable label for an action."""
    for action in model.get("diagnostic_actions", []):
        if action["id"] == action_id:
            return action.get("label", action_id)
    return action_id


def _find_strategy(model, strategy_id):
    """Find a strategy by ID."""
    for s in model.get("strategies", []):
        if s["id"] == strategy_id:
            return s
    return None
