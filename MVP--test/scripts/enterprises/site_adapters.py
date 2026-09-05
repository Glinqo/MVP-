# -*- coding: utf-8 -*-
"""Site-level parsers for authorized enterprise career pages.

The updater only receives HTML from approved sources.  These adapters turn
official career pages into structured job-post records before the generic text
pipeline runs, which keeps enterprise evidence easier to query and review.
"""
import json
import re
from collections.abc import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup


MAX_POSTS_PER_SOURCE = 30

SITE_ADAPTERS = {
    "siemens_career": {
        "domains": ["siemens"],
        "selectors": [
            "[data-ph-at-id*='job']",
            ".jobs-list__item",
            ".job-listing",
            ".search-result",
            ".job-card",
            "a[href*='/jobs/']",
        ],
        "title_selectors": ["[data-ph-at-id*='job-title']", "h1", "h2", "h3", ".job-title", "a"],
    },
    "inovance_career": {
        "domains": ["inovance", "huichuan"],
        "selectors": [
            ".position-list li",
            ".job-list li",
            ".recruit-list li",
            ".position-item",
            ".job-item",
            ".career-item",
            "tr",
        ],
        "title_selectors": ["h1", "h2", "h3", ".position-title", ".job-title", ".title", "td:first-child", "a"],
    },
    "byd_career": {
        "domains": ["byd"],
        "selectors": [
            ".recruit-list li",
            ".job-list li",
            ".position-list li",
            ".career-list li",
            ".job-item",
            ".position-item",
            "tr",
        ],
        "title_selectors": ["h1", "h2", "h3", ".position-title", ".job-title", ".title", "td:first-child", "a"],
    },
    "generic_enterprise": {
        "domains": [],
        "selectors": [
            "[class*='job']",
            "[class*='career']",
            "[class*='position']",
            "[class*='recruit']",
            "article",
            "li",
            "tr",
        ],
        "title_selectors": ["h1", "h2", "h3", ".position-title", ".job-title", ".title", "td:first-child", "a"],
    },
}

JOB_HINTS = [
    "工程师", "技术员", "自动化", "电气", "PLC", "调试", "运维", "设备", "机电",
    "Engineer", "Technician", "Automation", "Electrical", "Maintenance",
]
RESPONSIBILITY_LABELS = ["岗位职责", "工作职责", "主要职责", "职责", "工作内容", "负责"]
REQUIREMENT_LABELS = ["任职要求", "岗位要求", "职位要求", "任职资格", "要求"]
SKILL_LABELS = ["技能要求", "技能", "能力要求", "熟悉", "掌握"]


def infer_adapter_key(source: dict) -> str:
    explicit = source.get("adapter") or source.get("site_adapter")
    if explicit and explicit in SITE_ADAPTERS:
        return explicit

    haystack = " ".join(
        str(source.get(key) or "")
        for key in ("id", "source", "url", "search_url", "base_url", "company")
    ).lower()
    for adapter_key, spec in SITE_ADAPTERS.items():
        if adapter_key == "generic_enterprise":
            continue
        if any(domain in haystack for domain in spec.get("domains", [])):
            return adapter_key
    return "generic_enterprise"


def parse_enterprise_job_posts(source: dict, html: str, base_url: str = "") -> list[dict]:
    """Parse structured job posts from an enterprise official career page."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        if (tag.name or "").lower() != "script" or "ld+json" not in " ".join(tag.get("type", []) if isinstance(tag.get("type"), list) else [str(tag.get("type", ""))]):
            tag.decompose()

    base = base_url or source.get("url") or source.get("search_url") or source.get("base_url") or ""
    adapter_key = infer_adapter_key(source)
    spec = SITE_ADAPTERS.get(adapter_key, SITE_ADAPTERS["generic_enterprise"])

    records = []
    records.extend(_json_ld_job_postings(html, source, base, adapter_key))
    records.extend(_card_job_postings(soup, source, base, adapter_key, spec))
    return _dedupe_records(records)[:MAX_POSTS_PER_SOURCE]


def _json_ld_job_postings(html: str, source: dict, base_url: str, adapter_key: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        try:
            payload = json.loads(script.string or script.get_text() or "{}")
        except json.JSONDecodeError:
            continue
        for item in _walk_json(payload):
            item_type = item.get("@type") or item.get("type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if not any(str(value).lower() == "jobposting" for value in types):
                continue
            description = _html_text(item.get("description", ""))
            company = item.get("hiringOrganization") or {}
            if isinstance(company, dict):
                company = company.get("name", "")
            record = {
                "title": _clean(item.get("title", "")),
                "company": _clean(company or source.get("company") or source.get("source") or ""),
                "responsibilities": _extract_labeled_lines(description, RESPONSIBILITY_LABELS),
                "requirements": _extract_labeled_lines(description, REQUIREMENT_LABELS),
                "skills": _extract_labeled_lines(description, SKILL_LABELS),
                "text": description,
                "source_url": urljoin(base_url, str(item.get("url") or "")) if item.get("url") else base_url,
                "site_adapter": adapter_key,
                "source_type": "enterprise_official",
            }
            normalized = _normalize_record(record, source, base_url, adapter_key)
            if normalized:
                records.append(normalized)
    return records


def _card_job_postings(soup: BeautifulSoup, source: dict, base_url: str, adapter_key: str, spec: dict) -> list[dict]:
    records = []
    seen_elements = set()
    for selector in spec.get("selectors", []):
        for card in soup.select(selector):
            element_key = id(card)
            if element_key in seen_elements:
                continue
            seen_elements.add(element_key)
            candidate = _record_from_card(card, source, base_url, adapter_key, spec)
            if candidate:
                records.append(candidate)
            if len(records) >= MAX_POSTS_PER_SOURCE:
                return records
    return records


def _record_from_card(card, source: dict, base_url: str, adapter_key: str, spec: dict) -> dict | None:
    text = _clean(card.get_text("\n", strip=True))
    if len(text) < 12:
        return None
    title = _extract_title(card, spec)
    if not title and not _looks_like_job_text(text):
        return None

    link = card if getattr(card, "name", "") == "a" else card.select_one("a[href]")
    href = link.get("href") if link else ""
    fields = _fields_from_text(text)
    record = {
        "title": title or fields.get("title", ""),
        "company": source.get("company") or source.get("source") or "",
        "responsibilities": fields.get("responsibilities", []),
        "requirements": fields.get("requirements", []),
        "skills": fields.get("skills", []),
        "text": text,
        "source_url": urljoin(base_url, href) if href else base_url,
        "site_adapter": adapter_key,
        "source_type": "enterprise_official",
    }
    return _normalize_record(record, source, base_url, adapter_key)


def _normalize_record(record: dict, source: dict, base_url: str, adapter_key: str) -> dict | None:
    text = _clean(record.get("text", ""))
    title = _clean(record.get("title", ""))
    if title and len(title) > 96:
        title = title[:96]
    if not title and text:
        title = _first_job_like_line(text)
    if not title or not text:
        return None
    if not _looks_like_job_text(" ".join([title, text])):
        return None

    fields = _fields_from_text(text)
    responsibilities = _listify(record.get("responsibilities")) or fields.get("responsibilities", [])
    requirements = _listify(record.get("requirements")) or fields.get("requirements", [])
    skills = _listify(record.get("skills")) or fields.get("skills", [])
    company = _clean(record.get("company") or fields.get("company") or source.get("company") or source.get("source") or "")

    return {
        "title": title,
        "company": company,
        "responsibilities": responsibilities[:8],
        "requirements": requirements[:8],
        "skills": skills[:8],
        "text": text,
        "source_url": record.get("source_url") or base_url,
        "source_type": "enterprise_official",
        "site_adapter": adapter_key,
        "raw_source_id": source.get("id"),
    }


def _fields_from_text(text: str) -> dict:
    from scripts.pipeline.cleaner import extract_fields_from_text

    fields = extract_fields_from_text(text)
    fields.setdefault("responsibilities", [])
    fields.setdefault("requirements", [])
    fields.setdefault("skills", [])
    return fields


def _extract_title(card, spec: dict) -> str:
    for selector in spec.get("title_selectors", []):
        node = card.select_one(selector)
        if not node:
            continue
        title = _clean(node.get_text(" ", strip=True))
        if 2 <= len(title) <= 96 and _looks_like_job_text(title):
            return title
    for line in _clean(card.get_text("\n", strip=True)).split("\n"):
        line = _clean(line)
        if 2 <= len(line) <= 96 and _looks_like_job_text(line):
            return line
    return ""


def _extract_labeled_lines(text: str, labels: list[str]) -> list[str]:
    lines = [_clean(line) for line in re.split(r"[\n\r。；;]+", text or "") if _clean(line)]
    matched = []
    for line in lines:
        if any(label.lower() in line.lower() for label in labels):
            matched.append(line[:220])
    return matched[:8]


def _dedupe_records(records: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for record in records:
        key = (
            _clean(record.get("source_url", "")).lower()
            or f"{record.get('title','')}|{record.get('company','')}|{record.get('text','')[:80]}"
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def _walk_json(payload) -> Iterable[dict]:
    if isinstance(payload, dict):
        yield payload
        for value in payload.values():
            yield from _walk_json(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_json(item)


def _html_text(value: str) -> str:
    if not value:
        return ""
    return _clean(BeautifulSoup(str(value), "html.parser").get_text("\n", strip=True))


def _clean(value) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", str(value or "")).strip()


def _listify(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[\n\r。；;]+", str(value))
    cleaned = [_clean(item) for item in items if _clean(item)]
    return cleaned


def _looks_like_job_text(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(hint.lower() in lowered for hint in JOB_HINTS)


def _first_job_like_line(text: str) -> str:
    for line in re.split(r"[\n\r]+", text or ""):
        line = _clean(line)
        if 2 <= len(line) <= 96 and _looks_like_job_text(line):
            return line
    return ""
