# -*- coding: utf-8 -*-
"""Evidence event storage module."""
import hashlib, json, threading, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVENTS_DIR = ROOT / "data" / "evidence" / "events"
SNAPSHOTS_DIR = ROOT / "data" / "evidence" / "snapshots"
AUDIT_LOG_DIR = ROOT / "data" / "evidence" / "audit_log"
INDEX_FILE = ROOT / "data" / "evidence" / "event_index.json"
_lock = threading.Lock()

def _ensure_dirs():
    for d in [EVENTS_DIR, SNAPSHOTS_DIR, AUDIT_LOG_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def _hash_url(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]

def _content_hash(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]

def _load_index():
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return {"events": [], "event_by_url": {}, "version_sequence": {}}

def _save_index(index):
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

def create_event(job_role, ability_id, evidence_text, source_url, source_type, extraction_method="rule_lexicon_v1", confidence=0.5, metadata=None):
    _ensure_dirs()
    url_hash = _hash_url(source_url) if source_url else "nolink"
    content_digest = _content_hash(evidence_text)
    dedup_key = f"{url_hash}:{content_digest}"
    with _lock:
        index = _load_index()
        if dedup_key in index["event_by_url"]:
            return {"event_id": index["event_by_url"][dedup_key], "deduplicated": True}
        prefix = "EVT"
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        seq_key = f"{prefix}-{date_str}"
        seq = index["version_sequence"].get(seq_key, 0) + 1
        index["version_sequence"][seq_key] = seq
        event_id = f"{prefix}-{date_str}-{seq:04d}"
        event = {
            "event_id": event_id, "job_role": job_role, "ability_id": ability_id,
            "evidence": evidence_text, "source_url": source_url, "source_type": source_type,
            "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "extraction_method": extraction_method, "confidence": round(confidence, 2),
            "url_hash": url_hash, "content_hash": content_digest, "metadata": metadata or {},
        }
        (EVENTS_DIR / f"{event_id}.json").write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")
        index["events"].append(event_id)
        index["event_by_url"][dedup_key] = event_id
        _save_index(index)
    _audit("event_created", event_id, {"job_role": job_role, "ability_id": ability_id})
    return {"event_id": event_id, "deduplicated": False}

def get_event(event_id):
    ef = EVENTS_DIR / f"{event_id}.json"
    return json.loads(ef.read_text(encoding="utf-8")) if ef.exists() else None

def query_events(job_role=None, ability_id=None, source_type=None, days_back=None, limit=50):
    index = _load_index()
    results = []
    cutoff = time.time() - days_back * 86400 if days_back is not None else None
    for eid in reversed(index["events"]):
        ev = get_event(eid)
        if not ev: continue
        if job_role and ev["job_role"] != job_role: continue
        if ability_id and ev["ability_id"] != ability_id: continue
        if source_type and ev["source_type"] != source_type: continue
        if cutoff:
            try:
                et = datetime.strptime(ev["extracted_at"], "%Y-%m-%dT%H:%M:%SZ").timestamp()
                if et < cutoff: continue
            except ValueError: pass
        results.append(ev)
        if len(results) >= limit: break
    return results

def create_snapshot(job_role, nodes, dimensions, version_label=None):
    _ensure_dirs()
    safe = job_role.replace(" ", "_").replace("/", "_")
    role_dir = SNAPSHOTS_DIR / safe
    role_dir.mkdir(parents=True, exist_ok=True)
    version = version_label or datetime.now(timezone.utc).strftime("v%Y%m%d.%H%M%S")
    snap = {"version": version, "job_role": job_role, "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "node_count": len(nodes), "dimension_scores": dimensions, "nodes": nodes, "source": "evidence_derived"}
    (role_dir / f"{version}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    _audit("snapshot_created", version, {"job_role": job_role, "node_count": len(nodes)})
    return {"version": version}

def list_snapshots(job_role=None):
    _ensure_dirs()
    all_snaps = []
    dirs = [SNAPSHOTS_DIR / job_role.replace(" ", "_").replace("/", "_")] if job_role else sorted(SNAPSHOTS_DIR.iterdir())
    for d in dirs:
        if d.is_dir():
            for f in sorted(d.glob("*.json")):
                all_snaps.append(json.loads(f.read_text(encoding="utf-8")))
    return all_snaps

def _audit(action, entity_id, detail=None):
    _ensure_dirs()
    entry = {"timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "action": action, "entity_id": entity_id, "detail": detail or {}}
    with _lock:
        with open(AUDIT_LOG_DIR / f"{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\\n")

def audit_log(date_str=None, action=None, limit=100):
    _ensure_dirs()
    entries = []
    logs = [AUDIT_LOG_DIR / f"{date_str}.jsonl"] if date_str else sorted(AUDIT_LOG_DIR.glob("*.jsonl"))
    for lf in logs:
        if lf.exists():
            for line in lf.read_text(encoding="utf-8").strip().split("\\n"):
                if not line.strip(): continue
                entry = json.loads(line)
                if action and entry["action"] != action: continue
                entries.append(entry)
    return entries[-limit:]

def compute_confidence(source_type, match_count, total_sources):
    base = {"enterprise_official": 0.85, "job_platform": 0.65, "government_standard": 0.90, "local_file": 0.70, "education_standard": 0.80, "industry_report": 0.60}
    return min(0.95, base.get(source_type, 0.5) + (match_count / max(total_sources, 1)) * 0.15)
def get_snapshot(version, job_role=None):
    """Get a specific snapshot by version label"""
    all_snaps = list_snapshots(job_role)
    for s in all_snaps:
        if s["version"] == version:
            return s
    return None


def version_diff(v1, v2, job_role=None):
    """Compare two version snapshots"""
    snap1 = get_snapshot(v1, job_role)
    snap2 = get_snapshot(v2, job_role)
    if not snap1 or not snap2:
        return {"error": "version not found"}
    nodes1 = {n["id"]: n for n in snap1.get("nodes", [])}
    nodes2 = {n["id"]: n for n in snap2.get("nodes", [])}
    added = [n for nid, n in nodes2.items() if nid not in nodes1]
    removed = [n for nid, n in nodes1.items() if nid not in nodes2]
    changed = []
    for nid, n2 in nodes2.items():
        if nid in nodes1:
            n1 = nodes1[nid]
            diffs = {}
            for key in ("weight", "demand_weight", "confidence", "mastery_score"):
                if n1.get(key) != n2.get(key):
                    diffs[key] = {"from": n1.get(key), "to": n2.get(key)}
            if diffs:
                changed.append({"id": nid, "name": n2.get("name"), "changes": diffs})
    dims1 = snap1.get("dimension_scores", {})
    dims2 = snap2.get("dimension_scores", {})
    dim_diff = {}
    for k in set(list(dims1.keys()) + list(dims2.keys())):
        if dims1.get(k) != dims2.get(k):
            dim_diff[k] = {"from": dims1.get(k), "to": dims2.get(k)}
    return {
        "v1": v1, "v2": v2,
        "v1_created": snap1.get("created_at"),
        "v2_created": snap2.get("created_at"),
        "added": added, "removed": removed, "changed": changed,
        "dimension_changes": dim_diff,
        "has_changes": bool(added or removed or changed or dim_diff)
    }


def version_rollback(target_version, job_role=None):
    """Rollback by creating a new snapshot with the same data"""
    snap = get_snapshot(target_version, job_role)
    if not snap:
        return {"error": "version not found"}
    new_ver = target_version + "-restored"
    r = create_snapshot(snap["job_role"], snap["nodes"], snap.get("dimension_scores", {}), new_ver)
    _audit("rollback", new_ver, {"from": target_version})
    return {"version": new_ver, "restored_from": target_version}
