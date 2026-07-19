import re
from functools import lru_cache

from .data_loader import load_data


def tokenize(text):
    raw = str(text or "").lower()
    ascii_tokens = re.findall(r"[a-z0-9]+", raw)
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", raw)
    tokens = ascii_tokens + chinese_chunks

    # Extract bigrams and trigrams from longer Chinese chunks for better matching
    for chunk in chinese_chunks:
        if len(chunk) > 2:
            for i in range(len(chunk) - 1):
                tokens.append(chunk[i:i+2])  # bigram: 2-char substrings
            for i in range(len(chunk) - 2):
                tokens.append(chunk[i:i+3])  # trigram: 3-char substrings

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


def search_knowledge(query, limit=5, job_role=None):
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
            role_bonus = 3 if job_role and item.get("job_role") == job_role else 0
            scored.append((score + chain_bonus + role_bonus, item, matched_terms, ability))

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
