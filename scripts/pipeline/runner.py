#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pipeline CLI runner - list sources, dry-run, run pipeline, query events"""
import json, sys, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.crawler_framework import load_sources, get_crawler, BaseCrawler
from scripts.pipeline.cleaner import extract_skill_spans, map_skills_to_abilities, normalize_title
from scripts.pipeline.evidence_store import create_event, query_events, create_snapshot, compute_confidence

DEFAULT_JOB_ROLE = "\u81ea\u52a8\u5316\u751f\u4ea7\u7ebf\u88c5\u8c03\u4e0e\u8fd0\u7ef4\u6280\u672f\u5458"

def cmd_list(args):
    srcs = load_sources()
    print(f"{'ID':30s} {'Name':15s} {'Type':20s} {'Status'}")
    print("-" * 75)
    for s in srcs:
        e = "ENABLED" if s.get("enabled") else "disabled"
        print(f"{s.get('id',''):30s} {s.get('name',''):15s} {s.get('source_type',''):20s} {e}")

def cmd_dry_run(args):
    srcs = load_sources()
    target = [s for s in srcs if s.get("id") == args.source_id] if args.source_id else [s for s in srcs if s.get("enabled")]
    for s in target[:1]:
        c = get_crawler(s)
        print(f"Dry-run: {s.get('name')} ({s.get('id')})")
        if s.get("source_type") == "local_file":
            posts = c.load_local_posts()
            print(f"  Local posts loaded: {len(posts)}")
            for p in posts[:3]:
                print(f"    Title: {p.get('title','')[:50]}")
        else:
            result = c.dry_run()
            print(f"  Result: {json.dumps(result, ensure_ascii=False)}")

def cmd_run(args):
    srcs = load_sources()
    target = [s for s in srcs if s.get("id") == args.source_id] if args.source_id else [s for s in srcs if s.get("enabled")]
    total_events = 0
    for s in target:
        c = get_crawler(s)
        print(f"Running: {s.get('name')} ({s.get('id')})")
        posts = c.load_local_posts() if s.get("source_type") == "local_file" else c.crawl()
        print(f"  Fetched: {len(posts)} posts")
        for post in posts:
            text = " ".join(filter(None, [post.get("title",""), " ".join(post.get("responsibilities",[])), " ".join(post.get("skills",[]))]))
            skills = extract_skill_spans(text)
            abilities = map_skills_to_abilities(skills)
            if abilities:
                for a in abilities[:3]:
                    ev = create_event(DEFAULT_JOB_ROLE, a["ability_id"], post.get("title",""), s.get("base_url","local"), s.get("source_type","local_file"), "rule_lexicon_v1", compute_confidence(s.get("source_type","local_file"), len(abilities), 10))
                    if not ev.get("deduplicated"): total_events += 1
        print(f"  Events created this run: {total_events}")
    print(f"Total new evidence events: {total_events}")

def cmd_events(args):
    events = query_events(job_role=args.job_role or None, ability_id=args.ability_id or None, source_type=args.source_type or None, limit=args.limit)
    print(f"Events found: {len(events)}")
    for ev in events[:10]:
        print(f"  {ev['event_id']} | {ev['ability_id']} | conf={ev['confidence']} | {ev['source_type']}")

def cmd_snapshot(args):
    from scripts.pipeline.cleaner import load_ability_nodes
    nodes = load_ability_nodes()
    dims = {"electrical_safety": 0.85, "sensor": 0.72, "plc": 0.68, "troubleshooting": 0.60}
    r = create_snapshot(args.job_role, nodes, dims, version_label=args.version)
    print(f"Snapshot created: {r['version']}")

def cmd_lexicon(args):
    text = args.text or "\u8d1f\u8d23PLC\u63a5\u7ebf\u8c03\u8bd5\u3001\u4f20\u611f\u5668\u6545\u969c\u6392\u67e5\u3001\u7535\u6c14\u5b89\u5168\u68c0\u67e5"
    skills = extract_skill_spans(text)
    print(f"Input: {text}")
    print(f"Skills found: {len(skills)}")
    for s in skills[:10]:
        print(f"  {s['term']} [{s['category']}]")

def main():
    p = argparse.ArgumentParser(description="Job Ability Graph Pipeline")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("list", help="List configured sources")

    dr = sub.add_parser("dry-run", help="Dry-run a source (test parsing)")
    dr.add_argument("--source-id", default="")

    rn = sub.add_parser("run", help="Run full collection pipeline")
    rn.add_argument("--source-id", default="")

    ev = sub.add_parser("events", help="Query stored evidence events")
    ev.add_argument("--job-role", default="")
    ev.add_argument("--ability-id", default="")
    ev.add_argument("--source-type", default="")
    ev.add_argument("--limit", type=int, default=10)

    sn = sub.add_parser("snapshot", help="Create a version snapshot")
    sn.add_argument("--job-role", default=DEFAULT_JOB_ROLE)
    sn.add_argument("--version", default="")

    lx = sub.add_parser("lexicon", help="Test skill lexicon extraction")
    lx.add_argument("--text", default="")

    args = p.parse_args()
    dispatch = {"list": cmd_list, "dry-run": cmd_dry_run, "run": cmd_run, "events": cmd_events, "snapshot": cmd_snapshot, "lexicon": cmd_lexicon}
    dispatch.get(args.command, lambda a: p.print_help())(args)

if __name__ == "__main__":
    main()