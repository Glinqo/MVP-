import re
import logging
from functools import lru_cache

from .data_loader import load_data

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 混合检索权重（可在部署时按效果微调）
# ---------------------------------------------------------------------------
HYBRID_VEC_WEIGHT = 0.6     # 向量语义相似度权重
HYBRID_KW_WEIGHT = 0.3      # 关键词匹配权重
HYBRID_CHAIN_WEIGHT = 0.1   # 能力链加分权重
VECTOR_RECALL_K = 20        # 粗排召回数量


def tokenize(text):
    raw = str(text or "").lower()
    ascii_tokens = re.findall(r"[a-z0-9]+", raw)
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", raw)
    tokens = ascii_tokens + chinese_chunks

    domain_terms = [
        "传感器",
        "动作灯",
        "输入",
        "输出",
        "公共端",
        "接线",
        "断电",
        "电源",
        "气缸",
        "plc",
        "npn",
        "pnp",
        "地址",
        "监控",
        "端子",
        "无响应",
    ]
    tokens.extend(term for term in domain_terms if term in raw)
    return [token for token in tokens if token]


def item_text(item):
    values = []
    for key in ("id", "topic", "name", "title", "content", "description", "job_task", "use_when", "source"):
        value = item.get(key)
        if isinstance(value, str):
            values.append(value)
    for key in ("common_errors", "related_questions", "related_tasks", "node_ids"):
        value = item.get(key)
        if isinstance(value, list):
            values.extend(str(part) for part in value)
    return " ".join(values).lower()


@lru_cache(maxsize=1)
def knowledge_search_index():
    data = load_data()
    return [
        {
            "item": item,
            "text": item_text(item),
            "ability": data["ability_by_id"].get(item.get("ability_node_id"), {}),
        }
        for item in data["knowledge"]
    ]


def score_item(item, tokens):
    text = item if isinstance(item, str) else item_text(item)
    score = 0
    for token in tokens:
        if token in text:
            score += 3 if len(token) > 2 else 1
    return score


def matched_terms_for_item(item, tokens):
    text = item if isinstance(item, str) else item_text(item)
    matched = []
    for token in tokens:
        if token in text and token not in matched:
            matched.append(token)
    return matched


# ===================================================================
# 混合检索（向量 + 关键词）
# ===================================================================


def _normalize_scores(scores: list[float]) -> list[float]:
    """将原始分数列表归一化到 [0, 1]，保留相对大小关系。"""
    if not scores:
        return scores
    mn = min(scores)
    mx = max(scores)
    if mx == mn:
        return [1.0] * len(scores)
    return [(s - mn) / (mx - mn) for s in scores]


def _vector_recall(query: str) -> dict[str, float]:
    """向量粗排召回，返回 {knowledge_id: vector_similarity} 映射。

    如果向量模块不可用或出错，返回空 dict。
    """
    try:
        from .vector_index import vector_search
        results = vector_search(query, top_k=VECTOR_RECALL_K)
        return {r["doc_id"]: r["score"] for r in results if r["doc_type"] == "knowledge"}
    except ImportError:
        logger.debug("vector_search not available (sentence-transformers not installed)")
    except Exception:
        logger.warning("vector_search failed", exc_info=True)
    return {}


def hybrid_search(query: str, limit: int = 5) -> list[dict]:
    """两阶段混合检索：向量粗排 + 关键词精排。

    Stage 1 —— 向量语义召回 top-K
    Stage 2 —— 混合分数重排: α·vec_sim + β·keyword_score + γ·chain_bonus

    返回格式与 search_knowledge 一致。
    """
    data = load_data()
    tokens = tokenize(query)

    # Stage 1: 向量粗排召回
    vec_scores = _vector_recall(query)

    index_entries = knowledge_search_index()
    abilities = data["abilities"]
    ability_ids = {a.get("id") for a in abilities}

    # Stage 2: 混合精排
    candidates = []
    for entry in index_entries:
        item = entry["item"]
        kid = item.get("id", "")

        vec_sim = vec_scores.get(kid, 0.0)
        kw_score = score_item(entry["text"], tokens)

        # 只要有向量匹配或关键词匹配就进入候选
        if vec_sim <= 0 and kw_score <= 0:
            continue

        chain_bonus = 1 if item.get("ability_node_id") in ability_ids else 0
        candidates.append((item, entry["ability"], vec_sim, kw_score, chain_bonus))

    # 如果向量召回为0但有纯关键词命中，仍走关键词逻辑
    # 归一化后加权
    if not candidates:
        return _keyword_fallback(query, limit, data, tokens, index_entries, ability_ids)

    vec_vals = [c[2] for c in candidates]
    kw_vals = [c[3] for c in candidates]
    chain_vals = [c[4] for c in candidates]

    norm_vec = _normalize_scores(vec_vals)
    norm_kw = _normalize_scores(kw_vals)
    norm_chain = _normalize_scores([float(v) for v in chain_vals])

    scored = []
    for i, (item, ability, _, _, _) in enumerate(candidates):
        final_score = (
            HYBRID_VEC_WEIGHT * norm_vec[i]
            + HYBRID_KW_WEIGHT * norm_kw[i]
            + HYBRID_CHAIN_WEIGHT * norm_chain[i]
        )
        matched_terms = matched_terms_for_item(item_text(item), tokens)
        scored.append((final_score, item, ability, matched_terms))

    scored.sort(key=lambda pair: (-pair[0], pair[1].get("id", "")))

    return _format_results(scored[:limit])


def _keyword_fallback(query, limit, data, tokens, index_entries, ability_ids):
    """纯关键词检索降级路径（向量不可用时的兜底方案）。"""
    scored = []
    for entry in index_entries:
        item = entry["item"]
        text = entry["text"]
        ability = entry["ability"]
        score = score_item(text, tokens)
        if score > 0:
            matched_terms = matched_terms_for_item(text, tokens)
            chain_bonus = 1 if item.get("ability_node_id") in ability_ids else 0
            scored.append((score + chain_bonus, item, ability, matched_terms))

    scored.sort(key=lambda pair: (-pair[0], pair[1].get("id", "")))
    return _format_results(scored[:limit])


def _format_results(scored: list) -> list[dict]:
    """将内部打分结果转换为统一的输出格式。"""
    return [
        {
            "id": item.get("id"),
            "topic": item.get("topic"),
            "ability_node_id": item.get("ability_node_id"),
            "ability_name": ability.get("name", item.get("ability_node_id")),
            "content": item.get("content"),
            "related_tasks": item.get("related_tasks", []),
            "source": item.get("source"),
            "score": round(score, 4),
            "matched_terms": matched_terms,
            "match_reason": "向量+关键词混合命中：" + "、".join(matched_terms[:5]) if matched_terms else "语义匹配",
        }
        for score, item, ability, matched_terms in scored
    ]


# ===================================================================
# 主检索入口（对外接口保持兼容）
# ===================================================================


def search_knowledge(query, limit=5):
    """知识检索入口。

    优先使用向量+关键词混合检索；向量模块不可用时自动降级为纯关键词检索。
    """
    try:
        from .vector_index import vector_available
        if vector_available():
            return hybrid_search(query, limit)
    except ImportError:
        pass
    except Exception:
        logger.warning("hybrid_search init failed, falling back to keyword", exc_info=True)

    # 降级：纯关键词检索
    data = load_data()
    tokens = tokenize(query)
    scored = []

    for indexed in knowledge_search_index():
        item = indexed["item"]
        text = indexed["text"]
        ability = indexed["ability"]
        score = score_item(text, tokens)
        if score > 0:
            matched_terms = matched_terms_for_item(text, tokens)
            chain_bonus = 1 if item.get("ability_node_id") in {ability.get("id") for ability in data["abilities"]} else 0
            scored.append((score + chain_bonus, item, matched_terms, ability))

    scored.sort(key=lambda pair: (-pair[0], pair[1].get("id", "")))
    return [
        {
            "id": item.get("id"),
            "topic": item.get("topic"),
            "ability_node_id": item.get("ability_node_id"),
            "ability_name": ability.get("name", item.get("ability_node_id")),
            "content": item.get("content"),
            "related_tasks": item.get("related_tasks", []),
            "source": item.get("source"),
            "score": score,
            "matched_terms": matched_terms,
            "match_reason": "关键词/岗位能力链命中：" + "、".join(matched_terms[:5]),
        }
        for score, item, matched_terms, ability in scored[:limit]
    ]


def refs_for_ability_ids(ability_ids):
    data = load_data()
    knowledge_refs = []
    task_refs = []
    resource_refs = []
    seen_knowledge = set()
    seen_tasks = set()
    seen_resources = set()

    for ability_id in ability_ids:
        ability = data["ability_by_id"].get(ability_id)
        if not ability:
            continue

        for knowledge_id in ability.get("related_knowledge", []):
            item = data["knowledge_by_id"].get(knowledge_id)
            if item and knowledge_id not in seen_knowledge:
                seen_knowledge.add(knowledge_id)
                knowledge_refs.append(item)

        for task_id in ability.get("related_tasks", []):
            task = data["task_by_id"].get(task_id)
            if task and task_id not in seen_tasks:
                seen_tasks.add(task_id)
                task_refs.append(task)

        for resource in data["resources"]:
            if ability_id in resource.get("node_ids", []) and resource.get("id") not in seen_resources:
                seen_resources.add(resource.get("id"))
                resource_refs.append(resource)

    return {
        "knowledge_refs": knowledge_refs,
        "task_refs": task_refs,
        "resource_refs": resource_refs,
    }
