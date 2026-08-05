# -*- coding: utf-8 -*-
"""SQLite storage layer for evidence-driven ability graph."""
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("MVP_EVIDENCE_DB_PATH", ROOT / "data" / "evidence" / "evidence.db"))
DB_DIR = DB_PATH.parent

_lock = threading.Lock()
_connection = None

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS raw_documents (
        document_id TEXT PRIMARY KEY,
        source_type TEXT NOT NULL DEFAULT 'unknown',
        source TEXT DEFAULT '',
        source_url TEXT DEFAULT '',
        content_hash TEXT NOT NULL,
        raw_text TEXT NOT NULL,
        ingested_at TEXT NOT NULL,
        metadata TEXT DEFAULT '{}'
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_doc_dedup ON raw_documents(content_hash, source_url)",
    "CREATE INDEX IF NOT EXISTS idx_doc_source ON raw_documents(source_type)",
    """
    CREATE TABLE IF NOT EXISTS job_posts (
        job_post_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        job_role TEXT NOT NULL,
        raw_title TEXT DEFAULT '',
        normalized_title TEXT DEFAULT '',
        company TEXT DEFAULT '',
        responsibilities TEXT DEFAULT '[]',
        skills TEXT DEFAULT '[]',
        requirements TEXT DEFAULT '[]',
        source_type TEXT NOT NULL DEFAULT 'unknown',
        source_url TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_post_role ON job_posts(job_role)",
    "CREATE INDEX IF NOT EXISTS idx_post_doc ON job_posts(document_id)",
    """
    CREATE TABLE IF NOT EXISTS evidence_events (
        event_id TEXT PRIMARY KEY,
        job_role TEXT NOT NULL,
        ability_id TEXT NOT NULL,
        evidence_text TEXT NOT NULL,
        source_url TEXT DEFAULT '',
        source_type TEXT NOT NULL DEFAULT 'unknown',
        extraction_method TEXT DEFAULT 'rule_lexicon_v1',
        confidence REAL DEFAULT 0.5,
        extracted_at TEXT NOT NULL,
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ev_ability ON evidence_events(ability_id, job_role)",
    "CREATE INDEX IF NOT EXISTS idx_ev_source ON evidence_events(source_type)",
    "CREATE INDEX IF NOT EXISTS idx_ev_time ON evidence_events(extracted_at)",
    """
    CREATE TABLE IF NOT EXISTS proposals (
        proposal_id TEXT PRIMARY KEY,
        job_role TEXT NOT NULL,
        ability_id TEXT NOT NULL,
        action TEXT NOT NULL DEFAULT 'strengthen',
        suggested_weight_delta REAL DEFAULT 0.1,
        evidence TEXT DEFAULT '',
        source TEXT DEFAULT '',
        proposal_score REAL DEFAULT 0.5,
        status TEXT DEFAULT 'pending',
        confirmed_by TEXT DEFAULT '',
        confirmed_at TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_pr_status ON proposals(status)",
    "CREATE INDEX IF NOT EXISTS idx_pr_ability ON proposals(ability_id)",
    """
    CREATE TABLE IF NOT EXISTS snapshots (
        snapshot_id TEXT PRIMARY KEY,
        job_role TEXT NOT NULL,
        version TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        node_count INTEGER DEFAULT 0,
        node_data TEXT NOT NULL DEFAULT '[]',
        dimension_scores TEXT DEFAULT '{}',
        source TEXT DEFAULT 'evidence_derived',
        parent_version TEXT DEFAULT ''
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sn_role ON snapshots(job_role)",
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        action TEXT NOT NULL,
        entity_id TEXT DEFAULT '',
        detail TEXT DEFAULT '{}'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_al_action ON audit_log(action)",
]


def _get_db():
    global _connection
    if _connection is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        _connection = __import__("sqlite3").connect(str(DB_PATH), check_same_thread=False)
        _connection.row_factory = __import__("sqlite3").Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA synchronous=NORMAL")
        _init_tables()
    return _connection


def _init_tables():
    db = _connection
    for stmt in _SCHEMA:
        db.execute(stmt)
    db.commit()


def close():
    global _connection
    if _connection:
        _connection.close()
        _connection = None


def _next_event_id():
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    db = _get_db()
    row = db.execute("SELECT COUNT(*) FROM evidence_events WHERE event_id LIKE ?", (f"EVT-{date_str}%",)).fetchone()
    seq = (row[0] if row else 0) + 1
    return f"EVT-{date_str}-{seq:04d}"


def _next_proposal_id():
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    db = _get_db()
    row = db.execute("SELECT COUNT(*) FROM proposals WHERE proposal_id LIKE ?", (f"PRP-{date_str}%",)).fetchone()
    seq = (row[0] if row else 0) + 1
    return f"PRP-{date_str}-{seq:04d}"


def _next_document_id():
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    db = _get_db()
    row = db.execute("SELECT COUNT(*) FROM raw_documents WHERE document_id LIKE ?", (f"DOC-{date_str}%",)).fetchone()
    seq = (row[0] if row else 0) + 1
    return f"DOC-{date_str}-{seq:04d}"


def _next_job_post_id():
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    db = _get_db()
    row = db.execute("SELECT COUNT(*) FROM job_posts WHERE job_post_id LIKE ?", (f"JOB-{date_str}%",)).fetchone()
    seq = (row[0] if row else 0) + 1
    return f"JOB-{date_str}-{seq:04d}"


def add_raw_document(raw_text, source_type="unknown", source="", source_url="", metadata=None):
    """Store a raw imported or collected job document."""
    db = _get_db()
    text = raw_text or ""
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    existing = db.execute(
        "SELECT document_id FROM raw_documents WHERE content_hash = ? AND source_url = ?",
        (content_hash, source_url),
    ).fetchone()
    if existing:
        return {"document_id": existing[0], "deduplicated": True}

    document_id = _next_document_id()
    ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _lock:
        db.execute(
            """INSERT INTO raw_documents
               (document_id, source_type, source, source_url, content_hash, raw_text, ingested_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                document_id,
                source_type,
                source,
                source_url,
                content_hash,
                text,
                ingested_at,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        db.commit()
    _log("raw_document_created", document_id, {"source_type": source_type, "source": source})
    return {"document_id": document_id, "deduplicated": False}


def list_raw_documents(source_type=None, limit=50):
    """List raw documents without returning the full raw text."""
    db = _get_db()
    if source_type:
        rows = db.execute(
            """SELECT document_id, source_type, source, source_url, content_hash, ingested_at
               FROM raw_documents WHERE source_type = ? ORDER BY ingested_at DESC LIMIT ?""",
            (source_type, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT document_id, source_type, source, source_url, content_hash, ingested_at
               FROM raw_documents ORDER BY ingested_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_job_post(document_id, job_role, fields, source_type="unknown", source_url=""):
    """Store normalized job fields extracted from a raw document."""
    db = _get_db()
    existing = db.execute("SELECT job_post_id FROM job_posts WHERE document_id = ?", (document_id,)).fetchone()
    if existing:
        return {"job_post_id": existing[0], "deduplicated": True}

    job_post_id = _next_job_post_id()
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _lock:
        db.execute(
            """INSERT INTO job_posts
               (job_post_id, document_id, job_role, raw_title, normalized_title, company,
                responsibilities, skills, requirements, source_type, source_url, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_post_id,
                document_id,
                job_role,
                fields.get("title", ""),
                fields.get("normalized_title", ""),
                fields.get("company", ""),
                json.dumps(fields.get("responsibilities", []), ensure_ascii=False),
                json.dumps(fields.get("skills", []), ensure_ascii=False),
                json.dumps(fields.get("requirements", []), ensure_ascii=False),
                source_type,
                source_url,
                created_at,
            ),
        )
        db.commit()
    _log("job_post_created", job_post_id, {"document_id": document_id, "job_role": job_role})
    return {"job_post_id": job_post_id, "deduplicated": False}


def list_job_posts(job_role=None, limit=50):
    """List normalized job posts."""
    db = _get_db()
    params = []
    query = ["SELECT * FROM job_posts WHERE 1=1"]
    if job_role:
        query.append("AND job_role = ?")
        params.append(job_role)
    query.append("ORDER BY created_at DESC LIMIT ?")
    params.append(limit)
    rows = db.execute(" ".join(query), params).fetchall()
    posts = []
    for row in rows:
        item = dict(row)
        for key in ("responsibilities", "skills", "requirements"):
            item[key] = json.loads(item.get(key) or "[]")
        posts.append(item)
    return posts


# ── Evidence Events ──────────────────────────────────────────────

def add_event(job_role, ability_id, evidence_text, source_type="unknown",
              source_url="", extraction_method="rule_lexicon_v1",
              confidence=0.5, metadata=None):
    """Add an evidence event with dedup"""
    db = _get_db()
    existing = db.execute(
        """SELECT event_id FROM evidence_events
           WHERE job_role = ? AND ability_id = ? AND source_url = ? AND evidence_text = ?
           LIMIT 1""",
        (job_role, ability_id, source_url, evidence_text)
    ).fetchone()
    if existing:
        return {"event_id": existing[0], "deduplicated": True}

    event_id = _next_event_id()
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _lock:
        db.execute(
            """INSERT INTO evidence_events
               (event_id, job_role, ability_id, evidence_text, source_url,
                source_type, extraction_method, confidence, extracted_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, job_role, ability_id, evidence_text, source_url,
             source_type, extraction_method, round(confidence, 2),
             extracted_at, json.dumps(metadata or {}, ensure_ascii=False))
        )
        db.commit()
    _log("event_created", event_id, {"job_role": job_role, "ability_id": ability_id})
    return {"event_id": event_id, "deduplicated": False}


def query_events(ability_id=None, source_type=None, job_role=None,
                 days_back=None, limit=50):
    """Query evidence events with filters"""
    db = _get_db()
    parts = ["SELECT * FROM evidence_events WHERE 1=1"]
    params = []
    if ability_id:
        parts.append("AND ability_id = ?"); params.append(ability_id)
    if source_type:
        parts.append("AND source_type = ?"); params.append(source_type)
    if job_role:
        parts.append("AND job_role = ?"); params.append(job_role)
    if days_back is not None:
        parts.append("AND extracted_at >= datetime('now', ? || ' days')")
        params.append(f"-{days_back}")
    parts.append("ORDER BY extracted_at DESC LIMIT ?")
    params.append(limit)
    rows = db.execute(" ".join(parts), params).fetchall()
    return [dict(r) for r in rows]


def ability_evidence_summary(ability_id, job_role=None):
    """Aggregate evidence stats for a single ability node"""
    db = _get_db()
    params = [ability_id]
    role_filter = "AND job_role = ?" if job_role else ""
    if job_role: params.append(job_role)
    row = db.execute(
        f"SELECT COUNT(*), AVG(confidence), MAX(extracted_at) "
        f"FROM evidence_events WHERE ability_id = ? {role_filter}",
        params
    ).fetchone()
    count = row[0] if row and row[0] else 0
    avg_conf = round(row[1], 2) if row and row[1] else 0.0
    last_upd = row[2] if row and row[2] else ""

    # Source type distribution
    src_rows = db.execute(
        f"SELECT source_type, COUNT(*) as cnt FROM evidence_events "
        f"WHERE ability_id = ? {role_filter} GROUP BY source_type ORDER BY cnt DESC",
        params
    ).fetchall()
    sources = {r[0]: r[1] for r in src_rows} if src_rows else {}

    # Latest events
    latest_rows = db.execute(
        f"SELECT event_id, source_type, evidence_text, extracted_at, confidence "
        f"FROM evidence_events WHERE ability_id = ? {role_filter} "
        f"ORDER BY extracted_at DESC LIMIT 3",
        params
    ).fetchall()
    latest_events = []
    for r in latest_rows:
        latest_events.append({
            "event_id": r[0], "source_type": r[1],
            "evidence_snippet": (r[2] or "")[:80],
            "extracted_at": r[3], "confidence": round(r[4], 2) if r[4] else 0
        })

    return {
        "evidence_count": count,
        "avg_confidence": avg_conf,
        "last_updated_at": last_upd,
        "source_type_distribution": sources,
        "latest_evidence": latest_events
    }


# ── Proposals ────────────────────────────────────────────────────

def add_proposal(job_role, ability_id, action="strengthen",
                 suggested_weight_delta=0.1, evidence="", source="",
                 proposal_score=0.5):
    """Create a pending proposal"""
    db = _get_db()
    pid = _next_proposal_id()
    with _lock:
        db.execute(
            """INSERT INTO proposals
               (proposal_id, job_role, ability_id, action,
                suggested_weight_delta, evidence, source,
                proposal_score, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (pid, job_role, ability_id, action,
             round(suggested_weight_delta, 2), evidence, source,
             round(proposal_score, 2))
        )
        db.commit()
    _log("proposal_created", pid, {"ability_id": ability_id, "score": proposal_score})
    return {"proposal_id": pid, "status": "pending"}


def get_pending_proposals(job_role=None):
    """Get all pending proposals"""
    db = _get_db()
    if job_role:
        rows = db.execute(
            "SELECT * FROM proposals WHERE status='pending' AND job_role=? ORDER BY proposal_score DESC",
            (job_role,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM proposals WHERE status='pending' ORDER BY proposal_score DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def confirm_proposal(proposal_id, confirmed_by="teacher"):
    """Confirm a proposal and return its data"""
    db = _get_db()
    row = db.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
    if not row:
        return {"error": "proposal not found"}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _lock:
        db.execute(
            "UPDATE proposals SET status='confirmed', confirmed_by=?, confirmed_at=? WHERE proposal_id=?",
            (confirmed_by, now, proposal_id)
        )
        db.commit()
    _log("proposal_confirmed", proposal_id, {"confirmed_by": confirmed_by})
    updated = db.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
    return dict(updated)


def reject_proposal(proposal_id):
    """Reject a proposal"""
    db = _get_db()
    row = db.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
    if not row:
        return {"error": "proposal not found"}
    with _lock:
        db.execute("UPDATE proposals SET status='rejected' WHERE proposal_id=?", (proposal_id,))
        db.commit()
    _log("proposal_rejected", proposal_id, {})
    updated = db.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
    return dict(updated)


def get_proposal_history(ability_id, limit=20):
    """Get proposal history for an ability"""
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM proposals WHERE ability_id=? ORDER BY created_at DESC LIMIT ?",
        (ability_id, limit)
    ).fetchall()
    return [dict(r) for r in rows]


# ── Snapshots ─────────────────────────────────────────────────────

def create_snapshot(job_role, nodes, dimension_scores=None, version_label=None):
    """Create a version snapshot"""
    db = _get_db()
    version = version_label or datetime.now(timezone.utc).strftime("v%Y%m%d.%H%M%S")
    snapshot_id = f"SNAP-{version}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    node_data = json.dumps(nodes, ensure_ascii=False)
    dims = json.dumps(dimension_scores or {}, ensure_ascii=False)
    with _lock:
        # Check if version exists
        existing = db.execute("SELECT snapshot_id FROM snapshots WHERE version=?", (version,)).fetchone()
        if existing:
            return {"snapshot_id": existing[0], "version": version, "duplicated": True}
        db.execute(
            """INSERT INTO snapshots
               (snapshot_id, job_role, version, created_at, node_count,
                node_data, dimension_scores, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'evidence_derived')""",
            (snapshot_id, job_role, version, now, len(nodes), node_data, dims)
        )
        db.commit()
    _log("snapshot_created", snapshot_id, {"version": version, "node_count": len(nodes)})
    return {"snapshot_id": snapshot_id, "version": version}


def list_versions(job_role=None):
    """List all version snapshots"""
    db = _get_db()
    if job_role:
        rows = db.execute(
            "SELECT * FROM snapshots WHERE job_role=? ORDER BY created_at DESC, version DESC",
            (job_role,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM snapshots ORDER BY created_at DESC, version DESC").fetchall()
    return [{"version": r["version"], "job_role": r["job_role"],
             "created_at": r["created_at"], "node_count": r["node_count"],
             "source": r["source"], "parent_version": r["parent_version"]}
            for r in rows]


def get_snapshot(version):
    """Get a specific snapshot by version string"""
    db = _get_db()
    row = db.execute("SELECT * FROM snapshots WHERE version=?", (version,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["nodes"] = json.loads(row["node_data"])
    result["dimension_scores"] = json.loads(row["dimension_scores"] or "{}")
    return result


def get_version_diff(v1, v2):
    """Compare two snapshots and return differences"""
    s1 = get_snapshot(v1)
    s2 = get_snapshot(v2)
    if not s1 or not s2:
        return {"error": "version not found", "v1_found": s1 is not None, "v2_found": s2 is not None}

    n1 = {n["id"]: n for n in s1.get("nodes", [])}
    n2 = {n["id"]: n for n in s2.get("nodes", [])}
    added = [n for nid, n in n2.items() if nid not in n1]
    removed = [n for nid, n in n1.items() if nid not in n2]
    changed = []
    for nid, n2node in n2.items():
        if nid in n1:
            n1node = n1[nid]
            diffs = {}
            for key in ("demand_weight", "weight", "confidence", "status"):
                if n1node.get(key) != n2node.get(key):
                    diffs[key] = {"from": n1node.get(key), "to": n2node.get(key)}
            if diffs:
                changed.append({"id": nid, "name": n2node.get("name", nid), "changes": diffs})

    return {
        "v1": v1, "v2": v2,
        "v1_created": s1.get("created_at"), "v2_created": s2.get("created_at"),
        "added": added, "removed": removed, "changed": changed,
        "has_changes": bool(added or removed or changed)
    }


def rollback_to_version(target_version, job_role=None):
    """Rollback by creating a new snapshot with the same data"""
    snap = get_snapshot(target_version)
    if not snap:
        return {"error": f"version {target_version} not found"}
    new_ver = target_version + "-restored"
    result = create_snapshot(
        job_role=snap["job_role"],
        nodes=snap["nodes"],
        dimension_scores=snap.get("dimension_scores", {}),
        version_label=new_ver
    )
    # Record parent
    db = _get_db()
    db.execute("UPDATE snapshots SET parent_version=? WHERE version=?", (target_version, new_ver))
    db.commit()
    _log("rollback", new_ver, {"rolled_back_from": target_version})
    return {"version": new_ver, "restored_from": target_version, "rolled_back_to": target_version}


# ── Audit ─────────────────────────────────────────────────────────

def _log(action, entity_id="", detail=None):
    """Internal audit logging"""
    try:
        db = _get_db()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.execute(
            "INSERT INTO audit_log (timestamp, action, entity_id, detail) VALUES (?, ?, ?, ?)",
            (now, action, entity_id, json.dumps(detail or {}, ensure_ascii=False))
        )
        db.commit()
    except Exception:
        pass  # Audit should never crash


def query_log(action=None, limit=100):
    """Query audit log"""
    db = _get_db()
    if action:
        rows = db.execute(
            "SELECT * FROM audit_log WHERE action=? ORDER BY id DESC LIMIT ?",
            (action, limit)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Scoring ───────────────────────────────────────────────────────

def compute_proposal_score(source_type, confidence, evidence_count=1,
                           days_since_update=30, role_relevance=1.0):
    """Compute proposal score based on evidence quality.
    score = source_weight * confidence * frequency_factor * recency * relevance
    """
    source_weights = {
        "enterprise_official": 0.85,
        "teacher_material": 0.95,
        "standard": 0.90,
        "government_standard": 0.90,
        "education_standard": 0.80,
        "job_platform": 0.65,
        "local_file": 0.70,
        "industry_report": 0.60,
        "social_media": 0.25,
        "unknown": 0.40,
    }
    sw = source_weights.get(source_type, 0.40)
    freq = min(1.0, evidence_count / 20) * 0.3 + 0.7  # 0.7-1.0 based on count
    recency = max(0.3, 1.0 - days_since_update / 365)
    score = sw * confidence * freq * recency * role_relevance
    return round(score, 2)


def proposal_threshold(score):
    """Categorize proposal score into action levels"""
    if score >= 0.75:
        return "auto_approve"
    elif score >= 0.45:
        return "pending"
    else:
        return "weak_signal"


def migrate_from_json():
    """Migrate existing JSON evidence files to SQLite"""
    events_dir = ROOT / "data" / "evidence" / "events"
    if events_dir.exists():
        for f in sorted(events_dir.glob("*.json")):
            try:
                ev = json.loads(f.read_text(encoding="utf-8"))
                add_event(
                    job_role=ev.get("job_role", "unknown"),
                    ability_id=ev.get("ability_id", "unknown"),
                    evidence_text=ev.get("evidence", ""),
                    source_type=ev.get("source_type", "unknown"),
                    source_url=ev.get("source_url", ""),
                    extraction_method=ev.get("extraction_method", "rule_lexicon_v1"),
                    confidence=ev.get("confidence", 0.5),
                    metadata=ev.get("metadata")
                )
            except Exception as e:
                print(f"  Skipped {f.name}: {e}")
    return {"migrated": True}
