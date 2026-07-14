#!/usr/bin/env python3
"""Collect approved job materials and generate pending job graph proposals.

The updater is intentionally small and compliant:
- reads only configured local files or public URLs;
- uses stdlib urllib and robots.txt checks;
- extracts rough ability evidence with deterministic keywords;
- writes pending proposals through the existing graph update engine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ROOT / "knowledge" / "job_intelligence_sources.json"
DEFAULT_RUN_LOG = ROOT / "data" / "job_intelligence_runs.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


ABILITY_ALIASES = {
    "electrical_safety_check": ["安全", "断电", "急停", "上锁挂牌", "安全回路", "设备状态"],
    "power_isolation_confirmation": ["断电", "隔离", "电源确认", "拆线前"],
    "dc24v_power_check": ["24V", "DC24V", "直流电源", "供电", "电源模块"],
    "multimeter_voltage_measurement": ["万用表", "测电压", "电压测量"],
    "sensor_type_identification": ["NPN", "PNP", "传感器类型", "输出类型", "三线制"],
    "sensor_nameplate_reading": ["铭牌", "型号", "规格", "说明书"],
    "sensor_output_logic": ["输出逻辑", "源型", "漏型", "sourcing", "sinking"],
    "sensor_led_observation": ["动作灯", "指示灯", "传感器灯", "灯亮", "灯不亮"],
    "sensor_wiring_color_code": ["棕线", "蓝线", "黑线", "线色", "三线制"],
    "sensor_wiring_judgement": ["接线", "端子", "输出线", "黑线", "传感器接线"],
    "plc_input_common_terminal": ["公共端", "COM", "S/S", "输入公共端", "源型输入", "漏型输入"],
    "plc_input_grouping": ["输入分组", "公共端分组", "端子组"],
    "plc_io_address_mapping": ["I/O", "IO", "地址", "I0", "X0", "映射", "端子号"],
    "io_mapping_table_build": ["I/O 表", "映射表", "点表", "变量表"],
    "program_variable_lookup": ["程序变量", "变量", "梯形图", "程序条件", "地址引用"],
    "plc_input_monitoring": ["在线监控", "PLC 输入灯", "输入灯", "监控状态", "输入信号"],
    "input_led_compare": ["三联状态", "传感器灯", "PLC 输入灯", "在线监控"],
    "input_no_response_fault_scope": ["无响应", "没输入", "故障排查", "定位", "排故"],
    "no_response_power_path_check": ["供电路径", "保险", "电源端", "24V"],
    "no_response_sensor_side_check": ["检测距离", "目标材质", "安装距离", "传感器侧"],
    "no_response_common_terminal_check": ["公共端接错", "COM 接反", "S/S 接法", "公共端检查"],
    "no_response_address_mapping_check": ["地址错", "映射错", "监控地址", "程序地址"],
    "diagnosis_record_feedback": ["记录", "复测", "反馈", "证据", "原因"],
    "personalized_training_task_recommendation": ["训练任务", "培养方案", "学习路径", "补救训练"],
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag.lower() in {"p", "div", "li", "br", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return normalize_text(" ".join(self.parts))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    return path


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def html_to_text(raw: str) -> str:
    if "<html" not in raw[:1000].lower() and "<body" not in raw[:1000].lower():
        return normalize_text(raw)
    parser = TextExtractor()
    parser.feed(raw)
    return parser.text()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:16]


def robots_allowed(url: str, user_agent: str, timeout: int) -> tuple[bool, str]:
    parsed = urllib.parse.urlparse(url)
    robots_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    parser = urllib.robotparser.RobotFileParser()
    try:
        request = urllib.request.Request(robots_url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(200000)
            charset = response.headers.get_content_charset() or "utf-8"
        parser.parse(raw.decode(charset, errors="replace").splitlines())
        allowed = parser.can_fetch(user_agent, url)
        return allowed, "robots_allowed" if allowed else "robots_blocked"
    except (urllib.error.URLError, TimeoutError, UnicodeError):
        return True, "robots_unavailable_allowed"


def fetch_url(source: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    url = source.get("url") or source.get("search_url")
    if not url:
        return {"ok": False, "skip_reason": "url_missing", "source_id": source.get("id")}
    user_agent = policy.get("user_agent", "mechatronics-agent-mvp-job-intelligence/0.1")
    timeout = int(policy.get("timeout_seconds", 10))
    max_bytes = int(policy.get("max_bytes_per_source", 500000))

    if policy.get("respect_robots_txt", True):
        allowed, robots_status = robots_allowed(url, user_agent, timeout)
        if not allowed:
            return {"ok": False, "skip_reason": robots_status, "source_id": source.get("id"), "url": url}
    else:
        robots_status = "robots_check_disabled"

    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl()
        truncated = len(raw) > max_bytes
        raw = raw[:max_bytes]
        text = html_to_text(raw.decode(charset, errors="replace"))
        return {
            "ok": True,
            "source_id": source.get("id"),
            "source_type": source.get("source_type", "public_url"),
            "source": source.get("source") or url,
            "url": final_url,
            "robots_status": robots_status,
            "truncated": truncated,
            "text": text,
        }
    except (urllib.error.URLError, TimeoutError, UnicodeError) as exc:
        return {"ok": False, "skip_reason": f"fetch_failed:{exc}", "source_id": source.get("id"), "url": url}


def fetch_local_file(source: dict[str, Any]) -> dict[str, Any]:
    path_text = source.get("path") or source.get("local_path")
    if not path_text:
        return {"ok": False, "skip_reason": "local_file_path_missing", "source_id": source.get("id")}
    path = resolve_path(path_text)
    if not path.exists():
        return {"ok": False, "skip_reason": "local_file_missing", "source_id": source.get("id"), "path": str(path)}
    from scripts.pipeline.job_data_importer import read_text_fallback

    text = html_to_text(read_text_fallback(path))
    return {
        "ok": True,
        "source_id": source.get("id"),
        "source_type": source.get("source_type", "local_file"),
        "source": source.get("source") or str(path.relative_to(ROOT)),
        "path": str(path),
        "text": text,
    }


def source_keywords(config: dict[str, Any], source: dict[str, Any]) -> list[str]:
    keywords = []
    keywords.extend(config.get("global_keywords", []))
    keywords.extend(source.get("keywords", []))
    for terms in ABILITY_ALIASES.values():
        keywords.extend(terms)
    ordered = []
    seen = set()
    for item in keywords:
        term = str(item).strip()
        key = term.lower()
        if term and key not in seen:
            ordered.append(term)
            seen.add(key)
    return ordered


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])|\n+", text)
    return [normalize_text(part) for part in parts if normalize_text(part)]


def extract_snippets(text: str, keywords: list[str], limit: int = 10) -> list[str]:
    snippets = []
    lower_keywords = [keyword.lower() for keyword in keywords if keyword]
    for sentence in split_sentences(text):
        lowered = sentence.lower()
        if any(keyword in lowered for keyword in lower_keywords):
            snippets.append(sentence[:280])
        if len(snippets) >= limit:
            break
    if not snippets and text:
        snippets.append(text[:280])
    return snippets


def match_abilities(text: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    matches = []
    for ability_id, aliases in ABILITY_ALIASES.items():
        hits = []
        for alias in aliases:
            if alias.lower() in lowered:
                hits.append(alias)
        if hits:
            matches.append(
                {
                    "ability_id": ability_id,
                    "hit_count": len(hits),
                    "evidence_terms": hits[:5],
                }
            )
    matches.sort(key=lambda item: (-item["hit_count"], item["ability_id"]))
    return matches


def append_run_log(path: Path, record: dict[str, Any], max_records: int = 50) -> None:
    if path.exists():
        try:
            data = read_json(path)
        except json.JSONDecodeError:
            data = {"version": "0.1.0", "source": "project_runtime", "runs": []}
    else:
        data = {"version": "0.1.0", "source": "project_runtime", "runs": []}
    data.setdefault("runs", []).append(record)
    data["runs"] = data["runs"][-max_records:]
    write_json(path, data)


def select_sources(config: dict[str, Any], source_id: str | None, max_sources: int | None) -> list[dict[str, Any]]:
    sources = [item for item in config.get("sources", []) if item.get("enabled", False)]
    if source_id:
        sources = [item for item in sources if item.get("id") == source_id]
    policy = config_policy(config)
    limit = max_sources or int(policy.get("max_sources_per_run", 3))
    return sources[:limit]


def config_policy(config: dict[str, Any]) -> dict[str, Any]:
    """Support both old test fixture policy and current source registry format."""
    policy = dict(config.get("policy") or config.get("update_policy") or {})
    if "rate_limit_delay_s" in policy and "request_interval_seconds" not in policy:
        policy["request_interval_seconds"] = policy["rate_limit_delay_s"]
    return policy


def source_kind(source: dict[str, Any]) -> str:
    if source.get("type"):
        return source["type"]
    if source.get("source_type") == "local_file" or source.get("local_path"):
        return "local_file"
    if source.get("url") or source.get("search_url"):
        return "url"
    return "unknown"


def collect(config: dict[str, Any], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    policy = config_policy(config)
    if args.timeout:
        policy["timeout_seconds"] = args.timeout
    if args.max_bytes:
        policy["max_bytes_per_source"] = args.max_bytes

    collected = []
    skipped = []
    seen_hashes = set()
    sources = select_sources(config, args.source_id, args.max_sources)

    for index, source in enumerate(sources):
        source_type = source_kind(source)
        if source_type == "local_file":
            result = fetch_local_file(source)
        elif source_type == "url":
            result = fetch_url(source, policy)
        else:
            result = {"ok": False, "skip_reason": f"unsupported_source_type:{source_type}", "source_id": source.get("id")}

        if not result.get("ok"):
            skipped.append(result)
        else:
            text = result.get("text", "")
            digest = content_hash(text)
            if digest in seen_hashes:
                skipped.append({"source_id": source.get("id"), "skip_reason": "duplicate_content"})
            else:
                seen_hashes.add(digest)
                keywords = source_keywords(config, source)
                snippets = extract_snippets(text, keywords)
                matched = match_abilities(" ".join(snippets) or text)
                result.update(
                    {
                        "content_hash": digest,
                        "collected_at": now_iso(),
                        "job_role": source.get("job_role") or config.get("target_job_role"),
                        "snippets": snippets,
                        "matched_abilities": matched,
                    }
                )
                collected.append(result)

        if source_type == "url" and index + 1 < len(sources):
            time.sleep(float(policy.get("request_interval_seconds", 2)))

    return collected, skipped


def build_material(collected: list[dict[str, Any]]) -> str:
    blocks = []
    for item in collected:
        ability_hints = " ".join(match["ability_id"] for match in item.get("matched_abilities", [])[:8])
        snippets = "\n".join(f"- {snippet}" for snippet in item.get("snippets", []))
        blocks.append(
            "\n".join(
                [
                    f"source_id: {item.get('source_id')}",
                    f"source: {item.get('source')}",
                    f"job_role: {item.get('job_role')}",
                    f"ability_hints: {ability_hints}",
                    "material_snippets:",
                    snippets,
                ]
            )
        )
    return "\n\n".join(blocks)


def generate_proposals(material: str, collected: list[dict[str, Any]]) -> dict[str, Any]:
    from app.services.graph_update_engine import generate_job_graph_proposals

    source_labels = [item.get("source") or item.get("source_id") for item in collected]
    return generate_job_graph_proposals(
        {
            "material": material,
            "source_type": "job_intelligence_update",
            "source": "; ".join(source_labels),
        }
    )


def ingest_collected_sources(
    collected: list[dict[str, Any]],
    use_llm: bool = False,
    max_abilities: int = 5,
) -> dict[str, Any]:
    """Write collected authorized job materials into the SQLite evidence pipeline."""
    from scripts.pipeline.job_data_importer import SUPPORTED_SUFFIXES, import_path, ingest_job_text

    results = []
    for item in collected:
        job_role = item.get("job_role") or "自动化生产线装调与运维技术员"
        source_type = item.get("source_type", "job_intelligence_update")
        source = item.get("source") or item.get("source_id") or "job_intelligence_update"
        path_text = item.get("path")
        path = Path(path_text) if path_text else None

        if path and path.exists() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            imported = import_path(
                path,
                job_role=job_role,
                source_type=source_type,
                source=source,
                use_llm=use_llm,
                max_abilities=max_abilities,
            )
            results.append({
                "source_id": item.get("source_id"),
                "source": source,
                "document_count": imported["document_count"],
                "event_count": imported["event_count"],
                "proposal_count": imported["proposal_count"],
            })
            continue

        text = item.get("text") or "\n".join(item.get("snippets", []))
        imported = ingest_job_text(
            text,
            job_role=job_role,
            source_type=source_type,
            source=source,
            source_url=item.get("url", ""),
            use_llm=use_llm,
            max_abilities=max_abilities,
        )
        results.append({
            "source_id": item.get("source_id"),
            "source": source,
            "document_count": 1,
            "event_count": len(imported["events_created"]),
            "proposal_count": len(imported["proposals_generated"]),
        })

    return {
        "document_count": sum(item["document_count"] for item in results),
        "event_count": sum(item["event_count"] for item in results),
        "proposal_count": sum(item["proposal_count"] for item in results),
        "sources": results,
    }


def summary_from_matches(collected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for item in collected:
        for match in item.get("matched_abilities", []):
            ability_id = match["ability_id"]
            bucket = totals.setdefault(ability_id, {"ability_id": ability_id, "hit_count": 0, "evidence_terms": []})
            bucket["hit_count"] += match["hit_count"]
            for term in match.get("evidence_terms", []):
                if term not in bucket["evidence_terms"]:
                    bucket["evidence_terms"].append(term)
    return sorted(totals.values(), key=lambda item: (-item["hit_count"], item["ability_id"]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update job graph proposals from approved job intelligence sources.")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES), help="Path to job intelligence source config JSON.")
    parser.add_argument("--source-id", help="Run only one enabled source id.")
    parser.add_argument("--dry-run", action="store_true", help="Collect and summarize without writing proposals or run log.")
    parser.add_argument("--max-sources", type=int, help="Override max enabled sources for this run.")
    parser.add_argument("--timeout", type=int, help="Override network timeout in seconds.")
    parser.add_argument("--max-bytes", type=int, help="Override max bytes per source.")
    parser.add_argument("--run-log", default=str(DEFAULT_RUN_LOG), help="Runtime log path for non-dry runs.")
    parser.add_argument(
        "--store",
        choices=["sqlite", "legacy", "both"],
        default="sqlite",
        help="Where non-dry runs write proposals. sqlite uses the evidence-driven backend.",
    )
    parser.add_argument("--use-llm", action="store_true", help="Use the configured LLM as an auxiliary extractor.")
    parser.add_argument("--max-abilities", type=int, default=5, help="Max abilities to extract per collected source.")
    return parser.parse_args()


def run_update(args: argparse.Namespace) -> dict[str, Any]:
    config = read_json(resolve_path(args.sources))
    if not config_policy(config).get("enabled", True):
        return {"ok": False, "reason": "job_intelligence_policy_disabled"}

    collected, skipped = collect(config, args)
    material = build_material(collected)
    matched_abilities = summary_from_matches(collected)

    output: dict[str, Any] = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "collected_at": now_iso(),
        "source_config": str(resolve_path(args.sources)),
        "collected_count": len(collected),
        "skipped_sources": skipped,
        "matched_abilities": matched_abilities[:12],
        "collected_sources": [
            {
                "source_id": item.get("source_id"),
                "source": item.get("source"),
                "source_type": item.get("source_type"),
                "content_hash": item.get("content_hash"),
                "snippet_count": len(item.get("snippets", [])),
            }
            for item in collected
        ],
    }

    if collected and not args.dry_run:
        total_proposals = 0
        if args.store in {"sqlite", "both"}:
            sqlite_result = ingest_collected_sources(
                collected,
                use_llm=bool(args.use_llm),
                max_abilities=int(args.max_abilities or 5),
            )
            output["sqlite_ingest"] = sqlite_result
            total_proposals += sqlite_result["proposal_count"]
        if args.store in {"legacy", "both"}:
            proposal_result = generate_proposals(material, collected)
            output["proposal_batch_id"] = proposal_result.get("batch_id")
            output["legacy_proposal_count"] = len(proposal_result.get("proposals", []))
            total_proposals += output["legacy_proposal_count"]
        else:
            output["proposal_batch_id"] = None
            output["legacy_proposal_count"] = 0
        output["proposal_count"] = total_proposals
        append_run_log(resolve_path(args.run_log), output)
    else:
        output["proposal_batch_id"] = None
        output["legacy_proposal_count"] = 0
        output["proposal_count"] = 0

    return output


def main() -> int:
    output = run_update(parse_args())
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
