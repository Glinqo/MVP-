# -*- coding: utf-8 -*-
"""LLM-assisted skill extraction for job ability graph updates.

The LLM only returns candidate skills. It never writes graph updates directly.
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.llm_client import chat_completion, config, is_configured


PROMPT_VERSION = "job_skill_extractor_v1"
_LLM_CALL_COUNT = 0

_SYSTEM_PROMPT = """你是一个机电岗位能力分析助手。你的任务是从岗位描述文本中提取技能要求。

对每条技能，只输出下面的 JSON 字段：
{
  "skill_name": "PLC 调试",
  "ability_dimension": "PLC 控制调试",
  "matched_dimension_id": "plc_control_debug",
  "confidence": 0.85,
  "evidence_snippet": "负责 PLC 程序调试与现场总线配置",
  "implicit": false
}

ability_dimension 取值范围：电气安全、传感器信号、PLC 控制调试、排故诊断、通用。
matched_dimension_id 取值范围：electrical_safety_diagram、sensor_signal_acquisition、plc_control_debug、equipment_inspection_troubleshooting。

implicit=true 表示该技能没有被直接提到，但可以从上下文推断出来。
只输出 JSON 数组，不要输出解释文字。"""


def llm_extract_skills(jd_text, ability_nodes=None):
    """Use LLM to extract skill candidates from JD text.

    Returns [] when the LLM is not configured or fails, so the caller can keep
    using the rule-based extractor safely.
    """
    if not jd_text or len(jd_text.strip()) < 10:
        return []

    cfg = config()
    cache_key = _cache_key(jd_text, cfg.get("model", ""))
    cached = _read_cache(cache_key)
    if cached is not None:
        return _finalize_candidates(cached, ability_nodes)

    if not is_configured() or not _consume_call_budget():
        return []

    try:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "岗位描述：\n" + jd_text[:2000]},
        ]
        raw = chat_completion(messages, temperature=0.1, timeout=30)
        candidates = _parse_response(raw)
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate["prompt_version"] = PROMPT_VERSION
                candidate["llm_model"] = cfg["model"]
        _write_cache(cache_key, candidates)
        return _finalize_candidates(candidates, ability_nodes)
    except Exception:
        return []


def _finalize_candidates(candidates, ability_nodes=None):
    if ability_nodes:
        candidates = _validate_and_map(candidates, ability_nodes)
    return candidates[:10]


def _cache_key(jd_text, model):
    base = f"{PROMPT_VERSION}|{model}|{(jd_text or '').strip()[:2000]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _cache_enabled():
    return os.environ.get("LLM_EXTRACT_CACHE", "1").lower() not in {"0", "false", "no"}


def _cache_dir():
    return Path(os.environ.get("LLM_EXTRACT_CACHE_DIR", ROOT / "data" / "evidence" / "llm_cache"))


def _read_cache(key):
    if not _cache_enabled():
        return None
    path = _cache_dir() / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        candidates = data.get("candidates")
        return candidates if isinstance(candidates, list) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(key, candidates):
    if not _cache_enabled():
        return
    try:
        directory = _cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{key}.json"
        path.write_text(
            json.dumps(
                {
                    "prompt_version": PROMPT_VERSION,
                    "candidates": candidates,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        return


def _consume_call_budget():
    global _LLM_CALL_COUNT
    try:
        max_calls = int(os.environ.get("LLM_EXTRACT_MAX_CALLS", "50"))
    except ValueError:
        max_calls = 50
    if max_calls >= 0 and _LLM_CALL_COUNT >= max_calls:
        return False
    _LLM_CALL_COUNT += 1
    return True


def _parse_response(raw):
    """Parse LLM response text into a list of candidate dicts."""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        candidates = json.loads(text)
        if isinstance(candidates, list):
            return candidates
    except json.JSONDecodeError:
        pass

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
    """Validate LLM candidates and map them to known ability nodes."""
    validated = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        skill_name = str(candidate.get("skill_name") or "").strip()
        if not skill_name:
            continue

        try:
            confidence = float(candidate.get("confidence", 0.3))
        except (TypeError, ValueError):
            confidence = 0.3
        confidence = max(0.1, min(0.95, confidence))

        dim_id = str(candidate.get("matched_dimension_id") or "")
        matched_node, match_method, similarity = _best_node_match(skill_name, dim_id, ability_nodes or [])

        if not matched_node:
            continue

        validated.append({
            "skill_name": skill_name,
            "ability_id": matched_node["id"],
            "ability_name": matched_node.get("name"),
            "confidence": confidence,
            "evidence_snippet": candidate.get("evidence_snippet", ""),
            "original_dimension": dim_id,
            "implicit": bool(candidate.get("implicit", False)),
            "source": "llm_extraction",
            "prompt_version": candidate.get("prompt_version", PROMPT_VERSION),
            "llm_model": candidate.get("llm_model", ""),
            "match_method": match_method,
            "similarity_score": similarity,
        })

    return validated


def _best_node_match(skill_name, dim_id, ability_nodes):
    """Map a free-form LLM skill to the closest known ability node.

    Direct name matches stay deterministic.  When an embedding model is
    configured, vector similarity is used as the high-recall path; otherwise
    the local deterministic term scorer remains the safe fallback.
    """
    direct = []
    for node in ability_nodes:
        node_name = str(node.get("name") or "")
        if skill_name and (skill_name in node_name or node_name in skill_name):
            direct.append((node, 1.0))
    if direct:
        node = sorted(direct, key=lambda item: (_node_priority(item[0]), len(str(item[0].get("name") or ""))))[0][0]
        return node, "direct_name", 1.0

    embedding = _embedding_node_match(skill_name, dim_id, ability_nodes)
    if embedding:
        return embedding

    scored = []
    for node in ability_nodes:
        score = _node_similarity(skill_name, dim_id, node)
        if score >= 0.18:
            scored.append((score, _node_priority(node), node))
    if not scored:
        return None, "", 0.0

    score, _, node = sorted(scored, key=lambda item: (-item[0], item[1], str(item[2].get("id") or "")))[0]
    return node, "semantic_similarity", round(score, 3)


def _embedding_node_match(skill_name, dim_id, ability_nodes):
    if os.environ.get("EMBEDDING_MATCH_ENABLED", "1").lower() in {"0", "false", "no"}:
        return None
    try:
        from app.services.embedding_client import best_embedding_match, is_configured

        if not is_configured():
            return None
        candidates = []
        for node in ability_nodes:
            dimension_hint = " ".join(str(item) for item in node.get("radar_dimension_ids", []) or [])
            candidates.append({
                **node,
                "description": " ".join([
                    str(node.get("description") or ""),
                    dimension_hint,
                    str(dim_id or ""),
                ]),
            })
        result = best_embedding_match(skill_name, candidates, timeout=20)
        if not result:
            return None
        threshold = float(os.environ.get("EMBEDDING_MATCH_THRESHOLD", "0.68"))
        score = float(result.get("score", 0.0))
        if score < threshold:
            return None
        return result["candidate"], "embedding_similarity", round(score, 3)
    except Exception:
        return None


def _node_priority(node):
    level = str(node.get("level") or "")
    return {"root": 3, "advanced": 2, "intermediate": 1, "basic": 0}.get(level, 1)


def _node_similarity(skill_name, dim_id, node):
    query_tokens = _semantic_tokens(skill_name)
    node_text = " ".join([
        str(node.get("id") or ""),
        str(node.get("name") or ""),
        str(node.get("description") or ""),
        " ".join(str(item) for item in node.get("common_errors", [])),
    ])
    node_tokens = _semantic_tokens(node_text)
    if not query_tokens or not node_tokens:
        return 0.0

    overlap = len(query_tokens & node_tokens)
    coverage = overlap / max(len(query_tokens), 1)
    jaccard = overlap / max(len(query_tokens | node_tokens), 1)
    score = coverage * 0.55 + jaccard * 0.25

    lowered_query = str(skill_name or "").lower()
    lowered_node = node_text.lower()
    if lowered_query and lowered_query in lowered_node:
        score += 0.25
    node_name = str(node.get("name") or "").lower()
    if node_name and node_name in lowered_query:
        score += 0.2
    if dim_id and dim_id in (node.get("radar_dimension_ids") or []):
        score += 0.16
    if node.get("level") == "root":
        score -= 0.12
    return max(0.0, min(score, 1.0))


def _semantic_tokens(text):
    text = str(text or "").lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    for term in chinese_terms:
        tokens.add(term)
        if len(term) <= 4:
            continue
        for size in (2, 3):
            for index in range(0, len(term) - size + 1):
                tokens.add(term[index:index + size])
    return tokens


def extract_with_both(jd_text, ability_nodes=None):
    """Run rule-based extraction plus optional LLM extraction."""
    from scripts.pipeline.cleaner import extract_skill_spans, map_skills_to_abilities
    if ability_nodes is None:
        from scripts.pipeline.cleaner import load_ability_nodes
        ability_nodes = load_ability_nodes()

    skills = extract_skill_spans(jd_text)
    rule_results = map_skills_to_abilities(skills, ability_nodes)
    for result in rule_results:
        max_score = 5.0
        result["confidence"] = min(0.95, (result.get("score", 1) or 1) / max_score * 0.8)
        result["source"] = "rule_lexicon"
        result["is_rule"] = True

    merged = list(rule_results)
    seen_ids = {item["ability_id"] for item in rule_results if item.get("ability_id")}

    for llm_item in llm_extract_skills(jd_text, ability_nodes):
        ability_id = llm_item.get("ability_id")
        if ability_id and ability_id not in seen_ids:
            llm_item["confidence"] = max(0.1, llm_item.get("confidence", 0.5) - 0.15)
            merged.append(llm_item)
            seen_ids.add(ability_id)

    return sorted(merged, key=lambda item: -item.get("confidence", 0))[:10]
