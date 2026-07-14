# -*- coding: utf-8 -*-
"""Job JD cleaning and normalization."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_lexicon():
    path = ROOT / "knowledge" / "job_skill_lexicon.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"lexicon": {}}


def load_ability_nodes():
    path = ROOT / "knowledge" / "ability_nodes.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")).get("nodes", [])
    return []


def extract_text_from_html(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def extract_fields_from_text(text):
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    fields = {"title": "", "company": "", "skills": [], "responsibilities": [], "requirements": []}
    responsibility_keywords = ["职责", "工作内容", "岗位职责", "工作职责", "主要职责", "负责"]
    requirement_keywords = ["要求", "任职资格", "职位要求", "岗位要求", "任职要求"]
    skill_keywords = ["技能", "熟悉", "掌握", "了解", "PLC", "传感器", "电气", "排故", "调试"]
    company_keywords = ["公司", "企业", "单位"]

    for line in lines[:30]:
        if not fields["company"] and any(keyword in line for keyword in company_keywords):
            fields["company"] = line[:80]
        if any(keyword in line for keyword in responsibility_keywords):
            fields["responsibilities"].append(line)
        elif any(keyword in line for keyword in requirement_keywords):
            fields["requirements"].append(line)
        elif any(keyword in line for keyword in skill_keywords):
            fields["skills"].append(line)

    if not fields["title"] and lines:
        fields["title"] = lines[0]
    return fields


def normalize_title(raw_title):
    if not raw_title:
        return raw_title, None
    lexicon = load_lexicon()
    mapping = lexicon.get("lexicon", {}).get("job_title_normalization", {})
    for pattern, internal_id in mapping.items():
        if pattern in raw_title or raw_title in pattern:
            return pattern, internal_id
    return raw_title, None


def extract_skill_spans(text):
    lexicon = load_lexicon()
    hits = []
    for category, terms in lexicon.get("lexicon", {}).get("hard_skills", {}).items():
        for term in terms:
            index = text.find(term)
            if index >= 0:
                hits.append({"term": term, "category": category, "start": index})
    for term in lexicon.get("lexicon", {}).get("soft_skills", []):
        index = text.find(term)
        if index >= 0:
            hits.append({"term": term, "category": "soft_skill", "start": index})
    hits.sort(key=lambda item: item["start"])

    seen = set()
    unique = []
    for hit in hits:
        if hit["term"] not in seen:
            seen.add(hit["term"])
            unique.append(hit)
    return unique


def map_skills_to_abilities(skill_hits, ability_nodes=None):
    if ability_nodes is None:
        ability_nodes = load_ability_nodes()
    scores = {}
    for ability in ability_nodes:
        search = (
            ability.get("name", "")
            + ability.get("description", "")
            + " ".join(ability.get("related_knowledge", []))
        )
        terms = [hit["term"] for hit in skill_hits if hit["term"] in search]
        if terms:
            scores[ability["id"]] = {
                "ability_id": ability["id"],
                "name": ability.get("name"),
                "score": len(terms),
                "matched_terms": terms,
            }
    return sorted(scores.values(), key=lambda item: -item["score"])


def extract_skill_spans_jieba(text):
    """Jieba-enhanced skill extraction with multi-word support."""
    import jieba
    lexicon = load_lexicon()
    for terms in lexicon.get("lexicon", {}).get("hard_skills", {}).values():
        for term in terms:
            jieba.add_word(term, freq=100, tag="skill")
    for term in lexicon.get("lexicon", {}).get("soft_skills", []):
        jieba.add_word(term, freq=80, tag="skill_soft")
    for term in lexicon.get("lexicon", {}).get("certifications", []):
        jieba.add_word(term, freq=90, tag="cert")
    return [
        {**hit, "source": "lexicon"}
        for hit in extract_skill_spans(text)
    ]
