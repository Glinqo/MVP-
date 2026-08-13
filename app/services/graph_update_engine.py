import json
import re
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .data_loader import ROOT, load_data
from .feedback import append_session_event, load_session_record, safe_session_id


GRAPH_EVENTS_PATH = ROOT / "data" / "graph_update_events.json"
JOB_PROPOSALS_PATH = ROOT / "data" / "job_graph_update_proposals.json"
JOB_CONFIRMED_PATH = ROOT / "data" / "job_graph_confirmed_snapshots.json"

IMPROVING_EVENTS = {"question_explained", "practice_completed", "learning_plan_started", "learning_plan_checkpoint", "scenario_step_completed", "scenario_completed"}
WEAK_EVENTS = {"scenario_step_mistake"}
MASTERED_EVENTS = {"task_completed"}
SAFETY_REVIEW_ABILITIES = {"es_safety_rules", "es_power_isolation", "es_instrument_use"}

# Legacy ability ids/names used by assessment questions, diagnosis rules and
# job-specific question sets map to the current ability_nodes.json ids.
LEGACY_ABILITY_ALIASES = {
    # Initial assessment question ability_ids
    "plc_basic_principle": "pl_program_monitor",
    "sensor_selection": "sn_type_identify",
    "input_common_terminal": "pl_io_mapping",
    "electrical_safety": "es_safety_rules",
    "troubleshoot_order": "tr_fault_classify",
    "safety_ppe": "es_safety_rules",
    "sensor_wiring": "sn_wiring_rules",
    "plc_wiring": "pl_io_mapping",
    "motor_control": "pl_logic_control",
    "hmi_basic": "pl_device_integration",
    "emergency_stop": "es_safety_rules",
    "vfd_basic": "pl_device_integration",
    # Legacy diagnosis/scoring rule ability keys
    "electrical_safety_check": "es_safety_rules",
    "power_isolation_confirmation": "es_power_isolation",
    "dc24v_power_check": "es_low_voltage",
    "multimeter_voltage_measurement": "es_instrument_use",
    "sensor_type_identification": "sn_type_identify",
    "sensor_nameplate_reading": "sn_type_identify",
    "sensor_output_logic": "sn_signal_acq",
    "sensor_led_observation": "sn_signal_acq",
    "sensor_wiring_color_code": "sn_wiring_rules",
    "sensor_wiring_judgement": "sn_wiring_rules",
    "plc_input_common_terminal": "pl_io_mapping",
    "plc_input_grouping": "pl_io_mapping",
    "plc_io_address_mapping": "pl_io_mapping",
    "io_mapping_table_build": "pl_io_mapping",
    "program_variable_lookup": "pl_program_monitor",
    "plc_input_monitoring": "pl_program_monitor",
    "input_led_compare": "pl_program_monitor",
    "input_no_response_fault_scope": "tr_fault_classify",
    "no_response_power_path_check": "tr_signal_chain",
    "no_response_sensor_side_check": "sn_fault_diag",
    "no_response_common_terminal_check": "pl_io_mapping",
    "no_response_address_mapping_check": "pl_io_mapping",
    "diagnosis_record_feedback": "tr_record_feedback",
    "personalized_training_task_recommendation": "rt_training_recommend",
    "role_task_understanding": "rt_task_understanding",
    # Old scoring_rules.json ability_catalog ids
    "A01": "es_safety_rules",
    "A02": "sn_type_identify",
    "A03": "pl_io_mapping",
    "A04": "pl_io_mapping",
    "A05": "pl_program_monitor",
    "A06": "pl_program_monitor",
    "A07": "tr_fault_classify",
    "A08": "sn_wiring_rules",
    "A09": "sn_signal_acq",
    "A10": "pl_io_mapping",
    "A11": "pl_program_monitor",
    "A12": "sn_fault_diag",
    "A13": "tr_record_feedback",
    "A14": "rt_training_recommend",
    "A15": "pl_io_mapping",
    # plc_electrical_control_technician question set
    "pc_01": "es_low_voltage",
    "pc_02": "es_low_voltage",
    "pc_03": "es_low_voltage",
    "pc_04": "es_low_voltage",
    "pc_05": "es_safety_rules",
    "pc_06": "pl_device_integration",
    "pc_07": "pl_program_monitor",
    "pc_08": "pl_program_monitor",
    "pc_09": "pl_program_monitor",
    "pc_10": "pl_program_monitor",
    "pc_11": "pl_io_mapping",
    "pc_12": "pl_io_mapping",
    "pc_13": "pl_io_mapping",
    "pc_14": "pl_program_monitor",
    "pc_15": "pl_program_monitor",
    "pc_16": "pl_logic_control",
    "pc_17": "pl_logic_control",
    "pc_18": "pl_logic_control",
    "pc_19": "pl_logic_control",
    "pc_20": "pl_logic_control",
}

# ── 掌握度证据模型 ─────────────────────────────────────────────
# 证据类型权重 w_i（学生能力证据的可靠性权重）
EVIDENCE_WEIGHTS = {
    "diagnostic_test": 0.4,     # 诊断自测
    "training_feedback": 0.3,   # 实训任务反馈
    "judgment_qa": 0.2,         # 判断问答
    "explanation_retell": 0.1,  # 讲题复述
}

# 时间衰减系数 λ = 0.98^d（d 为距今天数）
TIME_DECAY_LAMBDA = 0.98

# 置信度阈值：低于该值的节点视为证据不足，需推送验证题
CONFIDENCE_THRESHOLD = 0.5

# ── global lock for runtime JSON files ─────────────────────────────
_global_runtime_lock = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def float_or_zero(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_runtime_json(path, default):
    with _global_runtime_lock:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default


def write_runtime_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with _global_runtime_lock:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def normalize_ability_id(ability_id):
    if not ability_id:
        return None
    data = load_data()
    raw = str(ability_id)
    if raw in data["ability_by_id"]:
        return raw
    if raw in LEGACY_ABILITY_ALIASES:
        return LEGACY_ABILITY_ALIASES[raw]

    catalog = data["rules_data"].get("ability_catalog", {})
    for internal_id, item in catalog.items():
        if raw in {str(item.get("ability_id")), str(item.get("ability_name"))}:
            return internal_id

    for internal_id, ability in data["ability_by_id"].items():
        if raw == str(ability.get("name")):
            return internal_id
    return raw


def extract_ability_ids(items):
    ability_ids = []
    for item in items or []:
        if isinstance(item, str):
            ability_id = normalize_ability_id(item)
        elif isinstance(item, dict):
            ability_id = None
            for key in ("ability_internal_id", "ability_node_id", "id", "ability_id", "node_id"):
                if item.get(key):
                    ability_id = normalize_ability_id(item.get(key))
                    break
        else:
            ability_id = None

        if ability_id and ability_id not in ability_ids:
            ability_ids.append(ability_id)
    return ability_ids


def ability_ids_from_names(names):
    data = load_data()
    matched = []
    for name in names or []:
        ability_id = normalize_ability_id(name)
        if ability_id in data["ability_by_id"] and ability_id not in matched:
            matched.append(ability_id)
    return matched


def event_ability_ids(event):
    ability_ids = []
    for key in ("ability_ids", "abilities", "weak_abilities", "highlighted_abilities", "related_abilities"):
        ability_ids.extend(extract_ability_ids(event.get(key, [])))
    for key in ("ability_id", "ability_node_id", "node_id"):
        if event.get(key):
            ability_ids.extend(extract_ability_ids([event.get(key)]))
    ordered = []
    for ability_id in ability_ids:
        if ability_id in load_data()["ability_by_id"] and ability_id not in ordered:
            ordered.append(ability_id)
    if event.get("event_type") in {"score", "diagnosis"}:
        for ability_id in _score_event_ability_scores(event):
            if ability_id not in ordered:
                ordered.append(ability_id)
    return ordered


def append_global_graph_event(session_id, event):
    data = read_runtime_json(GRAPH_EVENTS_PATH, {"version": "0.1.0", "source": "project_runtime", "events": []})
    event = dict(event or {})
    event["session_id"] = safe_session_id(session_id)
    event.setdefault("created_at", now_iso())
    event.setdefault("event_id", event["created_at"].replace(":", "").replace("-", "").replace(".", ""))
    data.setdefault("events", []).append(event)
    write_runtime_json(GRAPH_EVENTS_PATH, data)


def record_student_graph_event(payload):
    payload = payload or {}
    session_id = safe_session_id(payload.get("session_id"))
    ability_ids = event_ability_ids(payload)
    event = {
        "event_type": payload.get("event_type", "learning_event"),
        "ability_ids": ability_ids,
        "highlighted_abilities": [{"id": ability_id, "name": load_data()["ability_by_id"][ability_id].get("name", ability_id)} for ability_id in ability_ids],
        "question_id": payload.get("question_id"),
        "knowledge_id": payload.get("knowledge_id"),
        "task_id": payload.get("task_id"),
        "outcome": payload.get("outcome"),
        "note": payload.get("note", ""),
        "source": payload.get("source", "student_action"),
    }
    saved = append_session_event(session_id, event)
    append_global_graph_event(session_id, {**event, "created_at": now_iso()})
    return saved


def ability_event_bucket():
    return {
        "chat": 0,
        "weak": 0,
        "improving": 0,
        "mastered": 0,
        "recommended": 0,
        "last_updated_at": None,
        "reasons": [],
        "events": [],
    }


def _days_since(created_at):
    """返回证据距今天数，用于时间衰减 λ^d。"""
    if not created_at:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(created_at))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0.0, delta.total_seconds() / 86400.0)
    except (ValueError, TypeError, AttributeError):
        return 0.0


def _score_event_ability_scores(event):
    """Return {current_ability_id: score_0_100} for a score/diagnosis event."""
    ability_scores = event.get("score_result", {}).get("ability_scores", {})
    if not ability_scores:
        ability_scores = event.get("ability_scores", {})
    if not isinstance(ability_scores, dict):
        return {}

    data = load_data()
    result = {}
    for legacy_id, score in ability_scores.items():
        ability_id = normalize_ability_id(legacy_id)
        if ability_id and ability_id in data["ability_by_id"]:
            result[ability_id] = float_or_zero(score)
    return result


def _evidence_type_and_score(event, ability_id):
    """把原始事件映射为 (evidence_type, score)，不能贡献时返回 (None, None)。

    得分 s_i 统一采用 0-100 标尺。
    """
    event_type = event.get("event_type", "")

    # 判断问答：学生围绕该能力提出或回答判断性问题
    if event_type == "chat_message":
        return "judgment_qa", 60.0

    # 讲题复述：学生查看并尝试复述讲解
    if event_type == "question_explained":
        return "explanation_retell", 70.0

    # 诊断自测
    if event_type in {"score", "diagnosis"}:
        ability_scores = _score_event_ability_scores(event)
        if ability_scores and ability_id in ability_scores:
            return "diagnostic_test", ability_scores[ability_id]
        weak_ids = set(extract_ability_ids(event.get("weak_abilities", [])))
        if ability_id in weak_ids:
            return "diagnostic_test", 0.0
        return None, None

    if event_type == "initial_quiz_answered":
        return "diagnostic_test", 100.0 if event.get("is_correct") else 0.0

    if event_type == "initial_assessment_completed":
        ability_scores = event.get("ability_scores", {})
        if isinstance(ability_scores, dict):
            for legacy_id, raw_score in ability_scores.items():
                if normalize_ability_id(legacy_id) == ability_id:
                    return "diagnostic_test", round(float_or_zero(raw_score) * 100.0, 1)
        return "diagnostic_test", 0.0

    # 实训任务反馈
    if event_type == "feedback":
        return "training_feedback", 100.0 if event.get("feedback") == "已掌握" else 0.0

    if event_type == "task_completed":
        outcome = event.get("outcome")
        return "training_feedback", 100.0 if outcome in {None, "", "passed", "completed"} else 50.0

    if event_type in {"practice_completed", "scenario_completed", "scenario_step_completed", "learning_plan_checkpoint"}:
        return "training_feedback", 80.0

    if event_type == "learning_plan_started":
        return "training_feedback", 50.0

    if event_type == "scenario_step_mistake":
        return "training_feedback", 0.0

    return None, None


def add_bucket_event(bucket, event, reason, ability_id=None):
    bucket["last_updated_at"] = event.get("created_at") or bucket["last_updated_at"]
    bucket["reasons"].append(reason)
    evidence_type, score = _evidence_type_and_score(event, ability_id)
    weight = EVIDENCE_WEIGHTS.get(evidence_type, 0.0) if evidence_type else 0.0
    bucket["events"].append(
        {
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "created_at": event.get("created_at"),
            "reason": reason,
            "source": event.get("source"),
            "question_id": event.get("question_id"),
            "knowledge_id": event.get("knowledge_id"),
            "task_id": event.get("task_id"),
            "note": event.get("note", ""),
            "evidence_type": evidence_type,
            "score": score,
            "weight": weight,
        }
    )


def personal_graph_state(session_id, core_chain):
    """Return the personal ability graph for a session.

    Uses incremental cache (session_store.ability_state_cache) when available;
    falls back to full event-scan on cache miss or for sessions with complex
    events (feedback / score) that mutate multiple counters at once.
    """
    # Try cache-first path
    try:
        from .session_store import load_ability_cache

        record = load_session_record(session_id)
        complex_types = {
            "score",
            "diagnosis",
            "feedback",
            "initial_quiz_answered",
            "initial_assessment_completed",
        }
        has_complex_events = any(
            event.get("event_type") in complex_types for event in record.get("events", [])
        )
        cached = load_ability_cache(safe_session_id(session_id))
        if cached and not has_complex_events:
            buckets, recommended_names = _buckets_from_cache_and_events(
                session_id, core_chain, cached
            )
        else:
            buckets, recommended_names = _full_event_scan(session_id, core_chain)
            # Persist cache for next time
            _save_buckets_to_cache(session_id, buckets)
    except Exception:
        buckets, recommended_names = _full_event_scan(session_id, core_chain)

    # ── post-processing: recommended_ids (same as original) ──────────
    record = load_session_record(session_id)
    recommended_names.extend(record.get("recommended_path", []))
    recommended_ids = _compute_recommended_ids(buckets, recommended_names, core_chain)

    for ability_id in recommended_ids:
        if ability_id in load_data()["ability_by_id"]:
            buckets[ability_id]["recommended"] += 1
            if not buckets[ability_id]["reasons"]:
                buckets[ability_id]["reasons"].append("推荐下一步训练")

    return {"record": record, "buckets": buckets, "recommended_ids": recommended_ids}


def _buckets_from_cache_and_events(session_id, core_chain, cached):
    """Build buckets from cached counters + iterate events for reason details only."""
    from collections import defaultdict

    buckets = defaultdict(ability_event_bucket)
    recommended_names = []
    record = load_session_record(session_id)

    # Fill counters from cache
    for ability_id, counters in cached.items():
        b = buckets[ability_id]
        b["chat"] = counters.get("chat_count", 0)
        b["weak"] = counters.get("weak_count", 0)
        b["improving"] = counters.get("improving_count", 0)
        b["mastered"] = counters.get("mastered_count", 0)
        b["recommended"] = counters.get("recommended_count", 0)
        b["last_updated_at"] = counters.get("last_updated_at")

    # Still iterate events for reason details and complex events that
    # might modify counters beyond simple increment
    for event in record.get("events", []):
        event_type = event.get("event_type")

        if event_type == "chat_message":
            recommended_names.extend(event.get("recommended_path", []))
            ability_ids = event_ability_ids(event) or extract_ability_ids(event.get("highlighted_abilities", []))
            for ability_id in ability_ids:
                add_bucket_event(buckets[ability_id], event, "问答命中该能力", ability_id)
            continue

        if event_type in {"score", "diagnosis"}:
            for ability_id in event_ability_ids(event):
                add_bucket_event(buckets[ability_id], event, "确定性评分更新", ability_id)
            recommended_names.extend(event.get("recommended_path", []))
            continue

        if event_type == "feedback":
            add_reason = (
                "学生反馈已掌握"
                if event.get("feedback") == "已掌握"
                else f"学生反馈{event.get('feedback', '')}"
            )
            ability_ids = event_ability_ids(event)
            for ability_id in ability_ids:
                add_bucket_event(buckets[ability_id], event, add_reason, ability_id)
            recommended_names.extend(event.get("recommended_path", []))
            continue

        if event_type in IMPROVING_EVENTS:
            for ability_id in event_ability_ids(event):
                add_bucket_event(buckets[ability_id], event, "讲题/练习产生改进证据", ability_id)
            continue

        if event_type in WEAK_EVENTS:
            for ability_id in event_ability_ids(event):
                add_bucket_event(buckets[ability_id], event, "排故角色扮演选择错误，提示该能力需补强", ability_id)
            continue

        if event_type in MASTERED_EVENTS:
            msg = (
                "任务完成产生掌握证据"
                if event.get("outcome") in {None, "", "passed", "completed"}
                else "任务完成但仍需复核"
            )
            for ability_id in event_ability_ids(event):
                add_bucket_event(buckets[ability_id], event, msg, ability_id)

    # Handle record-level weak_abilities and feedback (post-processing)
    for ability_id in extract_ability_ids(record.get("weak_abilities", [])):
        if ability_id not in buckets:
            buckets[ability_id] = ability_event_bucket()
    if record.get("feedback") == "已掌握":
        for ability_id in extract_ability_ids(record.get("weak_abilities", [])):
            pass  # already handled via cached counters
    elif record.get("feedback") in {"仍不会", "需要更基础讲解"}:
        for ability_id in extract_ability_ids(record.get("weak_abilities", [])):
            pass

    return buckets, recommended_names


def _full_event_scan(session_id, core_chain):
    """Original full-scan logic, extracted for reuse."""
    record = load_session_record(session_id)
    buckets = defaultdict(ability_event_bucket)
    recommended_names = []

    for event in record.get("events", []):
        event_type = event.get("event_type")
        ability_ids = event_ability_ids(event)

        if event_type == "chat_message":
            ability_ids = ability_ids or extract_ability_ids(event.get("highlighted_abilities", []))
            for ability_id in ability_ids:
                buckets[ability_id]["chat"] += 1
                add_bucket_event(buckets[ability_id], event, "问答命中该能力", ability_id)
            recommended_names.extend(event.get("recommended_path", []))
            continue

        if event_type in {"score", "diagnosis"}:
            score_map = _score_event_ability_scores(event)
            for ability_id, score in score_map.items():
                if score <= 0:
                    buckets[ability_id]["weak"] += 1
                elif score < 75:
                    buckets[ability_id]["improving"] += 1
                else:
                    buckets[ability_id]["mastered"] += 1
                add_bucket_event(buckets[ability_id], event, "确定性评分更新", ability_id)
            recommended_names.extend(event.get("recommended_path", []))
            continue

        if event_type == "initial_quiz_answered":
            related_ids = event_ability_ids(event) or extract_ability_ids([event.get("ability_id")])
            for ability_id in related_ids:
                if event.get("is_correct"):
                    buckets[ability_id]["improving"] += 1
                else:
                    buckets[ability_id]["weak"] += 1
                add_bucket_event(buckets[ability_id], event, "初始能力测评答题", ability_id)
            continue

        if event_type == "initial_assessment_completed":
            score_map = _score_event_ability_scores(event)
            for ability_id, score in score_map.items():
                if score <= 0:
                    buckets[ability_id]["weak"] += 1
                elif score < 75:
                    buckets[ability_id]["improving"] += 1
                else:
                    buckets[ability_id]["mastered"] += 1
                add_bucket_event(buckets[ability_id], event, "初始能力测评完成", ability_id)
            continue

        if event_type == "feedback":
            related_ids = extract_ability_ids(event.get("weak_abilities", [])) or extract_ability_ids(event.get("highlighted_abilities", []))
            feedback = event.get("feedback")
            for ability_id in related_ids:
                if feedback == "已掌握":
                    buckets[ability_id]["mastered"] += 1
                    buckets[ability_id]["weak"] = 0
                    add_bucket_event(buckets[ability_id], event, "学生反馈已掌握", ability_id)
                elif feedback in {"仍不会", "需要更基础讲解"}:
                    buckets[ability_id]["weak"] += 1
                    add_bucket_event(buckets[ability_id], event, f"学生反馈{feedback}", ability_id)
            recommended_names.extend(event.get("recommended_path", []))
            continue

        if event_type in IMPROVING_EVENTS:
            for ability_id in ability_ids:
                buckets[ability_id]["improving"] += 1
                add_bucket_event(buckets[ability_id], event, "讲题/练习产生改进证据", ability_id)
            continue

        if event_type in WEAK_EVENTS:
            for ability_id in ability_ids:
                buckets[ability_id]["weak"] += 1
                add_bucket_event(buckets[ability_id], event, "排故角色扮演选择错误，提示该能力需补强", ability_id)
            continue

        if event_type in MASTERED_EVENTS:
            for ability_id in ability_ids:
                if event.get("outcome") in {None, "", "passed", "completed"}:
                    buckets[ability_id]["mastered"] += 1
                    add_bucket_event(buckets[ability_id], event, "任务完成产生掌握证据", ability_id)
                else:
                    buckets[ability_id]["improving"] += 1
                    add_bucket_event(buckets[ability_id], event, "任务完成但仍需复核", ability_id)

    for ability_id in extract_ability_ids(record.get("weak_abilities", [])):
        buckets[ability_id]["weak"] += 1
    if record.get("feedback") == "已掌握":
        for ability_id in extract_ability_ids(record.get("weak_abilities", [])):
            buckets[ability_id]["mastered"] += 1
            buckets[ability_id]["weak"] = 0
    elif record.get("feedback") in {"仍不会", "需要更基础讲解"}:
        for ability_id in extract_ability_ids(record.get("weak_abilities", [])):
            buckets[ability_id]["weak"] += 1
    recommended_names.extend(record.get("recommended_path", []))

    return buckets, recommended_names


def _compute_recommended_ids(buckets, recommended_names, core_chain):
    """Compute which ability IDs should be marked as recommended_next."""
    recommended_ids = set(ability_ids_from_names(recommended_names))
    if any(bucket["weak"] for bucket in buckets.values()):
        for ability_id, bucket in list(buckets.items()):
            if not bucket["weak"]:
                continue
            ability = load_data()["ability_by_id"].get(ability_id, {})
            for prerequisite in ability.get("prerequisites", []):
                recommended_ids.add(prerequisite)
    elif any(bucket["chat"] for bucket in buckets.values()):
        touched_chain = [item for item in core_chain if buckets[item]["chat"]]
        if touched_chain:
            last_index = max(core_chain.index(item) for item in touched_chain)
            if last_index + 1 < len(core_chain):
                recommended_ids.add(core_chain[last_index + 1])
    return recommended_ids


def _save_buckets_to_cache(session_id, buckets):
    """Persist computed bucket counters to SQLite cache."""
    try:
        from .session_store import rebuild_ability_cache

        rebuild_ability_cache(session_id, {
            aid: {
                "chat": b["chat"],
                "weak": b["weak"],
                "improving": b["improving"],
                "mastered": b["mastered"],
                "recommended": b["recommended"],
                "last_event_id": (b.get("events") or [{}])[-1].get("event_id", "") if b.get("events") else "",
                "last_updated_at": b.get("last_updated_at", ""),
            }
            for aid, b in buckets.items()
        })
    except Exception:
        pass  # cache write failure is non-critical


def rebuild_cache(session_id):
    """Force a full recompute and cache write for a session."""
    from .data_loader import primary_job_profile

    profile = primary_job_profile()
    core_chain = [
        item.get("ability_internal_id", item.get("id", ""))
        for item in profile.get("core_ability_chain", [])
    ]
    buckets, _ = _full_event_scan(session_id, core_chain)
    _save_buckets_to_cache(session_id, buckets)
    return {"rebuilt": True, "session_id": safe_session_id(session_id), "ability_count": len(buckets)}


def compute_node_metrics(ability_id, bucket):
    # 加权时间衰减证据模型：
    # M(c) = Σ(w_i · s_i · λ^Δt_i) / Σ(w_i · λ^Δt_i)
    # conf(c) = 1 - 1 / (1 + Σ w_i)
    weighted_score_sum = 0.0
    weighted_decay_sum = 0.0
    weight_sum = 0.0
    evidence_count = 0

    for ev in bucket.get("events", []):
        weight = float_or_zero(ev.get("weight"))
        evidence_type = ev.get("evidence_type")
        if not evidence_type or weight <= 0:
            continue
        score = float_or_zero(ev.get("score"))
        days = _days_since(ev.get("created_at"))
        decay = TIME_DECAY_LAMBDA ** days
        weighted_score_sum += weight * score * decay
        weighted_decay_sum += weight * decay
        weight_sum += weight
        evidence_count += 1

    if weighted_decay_sum > 0:
        mastery = weighted_score_sum / weighted_decay_sum
    else:
        mastery = 0.0

    mastery = max(0.0, min(100.0, mastery))
    confidence = round(1.0 - 1.0 / (1.0 + weight_sum), 4) if weight_sum > 0 else 0.0
    confidence = min(0.99, confidence)

    if ability_id in SAFETY_REVIEW_ABILITIES and bucket["mastered"]:
        mastery = min(mastery, 80.0)

    if bucket["mastered"] and not bucket["weak"] and ability_id not in SAFETY_REVIEW_ABILITIES:
        status = "mastered"
    elif bucket["weak"] and bucket["improving"]:
        status = "improving"
    elif bucket["weak"]:
        status = "weak"
    elif bucket["improving"] or (bucket["mastered"] and ability_id in SAFETY_REVIEW_ABILITIES):
        status = "improving"
    elif bucket["recommended"]:
        status = "recommended_next"
    elif bucket["chat"]:
        status = "touched"
    else:
        status = "unknown"

    reasons = list(dict.fromkeys(bucket["reasons"]))
    if ability_id in SAFETY_REVIEW_ABILITIES and bucket["mastered"]:
        reasons.append("安全相关能力需教师或实训指导人员复核")

    return {
        "status": status,
        "mastery_score": round(mastery, 1),
        "confidence": confidence,
        "low_confidence": confidence < CONFIDENCE_THRESHOLD,
        "evidence_count": evidence_count,
        "last_updated_at": bucket["last_updated_at"],
        "update_reasons": reasons[:5],
        "evidence_events": bucket["events"][-6:],
    }


def graph_update_timeline(session_id):
    record = load_session_record(session_id)
    updates = []
    for event in record.get("events", []):
        ability_ids = event_ability_ids(event)
        if not ability_ids and event.get("event_type") == "chat_message":
            ability_ids = extract_ability_ids(event.get("highlighted_abilities", []))
        if not ability_ids:
            continue
        for ability_id in ability_ids:
            updates.append(
                {
                    "created_at": event.get("created_at"),
                    "event_type": event.get("event_type"),
                    "ability_id": ability_id,
                    "ability_name": load_data()["ability_by_id"].get(ability_id, {}).get("name", ability_id),
                    "reason": event.get("note") or event.get("feedback") or event.get("matched_pattern", {}).get("title") or "图谱证据更新",
                    "source": event.get("source") or "session_event",
                }
            )
    return {"session_id": safe_session_id(session_id), "updates": updates}


def proposal_id():
    return "JP" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


def keyword_hits(material, ability):
    text = material.lower()
    terms = {ability.get("name", ""), ability.get("id", ""), ability.get("description", "")}
    terms.update(ability.get("common_errors", []))
    terms.update(ability.get("related_knowledge", []))
    aliases = {
        "sensor_type_identification": ["npn", "pnp", "传感器类型", "型号", "线色"],
        "sensor_wiring_judgement": ["接线", "端子", "输出线", "黑线", "三线制"],
        "plc_input_common_terminal": ["公共端", "com", "s/s", "输入公共端"],
        "plc_io_address_mapping": ["i/o", "io", "地址", "变量", "映射"],
        "plc_input_monitoring": ["监控", "输入灯", "在线", "输入信号"],
        "input_no_response_fault_scope": ["排故", "无响应", "故障", "定位"],
        "electrical_safety_check": ["安全", "断电", "急停", "气源"],
    }
    terms.update(aliases.get(ability.get("id"), []))
    score = 0
    evidence = []
    for term in terms:
        term = str(term).strip()
        if not term:
            continue
        if term.lower() in text:
            score += 1
            evidence.append(term)
    return score, evidence[:4]


def generate_job_graph_proposals(payload):
    payload = payload or {}
    material = payload.get("material", "") or payload.get("text", "")
    source = payload.get("source", "teacher_imported_material")
    source_type = payload.get("source_type", "teacher_curated")
    if not material.strip():
        raise ValueError("material is required")

    scored = []
    for ability in load_data()["abilities"]:
        score, evidence = keyword_hits(material, ability)
        if score:
            scored.append((score, ability, evidence))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        scored = [(1, load_data()["ability_by_id"][ability_id], ["默认岗位主链"]) for ability_id in list(load_data()["ability_by_id"])[:3]]

    batch_id = proposal_id()
    created_at = now_iso()
    proposals = []
    for score, ability, evidence_terms in scored[:6]:
        action = "strengthen" if ability.get("id") in {"sensor_wiring_judgement", "plc_input_common_terminal", "input_no_response_fault_scope"} else "add_evidence"
        proposals.append(
            {
                "proposal_id": f"{batch_id}-{len(proposals) + 1:02d}",
                "batch_id": batch_id,
                "status": "pending",
                "created_at": created_at,
                "source_type": source_type,
                "source": source,
                "ability_id": ability.get("id"),
                "ability_name": ability.get("name"),
                "action": action,
                "suggested_weight_delta": round(min(0.5, 0.08 * score), 2),
                "evidence": f"材料命中关键词：{'、'.join(evidence_terms)}",
                "material_excerpt": re.sub(r"\s+", " ", material.strip())[:180],
            }
        )

    store = read_runtime_json(JOB_PROPOSALS_PATH, {"version": "0.1.0", "source": "project_runtime", "proposal_batches": [], "proposals": []})
    store.setdefault("proposal_batches", []).append(
        {
            "batch_id": batch_id,
            "created_at": created_at,
            "source_type": source_type,
            "source": source,
            "material_excerpt": re.sub(r"\s+", " ", material.strip())[:240],
            "proposal_count": len(proposals),
        }
    )
    store.setdefault("proposals", []).extend(proposals)
    write_runtime_json(JOB_PROPOSALS_PATH, store)
    return {"batch_id": batch_id, "proposals": proposals}


def pending_job_proposals():
    store = read_runtime_json(JOB_PROPOSALS_PATH, {"version": "0.1.0", "source": "project_runtime", "proposal_batches": [], "proposals": []})
    return [item for item in store.get("proposals", []) if item.get("status") == "pending"]


def confirmed_job_snapshots():
    store = read_runtime_json(JOB_CONFIRMED_PATH, {"version": "0.1.0", "source": "project_runtime", "snapshots": []})
    return store.get("snapshots", [])


def confirm_job_graph_proposals(payload):
    payload = payload or {}
    proposal_ids = set(payload.get("proposal_ids", []))
    confirm_all = bool(payload.get("confirm_all"))
    teacher = payload.get("confirmed_by", "teacher")
    store = read_runtime_json(JOB_PROPOSALS_PATH, {"version": "0.1.0", "source": "project_runtime", "proposal_batches": [], "proposals": []})
    proposals = []
    for proposal in store.get("proposals", []):
        if proposal.get("status") != "pending":
            continue
        if confirm_all or proposal.get("proposal_id") in proposal_ids:
            proposal["status"] = "confirmed"
            proposal["confirmed_at"] = now_iso()
            proposal["confirmed_by"] = teacher
            proposals.append(proposal)

    if not proposals:
        raise ValueError("no pending proposals selected")

    snapshot = {
        "snapshot_id": "CONF" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"),
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source_type": "teacher_confirmed_update",
        "source": f"confirmed_by:{teacher}",
        "job_role": "自动化生产线装调与运维技术员",
        "evidence": "教师确认的岗位能力图谱更新建议。",
        "weight": 0.8,
        "required_abilities": [
            {
                "ability_id": proposal.get("ability_id"),
                "demand_label": "确认更新",
                "evidence": proposal.get("evidence"),
                "weight": max(0.1, proposal.get("suggested_weight_delta", 0.1)),
                "source": proposal.get("source"),
            }
            for proposal in proposals
        ],
    }
    confirmed_store = read_runtime_json(JOB_CONFIRMED_PATH, {"version": "0.1.0", "source": "project_runtime", "snapshots": []})
    confirmed_store.setdefault("snapshots", []).append(snapshot)
    write_runtime_json(JOB_CONFIRMED_PATH, confirmed_store)
    write_runtime_json(JOB_PROPOSALS_PATH, store)
    return {"confirmed": True, "snapshot": snapshot, "confirmed_proposals": proposals}


def generate_proposals_from_evidence(job_role=None):
    """Read evidence from SQLite, compute scores, generate proposals"""
    try:
        from scripts.pipeline.evidence_store import query_events, add_proposal, compute_proposal_score, proposal_threshold
        from .data_loader import primary_job_profile
        
        events = query_events(job_role=(job_role or None), limit=1000)
        abilities = {}
        for ev in events:
            aid = ev["ability_id"]
            if aid not in abilities:
                abilities[aid] = {"count": 0, "source_types": set(), "confs": []}
            abilities[aid]["count"] += 1
            abilities[aid]["source_types"].add(ev.get("source_type", "unknown"))
            abilities[aid]["confs"].append(ev.get("confidence", 0.5))

        target_role = job_role or primary_job_profile().get("role_name", "自动化生产线装调与运维技术员")
        proposals = []
        for aid, data in abilities.items():
            srclist = list(data["source_types"])
            source_type = srclist[0] if srclist else "unknown"
            avg_conf = sum(data["confs"]) / len(data["confs"]) if data["confs"] else 0.5
            score = compute_proposal_score(source_type, avg_conf, data["count"], 7)
            threshold = proposal_threshold(score)
            if threshold in ("auto_approve", "pending"):
                evidence_text = f"{data['count']} 条证据，平均置信度 {round(avg_conf, 2)}"
                pr = add_proposal(
                    job_role=target_role,
                    ability_id=aid,
                    action="strengthen",
                    suggested_weight_delta=round(score * 0.2, 2),
                    evidence=evidence_text,
                    source="evidence_aggregation",
                    proposal_score=score
                )
                pr["threshold"] = threshold
                pr["evidence_count"] = data["count"]
                proposals.append(pr)
        return proposals
    except Exception as e:
        return {"error": str(e)}


def dimension_scores_from_nodes(nodes):
    scores = defaultdict(float)
    for node in nodes:
        weight = float_or_zero(node.get("demand_weight") or node.get("weight") or 0)
        dimensions = node.get("radar_dimension_ids") or ["unknown"]
        for dimension_id in dimensions:
            scores[dimension_id] += weight
    return {key: round(value, 2) for key, value in sorted(scores.items())}


def build_confirmed_proposal_snapshot(job_role, proposals):
    """Create a versioned job graph snapshot after SQLite proposals are confirmed."""
    from app.services.graph import ability_label, build_job_ability_graph, node_payload
    from scripts.pipeline.evidence_store import ability_evidence_summary, create_snapshot

    graph = build_job_ability_graph()
    nodes = [dict(node) for node in graph.get("nodes", [])]
    by_id = {node["id"]: node for node in nodes}

    for proposal in proposals:
        ability_id = proposal.get("ability_id")
        if not ability_id:
            continue
        node = by_id.get(ability_id)
        if not node:
            node = node_payload(ability_id, f"C{len(nodes) + 1}", "industry")
            node["demand_weight"] = 0
            node["evidence"] = []
            node["demand_sources"] = []
            nodes.append(node)
            by_id[ability_id] = node

        delta = float_or_zero(proposal.get("suggested_weight_delta"))
        node["demand_weight"] = round(float_or_zero(node.get("demand_weight")) + delta, 2)
        node["status"] = "industry_hot" if float_or_zero(proposal.get("proposal_score")) >= 0.75 else "industry"
        node["status_label"] = "教师确认更新"
        node.setdefault("evidence", [])
        if proposal.get("evidence"):
            node["evidence"] = list(dict.fromkeys(node["evidence"] + [proposal.get("evidence")]))[:5]
        node.setdefault("demand_sources", [])
        if proposal.get("source"):
            node["demand_sources"] = list(dict.fromkeys(node["demand_sources"] + [proposal.get("source")]))
        node["confirmed_proposal_id"] = proposal.get("proposal_id")
        node["confirmed_by"] = proposal.get("confirmed_by")
        node["confirmed_at"] = proposal.get("confirmed_at")
        node["proposal_score"] = proposal.get("proposal_score")
        node["label"] = node.get("label") or ability_label(ability_id)

    for node in nodes:
        evidence = ability_evidence_summary(node["id"], job_role)
        node["evidence_count"] = evidence["evidence_count"]
        node["avg_confidence"] = evidence["avg_confidence"]
        node["last_updated_at"] = evidence["last_updated_at"]
        node["source_types"] = evidence["source_type_distribution"]
        node["latest_evidence"] = evidence["latest_evidence"]

    dimension_scores = dimension_scores_from_nodes(nodes)
    version = datetime.now(timezone.utc).strftime("v%Y%m%d.%H%M%S.%f")
    snapshot = create_snapshot(job_role, nodes, dimension_scores, version)
    return {
        "snapshot": snapshot,
        "snapshot_graph": {
            "graph_type": "job_ability_snapshot",
            "job_role": job_role,
            "created_from": "confirmed_sqlite_proposals",
            "confirmed_proposal_ids": [item.get("proposal_id") for item in proposals],
            "nodes": nodes,
            "edges": graph.get("edges", []),
            "dimension_scores": dimension_scores,
        },
    }


def confirm_sqlite_job_graph_proposal(payload):
    """Confirm/reject a SQLite proposal and create a graph snapshot on confirmation."""
    from scripts.pipeline.evidence_store import confirm_proposal, reject_proposal

    proposal_id = payload.get("proposal_id", "")
    action = payload.get("action", "confirm")
    if action == "reject":
        return {"action": "reject", "proposal": reject_proposal(proposal_id), "snapshot": None}

    proposal = confirm_proposal(proposal_id, payload.get("confirmed_by", "teacher"))
    if proposal.get("error"):
        return {"action": "confirm", "proposal": proposal, "snapshot": None}

    snapshot_result = build_confirmed_proposal_snapshot(proposal.get("job_role"), [proposal])
    return {
        "action": "confirm",
        "proposal": proposal,
        "snapshot": snapshot_result["snapshot"],
        "snapshot_graph": snapshot_result["snapshot_graph"],
    }


def confirm_sqlite_job_graph_proposals(payload):
    """Confirm/reject multiple SQLite proposals and snapshot confirmed changes by job role."""
    from collections import defaultdict
    from scripts.pipeline.evidence_store import confirm_proposal, get_pending_proposals, reject_proposal

    payload = payload or {}
    action = payload.get("action", "confirm")
    confirmed_by = payload.get("confirmed_by", "teacher")
    job_role = payload.get("job_role")
    proposal_ids = list(dict.fromkeys(payload.get("proposal_ids") or []))

    if payload.get("confirm_all"):
        proposal_ids = [item["proposal_id"] for item in get_pending_proposals(job_role)]
    if not proposal_ids:
        raise ValueError("proposal_ids or confirm_all is required")

    proposals = []
    errors = []
    if action == "reject":
        for proposal_id in proposal_ids:
            result = reject_proposal(proposal_id)
            if result.get("error"):
                errors.append({"proposal_id": proposal_id, "error": result["error"]})
            else:
                proposals.append(result)
        return {
            "action": "reject",
            "requested_count": len(proposal_ids),
            "rejected_count": len(proposals),
            "proposals": proposals,
            "errors": errors,
            "snapshots": [],
        }

    by_role = defaultdict(list)
    for proposal_id in proposal_ids:
        proposal = confirm_proposal(proposal_id, confirmed_by)
        if proposal.get("error"):
            errors.append({"proposal_id": proposal_id, "error": proposal["error"]})
            continue
        proposals.append(proposal)
        by_role[proposal.get("job_role")].append(proposal)

    snapshots = []
    for role, role_proposals in by_role.items():
        snapshot_result = build_confirmed_proposal_snapshot(role, role_proposals)
        snapshots.append({
            "job_role": role,
            "snapshot": snapshot_result["snapshot"],
            "snapshot_graph": snapshot_result["snapshot_graph"],
        })

    return {
        "action": "confirm",
        "requested_count": len(proposal_ids),
        "confirmed_count": len(proposals),
        "proposals": proposals,
        "errors": errors,
        "snapshots": snapshots,
    }
