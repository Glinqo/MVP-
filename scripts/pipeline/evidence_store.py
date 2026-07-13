# -*- coding: utf-8 -*-
"""Evidence store - thin wrapper over SQLite store.
Backward-compatible API for existing code.
Keeps all original function names (create_event, list_snapshots, etc.)"""
from scripts.pipeline.sqlite_store import (
    add_event as sqlite_add_event,
    query_events as sqlite_query_events,
    ability_evidence_summary,
    add_proposal, get_pending_proposals, confirm_proposal, reject_proposal, get_proposal_history,
    create_snapshot as sqlite_create_snapshot,
    list_versions as sqlite_list_versions,
    get_snapshot as sqlite_get_snapshot,
    get_version_diff,
    rollback_to_version,
    compute_proposal_score,
    proposal_threshold,
    query_log as sqlite_query_log,
    close as sqlite_close,
    migrate_from_json,
)

# ── Backward-compatible aliases ──────────────────────────────────

def create_event(job_role, ability_id, evidence_text, source_url="",
                 source_type="unknown", extraction_method="rule_lexicon_v1",
                 confidence=0.5, metadata=None):
    """Alias for add_event (old API)"""
    return sqlite_add_event(job_role, ability_id, evidence_text, source_type,
                            source_url, extraction_method, confidence, metadata)


def query_events(job_role=None, ability_id=None, source_type=None,
                 days_back=None, limit=50):
    """Query evidence events"""
    return sqlite_query_events(ability_id=ability_id, source_type=source_type,
                               job_role=job_role, days_back=days_back, limit=limit)


def get_event(event_id):
    """Get a single event by ID"""
    evs = sqlite_query_events(limit=1000)
    for ev in evs:
        if ev["event_id"] == event_id:
            return ev
    return None


def create_snapshot(job_role, nodes, dimensions, version_label=None):
    """Alias for sqlite_create_snapshot"""
    return sqlite_create_snapshot(job_role, nodes, dimensions, version_label)


def list_snapshots(job_role=None):
    """Alias for list_versions (old API compatibility)"""
    return sqlite_list_versions(job_role)


def get_snapshot(version, job_role=None):
    """Get snapshot by version string"""
    return sqlite_get_snapshot(version)


def compute_confidence(source_type, match_count, total_sources):
    """Compute confidence from source type and coverage (old API)"""
    ratio = match_count / max(total_sources, 1)
    return compute_proposal_score(source_type, 0.7 + ratio * 0.2, match_count, 30)


def audit_log(date_str=None, action=None, limit=100):
    """Query audit log (old API compatibility)"""
    return sqlite_query_log(action=action, limit=limit)


def close():
    """Close SQLite connection"""
    sqlite_close()


# ── Auto-migrate old JSON data ──────────────────────────────────

def _auto_migrate():
    import json
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    old_dir = ROOT / "data" / "evidence" / "events"
    if old_dir.exists() and any(old_dir.glob("*.json")):
        result = migrate_from_json()
        for f in old_dir.glob("*.json"):
            f.rename(f.with_suffix(".json.migrated"))
        return result
    return {"migrated": False}

_auto_migrate()
def version_diff(v1, v2, job_role=None):
    """Alias for get_version_diff"""
    from scripts.pipeline.sqlite_store import get_version_diff as gvd
    return gvd(v1, v2)


def version_rollback(target_version, job_role=None):
    """Alias for rollback_to_version"""
    from scripts.pipeline.sqlite_store import rollback_to_version as rtv
    return rtv(target_version, job_role)

def add_event(job_role, ability_id, evidence_text, source_url="",
              source_type="unknown", extraction_method="rule_lexicon_v1",
              confidence=0.5, metadata=None):
    """Direct alias for sqlite_add_event"""
    return sqlite_add_event(job_role, ability_id, evidence_text, source_type,
                            source_url, extraction_method, confidence, metadata)
