#!/usr/bin/env python3
"""V1->V2 Simplified Migration - uses V2 EventBus directly."""

import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.v2_facade import emit_event
from knowledge.ability_id_aliases import resolve_ability_id

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

scanned = migrated = failed = skipped_unmapped = 0
unmapped_ids = set()

# Scan sessions
sd = os.path.join(DATA_DIR, "sessions")
if os.path.exists(sd):
    for fname in sorted(os.listdir(sd)):
        if not fname.endswith(".json"): continue
        with open(os.path.join(sd, fname), "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data if isinstance(data, list) else data.get("events", [])
        for ev in events:
            scanned += 1
            aid = ev.get("ability_id", "")
            canonical = resolve_ability_id(aid) if aid else ""
            if not canonical or (canonical == aid and not aid.startswith(("rt_","es_","sn_","pl_","tr_"))):
                unmapped_ids.add(aid)
                skipped_unmapped += 1
                continue
            raw = {
                "event_id": f"MIG_{fname}_{ev.get('event_id','')}",
                "actor_id": ev.get("session_id", "").split("-")[0] if ev.get("session_id") else "000",
                "student_id": ev.get("session_id", "").split("-")[0] if ev.get("session_id") else "000",
                "verb": ev.get("event_type", "assessment_answer"),
                "object_id": ev.get("question_id", ev.get("object_id", "")),
                "result": {"outcome": "correct" if ev.get("is_correct") else "incorrect"},
                "ability_id": canonical,
                "ability_ids": [canonical],
                "context": {"session_id": ev.get("session_id", ""), "job_role": ev.get("job_role", "")},
                "occurred_at": ev.get("timestamp", ""),
                "source": "v1_migration",
            }
            try:
                result = emit_event(raw)
                migrated += 1
            except Exception as e:
                failed += 1

print(f"Migration complete: scanned={scanned}, migrated={migrated}, skipped_unmapped={skipped_unmapped}, failed={failed}")
if unmapped_ids:
    print(f"Unmapped ability IDs ({len(unmapped_ids)}): {sorted(unmapped_ids)}")
