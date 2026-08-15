#!/usr/bin/env python3
"""V1 -> V2 Learning Event Migration Script.
Usage:
  python scripts/migrate_v1_events_to_v2.py --dry-run
  python scripts/migrate_v1_events_to_v2.py --apply
  python scripts/migrate_v1_events_to_v2.py --status
  python scripts/migrate_v1_events_to_v2.py --dry-run --student 000 --limit 10
"""

import argparse, json, hashlib, os, sqlite3, sys
from datetime import datetime, timezone
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from knowledge.ability_id_aliases import resolve_ability_id
from app.services.evidence.event_schema import normalize_event, SCHEMA_VERSION
from app.services.evidence.event_store import EventStore, get_event_store

MIGRATION_VERSION = "v2-5b-1"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

class MigrationScanner:
    def __init__(self):
        self.stats = defaultdict(int)
        self.unresolved_abilities = set()
        self.unresolved_students = set()
        self.unresolved_sessions = set()
        self.events: List[Dict] = []
        self.invalid: List[Dict] = []

    def scan(self, student_filter: str = "", limit: int = 0):
        self._scan_sessions(student_filter, limit)
        self._scan_assessments(student_filter, limit)
        return self

    def _scan_sessions(self, student_filter: str, limit: int):
        sd = os.path.join(DATA_DIR, "sessions")
        if not os.path.exists(sd): return
        for f in sorted(os.listdir(sd)):
            if not f.endswith(".json"): continue
            fp = os.path.join(sd, f)
            try:
                with open(fp, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                events = data if isinstance(data, list) else data.get("events", [])
                for ev in events:
                    self.stats["scanned"] += 1
                    if student_filter and student_filter not in str(ev.get("actor_id", ev.get("student_id", ""))): continue
                    self._process_event(ev, "session_json", f)
                    if 0 < limit <= self.stats["migratable"]: return
            except Exception as e:
                self.stats["parse_errors"] += 1

    def _scan_assessments(self, student_filter: str, limit: int):
        adb = os.path.join(DATA_DIR, "assessments.db")
        if not os.path.exists(adb): return
        conn = sqlite3.connect(adb)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM assessment_events").fetchall()
            for row in rows:
                self.stats["scanned"] += 1
                sid = row["student_id"] if "student_id" in row.keys() else str(row[1])
                if student_filter and student_filter not in str(sid): continue
                d = dict(row)
                d["source_type"] = "assessment_db"
                self._process_event(d, "assessment_db", f"assessments.db/assessment_events/{d.get('id','?')}")
                if 0 < limit <= self.stats["migratable"]: return
        except Exception as e:
            pass
        finally:
            conn.close()

    def _process_event(self, ev: Dict, source_type: str, source_path: str):
        sid = ev.get("student_id") or ev.get("actor_id") or ev.get("username") or ""
        aid = ev.get("ability_id") or (ev.get("context", {}) or {}).get("ability_ids", [None])[0] or ""
        session = ev.get("session_id") or ""

        # Check ability
        canonical_aid = resolve_ability_id(aid) if aid else ""
        if aid and canonical_aid == aid and not aid.startswith(("rt_","es_","sn_","pl_","tr_")): self.unresolved_abilities.add(aid); self.stats["ability_unmapped"] += 1
            self.unresolved_abilities.add(aid)
            canonical_aid = aid
        if not sid:
            self.unresolved_students.add("unknown")
            self.stats["student_unresolved"] += 1
            return

        # Build legacy source key for event_id hash
        legacy_key = f"{source_type}|{source_path}|{ev.get('id','')}|{ev.get('timestamp','')}|{sid}"
        canonical_event_id = "MIG_" + hashlib.sha256(legacy_key.encode()).hexdigest()[:12]

        self.events.append({
            "canonical_event_id": canonical_event_id,
            "legacy_key": legacy_key,
            "raw": ev,
            "student_id": sid,
            "ability_id": canonical_aid,
            "source_type": source_type,
            "source_path": source_path,
        })
        self.stats["migratable"] += 1

    def print_summary(self):
        print(f"Scanned records:     {self.stats['scanned']}")
        print(f"Learning facts:      {self.stats['migratable']}")
        print(f"Already migrated:    {self.stats.get('already_migrated', 0)}")
        print(f"Skipped projections: {self.stats.get('skipped_projections', 0)}")
        print(f"Skipped duplicates:  {self.stats.get('skipped_duplicates', 0)}")
        print(f"Ability unmapped:    {self.stats['ability_unmapped']}")
        print(f"Student unresolved:  {self.stats['student_unresolved']}")
        print(f"Session unresolved:  {self.stats['session_unresolved']}")
        print(f"Invalid schema:      {self.stats.get('invalid_schema', 0)}")
        print(f"Parse errors:        {self.stats.get('parse_errors', 0)}")


class MigrationApplier:
    def __init__(self):
        self.store = get_event_store()
        self.stats = {"written": 0, "already_exist": 0, "failed": 0}

    def apply(self, events: List[Dict]) -> dict:
        for ev in events:
            raw = ev["raw"]
            raw["event_id"] = ev["canonical_event_id"]
            raw["source"] = "v1_migration"
            raw.setdefault("verb", "assessment_answer")
            try:
                v2_event = normalize_event(raw)
                ok = self.store.insert_event(v2_event, idempotency_key=ev["canonical_event_id"])
                if ok:
                    self.stats["written"] += 1
                else:
                    self.stats["already_exist"] += 1
            except Exception as e:
                self.stats["failed"] += 1
        return dict(self.stats)

    def status(self) -> dict:
        total = self.store.count_events()
        return {"v2_event_total": total, "migration_version": MIGRATION_VERSION}


def main():
    p = argparse.ArgumentParser(description="V1->V2 Event Migration")
    p.add_argument("--dry-run", action="store_true", help="Scan only, no writes")
    p.add_argument("--apply", action="store_true", help="Execute migration")
    p.add_argument("--status", action="store_true", help="Show migration status")
    p.add_argument("--student", default="", help="Filter by student")
    p.add_argument("--limit", type=int, default=0, help="Limit records")
    args = p.parse_args()

    print("V1 -> V2 migration tool")
    print(f"Migration version: {MIGRATION_VERSION}\n")

    scanner = MigrationScanner()
    scanner.scan(args.student, args.limit)

    if args.dry_run:
        scanner.print_summary()
        print("\nNo writes performed.")
    elif args.apply:
        applier = MigrationApplier()
        result = applier.apply(scanner.events)
        print(f"Written: {result['written']}")
        print(f"Already exist: {result['already_exist']}")
        print(f"Failed: {result['failed']}")
    elif args.status:
        applier = MigrationApplier()
        s = applier.status()
        print(f"V2 EventStore total: {s['v2_event_total']}")
        print(f"Migration version: {s['migration_version']}")
        scanner.print_summary()

if __name__ == "__main__":
    main()
