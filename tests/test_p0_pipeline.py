# -*- coding: utf-8 -*-
"""Phase 0 Pipeline Tests"""
import json, sys, os, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_TMP_DB = tempfile.TemporaryDirectory()
os.environ["MVP_EVIDENCE_DB_PATH"] = str(Path(_TMP_DB.name) / "evidence.db")

from scripts.crawler_framework import load_sources, get_crawler, BaseCrawler
from scripts.pipeline.cleaner import extract_skill_spans, map_skills_to_abilities, normalize_title, load_lexicon, load_ability_nodes
from scripts.pipeline.evidence_store import create_event, query_events, create_snapshot, compute_confidence, audit_log, list_snapshots

passed = 0
failed = 0

def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name}")

print("=== Phase 0 Pipeline Tests ===")

print("\n--- 1. Source Configuration ---")
srcs = load_sources()
check("sources loaded", len(srcs) > 0)
check("demo_sample_jd configured", any(s["id"] == "demo_sample_jd" for s in srcs))
check("platform sources configured", any(s["source_type"] == "job_platform" for s in srcs))
check("enterprise sources configured", any(s["source_type"] == "enterprise_official" for s in srcs))

print("\n--- 2. Lexicon & NLP ---")
lex = load_lexicon()
check("lexicon loaded", len(lex.get("lexicon", {})) > 0)
check("hard_skills defined", len(lex.get("lexicon", {}).get("hard_skills", {})) > 0)
check("job_titles defined", len(lex.get("lexicon", {}).get("job_title_normalization", {})) > 0)

skills = extract_skill_spans("负责PLC接线调试、传感器故障排查")
check("skill extraction works", len(skills) >= 3)
check("PLC matched", any(s["term"] == "PLC" for s in skills))
check("sensor matched", any("传感器" in s["term"] for s in skills))

nodes = load_ability_nodes()
check("ability nodes loaded", len(nodes) >= 10)

abilities = map_skills_to_abilities(skills, nodes)
check("ability mapping works", len(abilities) > 0)

title, iid = normalize_title("自动化设备调试工程师")
check("title normalization works", iid is not None or title is not None)

print("\n--- 3. Evidence Store ---")
ev1 = create_event("测试岗位", "test_ability", "测试证据1", "http://test.com", "test", "manual", 0.8)
check("event creation", not ev1.get("error"))
check("event has id", len(ev1.get("event_id", "")) > 0)

ev2 = create_event("测试岗位", "test_ability", "测试证据1", "http://test.com", "test", "manual", 0.8)
check("dedup works", ev2.get("deduplicated") is True)

ev3 = create_event("测试岗位", "test_ability", "测试证据2", "http://test2.com", "test", "manual", 0.9)
check("different event created", not ev3.get("deduplicated"))
check("different event id", ev3["event_id"] != ev1["event_id"])

events = query_events(limit=10)
check("query returns results", len(events) > 0)
check("events have ability_id", all(e.get("ability_id") for e in events))

conf = compute_confidence("enterprise_official", 5, 10)
check("confidence enterprise", 0.80 <= conf <= 0.95)
conf2 = compute_confidence("job_platform", 2, 10)
check("confidence platform lower", conf2 < conf)

snap = create_snapshot("测试岗位", nodes, {"dim1": 0.8}, "v0.1.0-test")
check("snapshot created", "version" in snap)

snaps = list_snapshots("测试岗位")
check("snapshot queryable", len(snaps) > 0)

logs = audit_log()
check("audit trail exists", len(logs) > 0)

print("\n--- 4. Pipeline Runner ---")
from scripts.pipeline.runner import DEFAULT_JOB_ROLE
check("runner module loads", True)

local_src = [s for s in srcs if s["id"] == "demo_sample_jd"]
check("demo source available", len(local_src) > 0)
if local_src:
    c = get_crawler(local_src[0])
    check("crawler created", c is not None)
    posts = c.load_local_posts()
    check("local posts loaded", len(posts) == 5)
    if posts:
        check("posts have titles", all(p.get("title") for p in posts))
        check("posts have skills", any(p.get("skills") for p in posts))

platform_src = [s for s in srcs if s["id"] == "zhilian_zhaopin"]
if platform_src:
    c2 = get_crawler(platform_src[0])
    check("platform crawler dispatch", c2.__class__.__name__ == "ZhilianCrawler")

enterprise_src = [s for s in srcs if s["id"] == "siemens_career"]
if enterprise_src:
    c3 = get_crawler(enterprise_src[0])
    check("enterprise crawler dispatch", c3.__class__.__name__ == "EnterpriseCrawler")

print(f"\n=== Results: {passed} passed, {failed} failed out of {passed + failed} ===")
try:
    from scripts.pipeline.evidence_store import close
    close()
finally:
    _TMP_DB.cleanup()
sys.exit(0 if failed == 0 else 1)
