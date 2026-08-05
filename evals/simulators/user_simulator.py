# -*- coding: utf-8 -*-
"""
Deterministic User Simulator for E2E evaluation.

Phase 8 improved version:
- Recognizes 陈述式信息请求 (declarative info requests) not just questions
- No more meaningless "请继续" loops
- Explicit behavior modes: ANSWER_FACT, DONT_KNOW, CONFIRM_CONTINUE, STOP
"""

import re
import hashlib

# ── Slot Answer Templates ──────────────────────────────────────────
_SLOT_ANSWER_TEMPLATES = {
    "sensor_led": {
        "on": ["亮", "传感器灯亮的", "灯亮"],
        "off": ["不亮", "没亮", "灯不亮"],
        "flicker": ["闪", "一会儿亮一会儿不亮"],
    },
    "plc_input_led": {
        "on": ["亮", "PLC灯亮", "输入灯亮"],
        "off": ["不亮", "PLC灯不亮", "没亮"],
        "flicker": ["闪", "跟着闪"],
    },
    "online_monitor": {
        "changed": ["有变化", "变了", "监控有变化"],
        "no_change": ["没变化", "不变", "监控没反应"],
    },
    "cylinder_action": {
        "none": ["不动", "完全不动", "气缸不动"],
    },
    "air_supply": {
        "normal": ["正常", "气源没问题"],
    },
}

_UNKNOWN_ANSWERS = ["不知道", "没看", "不清楚", "不确定", "没注意"]

# ── Slot → Question Pattern Mapping ────────────────────────────────
# Each slot maps to regex patterns that appear when the system is
# REQUESTING information about that slot.
_SLOT_QUESTION_PATTERNS = {
    "sensor_led": [
        "传感器.*灯", "动作灯", "sensor.*led", "灯.*状态",
        "传感器.*状态", "传感器.*亮"
    ],
    "plc_input_led": [
        "plc.*灯", "输入灯", "input.*led", "plc.*指示",
        "PLC.*输入.*亮", "输入.*状态"
    ],
    "online_monitor": [
        "在线监控", "monitor", "监控.*变", "编程软件",
        "监控.*状态", "输入.*变化"
    ],
    "sensor_type": [
        "传感器.*类型", "npn.*pnp", "pnp.*npn", "型号",
        "哪种", "什么类型", "NPN还是PNP"
    ],
    "common_terminal": [
        "公共端", "com", "接法", "COM端", "公共.*接"
    ],
    "power_supply": [
        "电源", "24v", "电压", "dc", "供电",
        "DC.*电源", "开关电源"
    ],
    "cylinder_action": [
        "气缸", "cylinder", "执行.*动作", "气动"
    ],
    "air_supply": [
        "气源", "air", "气压", "供气"
    ],
    "io_mapping": [
        "地址", "映射", "IO.*点", "输入点", "I\d",
        "监控.*地址", "对应.*输入"
    ],
    "valve_coil": [
        "电磁阀", "线圈", "valve", "coil", "电磁.*线圈"
    ],
    "wiring": [
        "接线", "信号线", "连接", "线.*接"
    ],
    "wiring_loose": [
        "松动", "loose", "端子", "接线.*紧固"
    ],
    "dc24v_power": [
        "dc24v", "24v电源", "开关电源", "DC.*V"
    ],
    "program_logic": [
        "程序", "program", "逻辑", "logic", "条件",
        "梯形图", "程序.*条件"
    ],
    "wiring_color": [
        "颜色", "color", "线色", "色标"
    ],
}

# ── Information Request Patterns ───────────────────────────────────
# These patterns indicate the system is requesting information from the user,
# even when there's no explicit "?" mark.
_INFO_REQUEST_PATTERNS = [
    # Direct asks
    r"是什么", r"告诉我", r"知道吗", r"请问", r"怎么回事",
    r"如何", r"怎么", r"什么样", r"哪种",
    # Imperative requests (陈述式信息请求)
    r"请确认", r"请检查", r"请告诉", r"请描述",
    r"先确认", r"先看看", r"先查", r"先检查",
    r"确认一下", r"看一下", r"查一下",
    r"需要知道", r"需要确认", r"需要了解",
    r"下一步.*确认", r"接下来.*确认",
    r"能否.*确认", r"能不能.*看",
    r"告诉我.*状态", r"描述一下",
    r"看看.*有没有", r"看看.*是不是",
    r"检查一下.*是否",
    # Status/state requests
    r"有没有.*变化", r"是否.*变化",
    r"什么.*情况",
]

def _is_information_request(system_message):
    """Detect if system is requesting information, including declarative forms.
    
    Returns True for:
    - Explicit questions (contains ? or ？)
    - Imperative info requests (请确认..., 先看看..., etc.)
    - Status inquiries (现在是什么状态, 有没有变化, etc.)
    """
    msg = str(system_message) if system_message else ""
    
    # Direct question marks
    if "?" in msg or "？" in msg:
        return True
    
    # Pattern-based info requests
    msg_lower = msg.lower()
    for pat in _INFO_REQUEST_PATTERNS:
        if re.search(pat, msg_lower):
            return True
    
    return False


def _detect_asked_slot(system_message):
    """Detect which slot the system is asking about.
    Only called when _is_information_request returned True.
    """
    msg = str(system_message).lower() if system_message else ""
    for slot, patterns in _SLOT_QUESTION_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, msg, re.IGNORECASE):
                return slot
    return None


# ── Main Respond Function ──────────────────────────────────────────

def user_respond(system_message, user_knowledge, user_unknown, answered_slots=None):
    """Generate a deterministic user response.
    
    Behavior modes:
    - ANSWER_FACT: System is asking for a known slot → answer with fact
    - DONT_KNOW: System is asking for an unknown slot → "不知道"
    - CONFIRM_CONTINUE: System gave advice/completed a step → "好的，下一步呢？"
    - STOP: Conversation should end
    
    NEVER returns "请继续" when the system is requesting information.
    """
    answered_slots = answered_slots or set()
    msg = str(system_message).lower() if system_message else ""
    
    # Check if system is requesting information
    if _is_information_request(system_message):
        asked_slot = _detect_asked_slot(system_message)
        
        if asked_slot:
            # Already answered this slot
            if asked_slot in answered_slots:
                return "我已经说过了"
            
            # User KNOWS this slot → answer with fact
            if asked_slot not in user_unknown and asked_slot in user_knowledge:
                val = user_knowledge[asked_slot]
                answers = _SLOT_ANSWER_TEMPLATES.get(asked_slot, {})
                if isinstance(answers, dict) and val in answers:
                    return answers[val][0]
                elif val is not None:
                    return str(val)
            
            # User does NOT know this slot
            if asked_slot in user_unknown:
                return _UNKNOWN_ANSWERS[0]
        
        # System is requesting info but we can't determine which slot
        # Try to match any known slot that's relevant to the message
        for slot, answers in _SLOT_ANSWER_TEMPLATES.items():
            if slot in user_unknown or slot in answered_slots:
                continue
            if slot in user_knowledge:
                slot_keywords = {
                    "sensor_led": ["传感器", "sensor", "灯"],
                    "plc_input_led": ["plc", "输入"],
                    "online_monitor": ["监控", "monitor"],
                }
                keywords = slot_keywords.get(slot, [])
                if any(kw in msg for kw in keywords):
                    val = user_knowledge[slot]
                    if isinstance(answers, dict) and val in answers:
                        return answers[val][0]
        
        # Check if asking about unknown slots
        unknown_labels = {
            "sensor_type": ["类型", "NPN", "PNP", "型号"],
            "common_terminal": ["公共端", "COM", "接法"],
            "io_mapping": ["地址", "映射", "IO"],
            "power_supply": ["电源", "24V", "电压"],
            "wiring": ["接线", "信号线"],
            "valve_coil": ["电磁阀", "线圈"],
            "root_cause": ["根本原因", "原因"],
        }
        for slot in user_unknown:
            labels = unknown_labels.get(slot, [slot])
            if any(label in msg for label in labels):
                return _UNKNOWN_ANSWERS[0]
        
        # Can't figure out what to answer, but system IS asking
        # Default to "不知道" rather than "请继续"
        return _UNKNOWN_ANSWERS[0]
    
    # System is NOT requesting information → it's giving advice/stating status
    # CONFIRM_CONTINUE mode
    continuations = ["好的，下一步呢？", "然后怎么做？", "好的", "明白了，继续"]
    idx = int(hashlib.md5(msg.encode()).hexdigest()[:8], 16) % len(continuations)
    return continuations[idx]


# ── Conversation Simulator ─────────────────────────────────────────

def simulate_conversation(initial_message, scenario, max_turns, chat_fn):
    """Run a simulated conversation between system and deterministic user.
    
    Stops when:
    - System gives an actionable conclusion (contains 排查 or 建议 or 修复)
    - All known slots have been answered AND system is no longer asking
    - Max turns reached
    """
    goal = str(scenario.get("user_goal", "task"))[:20].replace(" ", "_")
    session_id = "e2e-sim-" + goal
    user_knowledge = dict(scenario.get("user_knowledge", {}))
    user_unknown = list(scenario.get("user_unknown", []))
    
    trace = []
    current_message = initial_message
    answered_slots = set()
    consecutive_continues = 0
    
    for turn_num in range(max_turns):
        # User sends message
        trace.append({"role": "user", "content": current_message, "turn": turn_num})
        
        # System responds via real production chat_message
        payload = {
            "session_id": session_id,
            "message": current_message,
            "context": {},
        }
        response = chat_fn(payload)
        assistant_msg = response.get("answer", "")
        trace.append({
            "role": "assistant", "content": assistant_msg, "turn": turn_num,
            "policy_source": response.get("policy_source", ""),
            "tool_results": response.get("tool_results", []),
            "safety_notice": response.get("safety_notice"),
        })
        
        # Generate next user message
        current_message = user_respond(assistant_msg, user_knowledge, user_unknown, answered_slots)
        
        # Track answered slots
        asked = _detect_asked_slot(assistant_msg)
        if asked and _is_information_request(assistant_msg):
            if asked in user_knowledge and asked not in user_unknown:
                answers = _SLOT_ANSWER_TEMPLATES.get(asked, {})
                if isinstance(answers, dict):
                    val = user_knowledge.get(asked)
                    if val in answers and current_message in answers[val]:
                        answered_slots.add(asked)
        
        # ── Stop Conditions ──
        
        # 1. System has given a concrete actionable conclusion
        conclusion_markers = ["排查步骤", "建议", "修复方法", "按以下", "处理方案"]
        if any(marker in assistant_msg for marker in conclusion_markers):
            break
        
        # 2. Consecutive continues from user (no real info exchange in 3+ turns)
        continue_messages = {"好的，下一步呢？", "然后怎么做？", "好的", "明白了，继续", "我已经说过了"}
        if current_message in continue_messages:
            consecutive_continues += 1
        else:
            consecutive_continues = 0
        
        if consecutive_continues >= 3:
            break
        
        # 3. All known slots answered and system stopped asking
        known_slots = set(user_knowledge.keys()) - set(user_unknown)
        system_still_asking = _is_information_request(assistant_msg)
        if turn_num >= 4 and answered_slots >= known_slots and not system_still_asking:
            break
        
        # 4. User doesn't know anything useful (all unknown)
        if turn_num >= 2 and not known_slots:
            break
    
    return trace
