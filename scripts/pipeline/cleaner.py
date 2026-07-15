# -*- coding: utf-8 -*-
"""Job JD cleaning and normalization"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def load_lexicon():
    p = ROOT / "knowledge" / "job_skill_lexicon.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"lexicon": {}}

def load_ability_nodes():
    p = ROOT / "knowledge" / "ability_nodes.json"
    return json.loads(p.read_text(encoding="utf-8")).get("nodes", []) if p.exists() else []

def extract_text_from_html(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]): tag.decompose()
    return soup.get_text(separator="\n", strip=True)

def extract_fields_from_text(text):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    fields = {"title": "", "company": "", "skills": [], "responsibilities": [], "requirements": []}
    for line in lines[:30]:
        if any(kw in line for kw in ["职责", "工作内容", "岗位职责"]):
            fields["responsibilities"].append(line)
        elif any(kw in line for kw in ["要求", "任职资格", "职位要求"]):
            fields["requirements"].append(line)
        elif any(kw in line for kw in ["技能", "熟悉", "掌握", "精通"]):
            fields["skills"].append(line)
    if not fields["title"] and lines:
        fields["title"] = lines[0]
    return fields

def normalize_title(raw_title):
    if not raw_title: return raw_title, None
    lex = load_lexicon()
    mapping = lex.get("lexicon", {}).get("job_title_normalization", {})
    for pat, iid in mapping.items():
        if pat in raw_title or raw_title in pat:
            return pat, iid
    return raw_title, None

def extract_skill_spans(text):
    lex = load_lexicon()
    hits = []
    for cat, terms in lex.get("lexicon", {}).get("hard_skills", {}).items():
        for term in terms:
            idx = text.find(term)
            if idx >= 0:
                hits.append({"term": term, "category": cat, "start": idx})
    for term in lex.get("lexicon", {}).get("soft_skills", []):
        idx = text.find(term)
        if idx >= 0:
            hits.append({"term": term, "category": "soft_skill", "start": idx})
    hits.sort(key=lambda x: x["start"])
    seen = set()
    unique = []
    for h in hits:
        if h["term"] not in seen:
            seen.add(h["term"])
            unique.append(h)
    return unique

def map_skills_to_abilities(skill_hits, ability_nodes=None):
    if ability_nodes is None: ability_nodes = load_ability_nodes()
    scores = {}
    for ab in ability_nodes:
        search = ab.get("name","") + ab.get("description","") + " ".join(ab.get("related_knowledge",[]))
        terms = [h["term"] for h in skill_hits if h["term"] in search]
        if terms:
            scores[ab["id"]] = {"ability_id": ab["id"], "name": ab.get("name"), "score": len(terms), "matched_terms": terms}
    return sorted(scores.values(), key=lambda x: -x["score"])
def extract_skill_spans_jieba(text):
    """Jieba-enhanced skill extraction with multi-word support"""
    import jieba
    lex = load_lexicon()
    for cat, terms in lex.get("lexicon", {}).get("hard_skills", {}).items():
        for t in terms:
            jieba.add_word(t, freq=100, tag="skill")
    for t in lex.get("lexicon", {}).get("soft_skills", []):
        jieba.add_word(t, freq=80, tag="skill_soft")
    for t in lex.get("lexicon", {}).get("certifications", []):
        jieba.add_word(t, freq=90, tag="cert")
    hits = []
    for cat, terms in lex.get("lexicon", {}).get("hard_skills", {}).items():
        for term in terms:
            idx = text.find(term)
            if idx >= 0:
                hits.append({"term": term, "category": cat, "start": idx, "source": "lexicon"})
    for term in lex.get("lexicon", {}).get("soft_skills", []):
        idx = text.find(term)
        if idx >= 0:
            hits.append({"term": term, "category": "soft_skill", "start": idx, "source": "lexicon"})
    for term in lex.get("lexicon", {}).get("certifications", []):
        idx = text.find(term)
        if idx >= 0:
            hits.append({"term": term, "category": "certification", "start": idx, "source": "lexicon"})
    hits.sort(key=lambda x: x["start"])
    seen = set()
    unique = []
    for h in hits:
        if h["term"] not in seen:
            seen.add(h["term"])
            unique.append(h)
    return unique
