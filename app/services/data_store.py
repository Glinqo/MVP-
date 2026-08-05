"""Unified data store - single entry point for all persistent storage.

All JSON read/write for sessions, events, snapshots, and evidence
goes through this module. Other services should import from here
instead of using json.load/dump directly.

Layers:
  - Session store: session JSON files in data/sessions/
  - Event store: events inside session files (read via learning_event_store)
  - Snapshot store: versioned graph snapshots in data/snapshots/
  - Evidence store: evidence events in SQLite (scripts/pipeline/sqlite_store.py)
  - Knowledge store: read-only knowledge files in knowledge/ (via data_loader.py)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from .data_loader import ROOT

SESSIONS_DIR = ROOT / "data" / "sessions"
SNAPSHOTS_DIR = ROOT / "data" / "evidence" / "snapshots"
EVIDENCE_DIR = ROOT / "data" / "evidence" / "events"


def _ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)


# ---- Session operations ----

def load_session(session_id):
    """Load a session record. Returns dict with session_id, events[], created_at, updated_at."""
    sid = _safe_id(session_id)
    path = SESSIONS_DIR / f"{sid}.json"
    if not path.exists():
        return {
            "session_id": sid,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "events": [],
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "session_id": sid,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "events": [],
        }


def save_session(record):
    """Save a session record to disk."""
    sid = _safe_id(record.get("session_id", ""))
    record["session_id"] = sid
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    _ensure_dir(SESSIONS_DIR)
    path = SESSIONS_DIR / f"{sid}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def append_event(session_id, event):
    """Append an event to a session and save."""
    record = load_session(session_id)
    event = dict(event or {})
    event.setdefault("event_type", "unknown")
    event["event_id"] = event.get("event_id") or _now_id()
    event["created_at"] = event.get("created_at") or datetime.now(timezone.utc).isoformat()
    events = record.setdefault("events", [])
    if not isinstance(events, list):
        events = []
        record["events"] = events
    events.append(event)
    save_session(record)
    return record


def list_all_sessions():
    """List all session files with metadata."""
    _ensure_dir(SESSIONS_DIR)
    sessions = []
    for p in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
            sessions.append({
                "session_id": rec.get("session_id", p.stem),
                "event_count": len(rec.get("events", [])),
                "created_at": rec.get("created_at"),
                "updated_at": rec.get("updated_at"),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return sessions


# ---- Snapshot operations ----

def load_snapshot(job_role, version=None):
    """Load a graph snapshot. If version is None, load the latest."""
    _ensure_dir(SNAPSHOTS_DIR)
    role_dir = SNAPSHOTS_DIR / _safe_id(job_role or "default")
    if not role_dir.exists():
        return None
    if version:
        path = role_dir / f"{version}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None
    # Latest
    files = sorted(role_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    if files:
        return json.loads(files[0].read_text(encoding="utf-8"))
    return None


def save_snapshot(job_role, version, data):
    """Save a versioned graph snapshot."""
    _ensure_dir(SNAPSHOTS_DIR)
    role_dir = SNAPSHOTS_DIR / _safe_id(job_role or "default")
    _ensure_dir(role_dir)
    path = role_dir / f"{version}.json"
    snapshot = {
        "version": version,
        "job_role": job_role,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def list_snapshots(job_role=None):
    """List all snapshot versions."""
    _ensure_dir(SNAPSHOTS_DIR)
    result = []
    if job_role:
        dirs = [SNAPSHOTS_DIR / _safe_id(job_role)]
    else:
        dirs = [d for d in SNAPSHOTS_DIR.iterdir() if d.is_dir()]
    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                s = json.loads(p.read_text(encoding="utf-8"))
                result.append({
                    "version": s.get("version", p.stem),
                    "job_role": s.get("job_role", d.name),
                    "created_at": s.get("created_at"),
                })
            except (json.JSONDecodeError, OSError):
                continue
    return result


# ---- Evidence event operations (file-based fallback) ----

def save_evidence_event(event):
    """Save a single evidence event to the file-based store."""
    _ensure_dir(EVIDENCE_DIR)
    event_id = event.get("event_id", _now_id())
    path = EVIDENCE_DIR / f"{event_id}.json"
    path.write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")
    return event


def load_evidence_events(ability_id=None, days_back=30):
    """Load evidence events, optionally filtered."""
    _ensure_dir(EVIDENCE_DIR)
    events = []
    cutoff = None
    if days_back:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    for p in EVIDENCE_DIR.glob("*.json"):
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
            if ability_id and ability_id not in ev.get("ability_ids", []):
                continue
            if cutoff:
                created = ev.get("created_at", "")
                if created and created < cutoff.isoformat():
                    continue
            events.append(ev)
        except (json.JSONDecodeError, OSError):
            continue
    return sorted(events, key=lambda e: e.get("created_at", ""), reverse=True)


# ---- Helpers ----

import re
import hashlib

def _safe_id(value):
    raw = str(value or "default")
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", raw)[:80]
    return cleaned or "default"

def _now_id():
    return datetime.now(timezone.utc).strftime("S%Y%m%d%H%M%S%f")

def _generate_event_id(*parts):
    raw = "|".join(str(p) for p in parts)
    return "evt_" + hashlib.md5(raw.encode()).hexdigest()[:12]
