# -*- coding: utf-8 -*-
"""LLM-assisted skill extraction module.
Uses LLM to extract implicit skills from JD text that rule-based lexicon might miss.
LLM only generates candidates - never directly modifies the graph.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.llm_client import chat_completion, is_configured

_SYSTEM_PROMPT = """你是一个机电岗位能力分析助手。你的任务是从岗位描述文本中提取技能要求。

对于每条技能，输出以下JSON格式：
{
  "skill_name": "PLC调试",
  "ability_dimension": "PLC控制调试",
  "matched_dimension_id": "plc_control_debug",
  "confidence": 0.85,
  "evidence_snippet": "负责PLC程序调试与现场总线配置",
  "implicit": false
}

ability_dimension 取值范围：电气安全、传感器信号、PLC控制调试、排故诊断、通用
matched_dimension_id 取值范围：electrical_safety_diagram、sensor_signal_acquisition、plc_control_debug、equipment_inspection_troubleshooting

implicit=true 表示该技能没有被直接提到，但可以从上下文推断出来（例如：提到"处理设备异常报警"应推断出排故能力）

只输出JSON数组，不要输出任何解释文字。"""


def llm_extract_skills(jd_text, ability_nodes=None):
    """Use LLM to extract skills from JD text.
    Returns a list of validated candidate dicts.
    Returns empty list if LLM is not configured.
    """
    if not is_configured():
        return []

    if not jd_text or len(jd_text.strip()) < 10:
        return []

    try:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "岗位描述：\n" + jd_text[:2000]}
        ]
        raw = chat_completion(messages, temperature=0.1, timeout=30)
        candidates = _parse_response(raw)
        if ability_nodes:
            candidates = _validate_and_map(candidates, ability_nodes)
        return candidates[:10]  # Limit to 10 candidates
    except Exception as e:
        return [{"error": str(e)}]


def _parse_response(raw):
    """Parse LLM response text into structured candidates"""
    text = (raw or "").strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Try JSON parse
    try:
        candidates = json.loads(text)
        if isinstance(candidates, list):
            return candidates
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in text
    arr_start = text.find("[")
    arr_end = text.rfind("]")
    if arr_start >= 0 and arr_end > arr_start:
        try:
            candidates = json.loads(text[arr_start:arr_end + 1])
            if isinstance(candidates, list):
                return candidates
        except json.JSONDecodeError:
            pass

    return []


def _validate_and_map(candidates, ability_nodes):
    """Validate LLM candidates and map to ability nodes"""
    if not candidates or not ability_nodes:
        return candidates

    validated = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        skill_name = c.get("skill_name", "")
        confidence = c.get("confidence", 0.3)
        dim_id = c.get("matched_dimension_id", "")
        implicit = c.get("implicit", False)

        if not skill_name:
            continue

        confidence = max(0.1, min(0.95, float(confidence)))

        # Find matching ability node
        matched_node = None
        for node in ability_nodes:
            node_name = node.get("name", "")
            node_desc = node.get("description", "")
            node_dims = node.get("radar_dimension_ids", [])
            if (dim_id and dim_id in node_dims) or skill_name in node_name:
                matched_node = node
                break

        validated.append({
            "skill_name": skill_name,
            "ability_id": matched_node["id"] if matched_node else None,
            "ability_name": matched_node.get("name") if matched_node else None,
            "confidence": confidence,
            "original_dimension": dim_id,
            "implicit": implicit,
            "source": "llm_extraction",
        })

    return validated


def extract_with_both(jd_text, ability_nodes=None):
    """Run both rule-based and LLM extraction, merge results.
    Rule results keep original confidence.
    LLM results have confidence reduced by 0.15.
    Returns merged, deduplicated list.
    """
    from scripts.pipeline.cleaner import extract_skill_spans, map_skills_to_abilities
    if ability_nodes is None:
        from scripts.pipeline.cleaner import load_ability_nodes
        ability_nodes = load_ability_nodes()

    # Rule-based
    skills = extract_skill_spans(jd_text)
    rule_results = map_skills_to_abilities(skills, ability_nodes)
    for r in rule_results:
        max_score = 5.0
        r["confidence"] = min(0.95, (r.get("score", 1) or 1) / max_score * 0.8)
        r["source"] = "rule_lexicon"
        r["is_rule"] = True

    for r in rule_results:
        r["source"] = "rule_lexicon"

    # LLM
    llm_results = llm_extract_skills(jd_text, ability_nodes)
    for r in llm_results:
        r["confidence"] = max(0.1, r.get("confidence", 0.5) - 0.15)

    # Merge: LLM results that match a rule result keep higher confidence
    merged = list(rule_results)
    seen_ids = {r["ability_id"] for r in rule_results if r.get("ability_id")}

    for lr in llm_results:
        aid = lr.get("ability_id")
        if aid and aid not in seen_ids:
            merged.append(lr)
            seen_ids.add(aid)

    return sorted(merged, key=lambda x: -x.get("confidence", 0))[:10]