# -*- coding: utf-8 -*-
"""Import authorized job materials into the evidence-driven job graph pipeline."""
import argparse
import csv
import io
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_JOB_ROLE = "自动化生产线装调与运维技术员"
SUPPORTED_SUFFIXES = {".txt", ".md", ".html", ".htm", ".json", ".csv"}


def read_text_fallback(path):
    """Read common Chinese job-material encodings without corrupting content."""
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def candidate_confidence(candidate):
    value = candidate.get("confidence")
    if isinstance(value, (int, float)):
        return float(value)
    score = candidate.get("score")
    if isinstance(score, (int, float)):
        # Rule-based candidates expose a hit score, not a calibrated
        # probability. Keep one-hit candidates conservative but high enough
        # for trusted teacher/standard sources to enter the review queue.
        return min(0.88, 0.55 + min(score, 4) * 0.08)
    return 0.5


def post_text(record):
    parts = [
        record.get("title", ""),
        record.get("company", ""),
        " ".join(record.get("responsibilities", []) or []),
        " ".join(record.get("skills", []) or []),
        " ".join(record.get("requirements", []) or []),
        record.get("text", ""),
        record.get("description", ""),
    ]
    return "\n".join(str(part) for part in parts if part)


def records_from_json(path):
    data = json.loads(read_text_fallback(path))
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict) and isinstance(data.get("posts"), list):
        records = data["posts"]
    elif isinstance(data, dict):
        records = [data]
    else:
        records = []
    for index, record in enumerate(records):
        if isinstance(record, dict):
            yield record, f"{path}#{index + 1}"


def records_from_csv(path):
    handle = io.StringIO(read_text_fallback(path))
    for index, row in enumerate(csv.DictReader(handle)):
        record = {
            "title": row.get("title", ""),
            "company": row.get("company", ""),
            "skills": [row.get("skills", "")] if row.get("skills") else [],
            "responsibilities": [row.get("responsibilities", "")] if row.get("responsibilities") else [],
            "requirements": [row.get("requirements", "")] if row.get("requirements") else [],
            "text": row.get("text", "") or row.get("description", ""),
        }
        yield record, f"{path}#{index + 1}"


def text_from_file(path):
    text = read_text_fallback(path)
    if path.suffix.lower() in {".html", ".htm"}:
        from scripts.pipeline.cleaner import extract_text_from_html
        return extract_text_from_html(text)
    return text


def iter_input_documents(path):
    path = Path(path)
    files = sorted(path.rglob("*")) if path.is_dir() else [path]
    for file_path in files:
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        suffix = file_path.suffix.lower()
        if suffix == ".json":
            for record, source_url in records_from_json(file_path):
                text = post_text(record).strip()
                if text:
                    yield text, source_url
        elif suffix == ".csv":
            for record, source_url in records_from_csv(file_path):
                text = post_text(record).strip()
                if text:
                    yield text, source_url
        else:
            text = text_from_file(file_path).strip()
            if text:
                yield text, str(file_path)


def extract_abilities(text, use_llm=False):
    from scripts.pipeline.cleaner import extract_skill_spans, load_ability_nodes, map_skills_to_abilities

    nodes = load_ability_nodes()
    if use_llm:
        from scripts.pipeline.llm_extractor import extract_with_both
        return extract_with_both(text, nodes)
    skills = extract_skill_spans(text)
    return map_skills_to_abilities(skills, nodes)


def ingest_job_text(
    text,
    job_role=DEFAULT_JOB_ROLE,
    source_type="teacher_material",
    source="manual_import",
    source_url="",
    use_llm=False,
    max_abilities=5,
):
    """Import one job material text into raw/job/evidence/proposal stores."""
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")

    from scripts.pipeline.cleaner import extract_fields_from_text, normalize_title
    from scripts.pipeline.evidence_store import (
        add_event,
        add_job_post,
        add_proposal,
        add_raw_document,
        compute_proposal_score,
    )
    from scripts.pipeline.sqlite_store import proposal_threshold

    fields = extract_fields_from_text(text)
    normalized_title, _ = normalize_title(fields.get("title"))
    fields["normalized_title"] = normalized_title or fields.get("title", "")

    raw_document = add_raw_document(
        text,
        source_type=source_type,
        source=source,
        source_url=source_url,
        metadata={"job_role": job_role},
    )
    job_post = add_job_post(raw_document["document_id"], job_role, fields, source_type, source_url)

    abilities = extract_abilities(text, use_llm=use_llm)
    events = []
    proposals = []
    for ability in abilities[:max_abilities]:
        ability_id = ability.get("ability_id") or ability.get("id")
        if not ability_id:
            continue
        confidence = candidate_confidence(ability)
        metadata = {
            "source": source,
            "skill_name": ability.get("skill_name") or ability.get("name"),
            "candidate_source": ability.get("source") or ("llm_extraction" if use_llm else "rule_lexicon"),
            "prompt_version": ability.get("prompt_version"),
            "llm_model": ability.get("llm_model"),
        }
        metadata = {key: value for key, value in metadata.items() if value not in (None, "")}
        event = add_event(
            job_role=job_role,
            ability_id=str(ability_id),
            evidence_text=text[:300],
            source_url=source_url,
            source_type=source_type,
            extraction_method="llm_assisted" if use_llm else "rule_lexicon_v1",
            confidence=confidence,
            metadata=metadata,
        )
        events.append({**event, "ability": ability})

        score = compute_proposal_score(source_type, confidence, len(abilities), 1)
        threshold = proposal_threshold(score)
        if threshold in {"auto_approve", "pending"}:
            proposal = add_proposal(
                job_role=job_role,
                ability_id=str(ability_id),
                action="strengthen",
                suggested_weight_delta=round(score * 0.15, 2),
                evidence=text[:200],
                source=source,
                proposal_score=score,
            )
            proposal["ability_name"] = ability.get("name") or ability.get("ability_name")
            proposal["threshold"] = threshold
            proposals.append(proposal)

    return {
        "text_analyzed": text[:100],
        "raw_document": raw_document,
        "job_post": job_post,
        "normalized_fields": fields,
        "abilities_matched": abilities[:max_abilities],
        "events_created": events,
        "proposals_generated": proposals,
        "llm_used": use_llm,
        "method": "llm_extraction" if use_llm else "rule_lexicon",
    }


def import_path(path, job_role=DEFAULT_JOB_ROLE, source_type="local_file", source="", use_llm=False, max_abilities=5):
    results = []
    source = source or str(path)
    for text, source_url in iter_input_documents(path):
        results.append(
            ingest_job_text(
                text,
                job_role=job_role,
                source_type=source_type,
                source=source,
                source_url=source_url,
                use_llm=use_llm,
                max_abilities=max_abilities,
            )
        )
    return {
        "input": str(path),
        "document_count": len(results),
        "event_count": sum(len(item["events_created"]) for item in results),
        "proposal_count": sum(len(item["proposals_generated"]) for item in results),
        "results": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import authorized job documents into the ability graph pipeline.")
    parser.add_argument("path", help="File or directory: txt/md/html/json/csv")
    parser.add_argument("--job-role", default=DEFAULT_JOB_ROLE)
    parser.add_argument("--source-type", default="local_file")
    parser.add_argument("--source", default="")
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--max-abilities", type=int, default=5)
    args = parser.parse_args(argv)
    result = import_path(
        args.path,
        job_role=args.job_role,
        source_type=args.source_type,
        source=args.source,
        use_llm=args.use_llm,
        max_abilities=args.max_abilities,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
