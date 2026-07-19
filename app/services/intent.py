"""
Intent classifier for the conversation pipeline.

LLM-first classification with keyword-based fallback.
Supports 6 intents for the MVP:
  diagnosis      — 故障排查/实训问题
  knowledge_qa   — 知识问答/概念解释
  quiz           — 出题/自测
  graph          — 能力图谱/岗位能力查询
  learning_path  — 学习路径/训练计划
  clarify        — 信息不足需追问
"""

import json
from pathlib import Path

from .llm_client import LLMError, chat_completion, is_configured

ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = ROOT / "prompts" / "intent_classifier_prompt.md"


# ── keyword fallback ──────────────────────────────────────────────

# (intent, [(keyword, weight), ...])
# Strong indicators (weight 2): unmistakable intent signals
# Weak indicators (weight 1): common but ambiguous terms
KEYWORD_RULES = [
    ("quiz", [
        ("出题", 2), ("出几道", 2), ("帮我出", 2), ("给我几道", 2),
        ("做题", 1), ("自测", 1), ("题目", 1), ("练习", 1),
        ("测试", 1), ("考题", 1), ("练习题", 1), ("生成题目", 1),
        ("道题", 1),
    ]),
    ("graph", [
        ("能力图谱", 2), ("岗位能力", 2), ("图谱", 1), ("能力图", 1),
        ("能力结构", 1), ("需要哪些能力", 1), ("查看能力", 1), ("岗位要求", 1),
    ]),
    ("learning_path", [
        ("学习路径", 2), ("学习计划", 2), ("培养方案", 2), ("训练单", 2),
        ("下一步", 1), ("训练计划", 1), ("该怎么学", 1), ("怎么补", 1),
        ("补什么", 1), ("今日训练", 1),
    ]),
    ("knowledge_qa", [
        ("什么是", 2), ("解释一下", 2), ("的区别", 2), ("介绍一下", 2),
        ("讲讲", 2), ("是什么意思", 2), ("有哪些", 2), ("怎么", 1),
        ("区别", 1), ("概念", 1), ("定义", 1), ("为什么", 1),
    ]),
    ("diagnosis", [
        ("排查", 1), ("故障", 1), ("不亮", 1), ("不动", 1),
        ("异常", 1), ("没反应", 1), ("不工作", 1), ("灯亮", 1),
        ("接线", 1), ("传感器", 1), ("气缸", 1), ("监控", 1),
        ("动作", 1), ("调试", 1),
        # Low-weight technical terms that appear in many contexts
        ("plc", 0.3), ("PLC", 0.3), ("信号", 0.3), ("输入", 0.3),
        ("问题", 0.2), ("错误", 0.2),
    ]),
    ("clarify", [
        ("帮我看看", 2), ("能帮我看看", 2), ("帮我看一下", 2),
        ("怎么办", 1), ("不知道", 1), ("不懂", 1), ("不清楚", 1),
        ("不会弄", 1),
    ]),
]


def _score_keywords(text):
    """Score each intent against weighted keywords, return best match."""
    raw = str(text or "")
    scores = {}
    for intent, keywords in KEYWORD_RULES:
        scores[intent] = sum(
            weight for kw, weight in keywords if kw in raw or kw.lower() in raw.lower()
        )
    # When nothing matches, the input is inherently vague → clarify
    if all(v < 0.5 for v in scores.values()):
        return "clarify"
    best = max(scores, key=scores.get)
    # if diagnosis is best but another intent is close, prefer the other
    if best == "diagnosis":
        others = {k: v for k, v in scores.items() if k != "diagnosis"}
        runner_up = max(others, key=others.get)
        if others[runner_up] > 0 and scores["diagnosis"] - others[runner_up] < 0.5:
            return runner_up
    return best


# ── LLM classification ────────────────────────────────────────────

def _load_prompt():
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return ""


def _build_classification_messages(message, history=None):
    """Build messages array for intent classification call."""
    prompt = _load_prompt()
    history_text = ""
    if history:
        recent = history[-3:]
        history_text = "\n".join(
            f"{item.get('role', 'user')}: {item.get('content', '')[:120]}"
            for item in recent
        )
    system = (
        f"{prompt}\n\n"
        "重要：你只输出 JSON，不要输出任何解释、markdown 或额外文字。"
        'JSON 顶层包含 intent、confidence、reason、slots 字段。'
    )
    user = (
        f"对话历史（最近3轮）：\n{history_text or '无'}\n\n"
        f"当前用户输入：{message}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_llm_response(raw):
    """Extract JSON from LLM response (may include markdown fences)."""
    text = str(raw or "").strip()
    # strip ```json fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # remove first line (```json) and last line (```)
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to find JSON object in text
        brace_open = text.find("{")
        brace_close = text.rfind("}")
        if brace_open != -1 and brace_close > brace_open:
            try:
                return json.loads(text[brace_open:brace_close + 1])
            except json.JSONDecodeError:
                pass
        return None


def classify_intent(message, history=None, context=None):
    """
    Classify user message into one of 6 intents.

    Returns:
        {
            "intent": str,         # diagnosis | knowledge_qa | quiz | graph | learning_path | clarify
            "confidence": float,   # 0.0–1.0
            "reason": str,         # explanation
            "source": str,         # "llm" | "keyword"
        }
    """
    # Try LLM first
    if is_configured() and message.strip():
        try:
            messages = _build_classification_messages(message, history)
            raw = chat_completion(messages, temperature=0.0, timeout=15)
            parsed = _parse_llm_response(raw)
            if parsed and parsed.get("intent") in {
                "diagnosis", "knowledge_qa", "quiz", "graph",
                "learning_path", "clarify",
            }:
                return {
                    "intent": parsed["intent"],
                    "confidence": float(parsed.get("confidence", 0.8)),
                    "reason": parsed.get("reason", ""),
                    "slots": parsed.get("slots", {}),
                    "source": "llm",
                }
        except (LLMError, ValueError, OSError):
            pass  # fall through to keyword

    # Keyword fallback
    intent = _score_keywords(message)
    return {
        "intent": intent,
        "confidence": 0.6,
        "reason": f"关键词匹配 → {intent}",
        "slots": {},
        "source": "keyword",
    }
