"""
Cognitive digital twin for student troubleshooting.

Combines knowledge/procedure mastery, process metrics, strategy profile,
and safety scores into a unified per-ability cognitive twin view.

Output per ability node:
- knowledge_mastery: from existing graph (0-100)
- procedure_mastery: derived from process conformance (0-100)
- transfer_score: null (reserved for Phase 5)
- safety_score: from safety compliance + unsafe actions (0-100)
- process_metrics: 5-dimension sub-scores
- strategy_tags: recurring bias labels
"""

from .graph import build_student_ability_graph
from .graph_update_engine import personal_graph_state, compute_node_metrics
from .process_metrics import compute_all_metrics
from .strategy_profile import build_cumulative_strategy_profile
from .transfer_engine import compute_transfer_scores
from .diagnostic_trace import list_student_traces


def build_cognitive_twin(session_id):
    """
    Build a cognitive digital twin view for all ability nodes.

    Returns:
        dict with twin_id, session_id, abilities[] (each with process metadata)
    """
    # Get existing student graph
    student_graph = build_student_ability_graph(session_id)
    nodes = student_graph.get("nodes", [])

    # Get strategy profile
    profile = build_cumulative_strategy_profile(session_id)
    transfer_data = compute_transfer_scores(session_id)
    strategy_tags = [
        {"tag": w["tag"], "label": w["label"], "persistence": w.get("persistence", "observed")}
        for w in profile.get("weaknesses", [])
    ]

    # Get process metrics for each scenario
    traces = list_student_traces(session_id)
    all_metrics = {}
    for trace_info in traces:
        sid = trace_info.get("scenario_id", "")
        if sid:
            all_metrics[sid] = compute_all_metrics(session_id, sid)

    # Aggregate metrics across scenarios
    aggregated_metrics = _aggregate_metrics(all_metrics)

    # Per-ability mapping: which abilities are covered by which process metrics
    ability_to_metrics = _map_abilities_to_metrics(nodes, all_metrics)

    abilities = []
    for node in nodes:
        ability_id = node.get("id", "")
        mastery_score = node.get("mastery_score", 0)

        # Procedure mastery: derived from process conformance fitness. Prefer
        # the unified personal-graph profile when available so the graph and
        # twin tell the same story.
        proc_metrics = ability_to_metrics.get(ability_id, aggregated_metrics)
        procedure_mastery = node.get("procedure_mastery")
        if procedure_mastery is None:
            procedure_mastery = _derive_procedure_mastery(proc_metrics, mastery_score)

        # Safety score
        safety_score = node.get("safety_score")
        if safety_score is None:
            safety_score = _derive_safety_score(node, proc_metrics, strategy_tags)

        # Knowledge mastery (map from existing mastery_score 0-1 to 0-100)
        # mastery_score may already be 0-100 or 0-1; normalize to 0-100 scale
        knowledge_mastery = node.get("knowledge_mastery")
        if knowledge_mastery is None:
            knowledge_mastery = int(round(mastery_score * 100)) if mastery_score <= 1.0 else int(round(mastery_score))

        abilities.append({
            "ability_id": ability_id,
            "ability_name": node.get("label", ability_id),
            "status": node.get("status", "unknown"),
            "knowledge_mastery": knowledge_mastery,
            "procedure_mastery": procedure_mastery,
            "transfer_score": node.get("transfer_score") if node.get("transfer_score") is not None else _get_transfer_for_ability(ability_id, transfer_data),
            "safety_score": safety_score,
            "cognitive_mastery_score": node.get("cognitive_mastery_score"),
            "uncertainty": node.get("uncertainty"),
            "confidence": node.get("confidence", 0),
            "process_metrics": node.get("process_metrics") or {
                "safety_compliance": proc_metrics.get("safety_compliance", 0),
                "evidence_quality": proc_metrics.get("evidence_quality", 0),
                "fault_localization": proc_metrics.get("fault_localization", 0),
                "diagnostic_efficiency": proc_metrics.get("diagnostic_efficiency", 0),
                "closure_verification": proc_metrics.get("closure_verification", 0),
            },
            "strategy_tags": node.get("strategy_tags") or strategy_tags,
            "process_evidence": node.get("process_evidence", []),
            "safety_gate": node.get("safety_gate"),
            "recommended_intervention": node.get("recommended_intervention"),
            "update_reasons": node.get("update_reasons", []),
            # Compatibility fields
            "mastery_score": mastery_score,
            "evidence_count": node.get("evidence_count", 0),
            "last_updated_at": node.get("last_updated_at"),
        })

    return {
        "twin_id": f"twin:{session_id}",
        "session_id": session_id,
        "trace_count": len(traces),
        "aggregated_metrics": aggregated_metrics,
        "strategy_profile": {
            "weaknesses": profile.get("weaknesses", []),
            "strengths": profile.get("strengths", []),
            "preferred_strategy_id": profile.get("preferred_strategy_id"),
            "trace_count": profile.get("trace_count", 0),
        },
        "abilities": abilities,
    }



def _get_transfer_for_ability(ability_id, transfer_data):
    """Extract transfer score for a specific ability from transfer data."""
    if not transfer_data:
        return None
    for a in transfer_data.get("abilities", []):
        if a.get("ability_id") == ability_id:
            return a.get("transfer_score")
    return None


def _aggregate_metrics(all_metrics):
    """Aggregate process metrics across scenarios (average)."""
    if not all_metrics:
        return {
            "safety_compliance": 0,
            "evidence_quality": 0,
            "fault_localization": 0,
            "diagnostic_efficiency": 0,
            "closure_verification": 0,
        }

    keys = ["safety_compliance", "evidence_quality", "fault_localization",
            "diagnostic_efficiency", "closure_verification"]
    result = {}
    for key in keys:
        values = [m.get(key, 0) for m in all_metrics.values()]
        result[key] = round(sum(values) / len(values), 2)
    return result


def _map_abilities_to_metrics(nodes, all_metrics):
    """
    Map each ability to its most relevant process metrics.
    Currently a simple mapping: safety abilities -> safety_compliance,
    troubleshooting abilities -> fault_localization, etc.
    """
    safety_abilities = {"electrical_safety_check", "power_isolation_confirmation",
                         "dc24v_power_check", "multimeter_voltage_measurement"}
    evidence_abilities = {"sensor_type_identification", "sensor_wiring_judgement",
                           "sensor_led_observation", "plc_input_common_terminal",
                           "plc_input_grouping", "input_led_compare"}
    localization_abilities = {"input_no_response_fault_scope", "plc_io_address_mapping",
                               "program_variable_lookup", "no_response_common_terminal_check",
                               "no_response_address_mapping_check", "no_response_sensor_side_check",
                               "no_response_power_path_check"}
    closure_abilities = {"plc_input_monitoring", "diagnosis_record_feedback"}

    result = {}
    aggregated = _aggregate_metrics(all_metrics)

    for node in nodes:
        ability_id = node.get("id", "")
        metrics = dict(aggregated)

        if ability_id in safety_abilities:
            # Weight safety_compliance higher
            pass
        elif ability_id in evidence_abilities:
            metrics["evidence_quality"] = aggregated.get("evidence_quality", 0)
        elif ability_id in localization_abilities:
            metrics["fault_localization"] = aggregated.get("fault_localization", 0)
        elif ability_id in closure_abilities:
            metrics["closure_verification"] = aggregated.get("closure_verification", 0)

        result[ability_id] = metrics

    return result


def _derive_procedure_mastery(metrics, mastery_score):
    """
    Derive procedure mastery from process metrics.
    Weighted average of fault_localization, diagnostic_efficiency, and closure_verification.
    """
    fl = metrics.get("fault_localization", 0)
    de = metrics.get("diagnostic_efficiency", 0)
    cv = metrics.get("closure_verification", 0)
    raw = (fl * 0.4 + de * 0.3 + cv * 0.3) * 100
    return int(round(raw))


def _derive_safety_score(node, metrics, strategy_tags):
    """Derive safety score from safety compliance and strategy profile."""
    base = metrics.get("safety_compliance", 0) * 100

    # Penalize if safety-related strategy tags present
    safety_penalty = 0
    for tag in strategy_tags:
        if tag["tag"] == "safety_procedure_gap":
            safety_penalty += 30

    return max(0, min(100, int(base - safety_penalty)))
