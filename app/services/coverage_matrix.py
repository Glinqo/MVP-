"""Coverage matrix: ability x scenario x fault_context x evidence_type.

Tracks which abilities are covered in which scenarios, with what fault contexts,
and what types of evidence (positive/negative/process).
"""

import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]


def _load_models():
    p = ROOT / "knowledge" / "troubleshooting_models.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _load_scenarios():
    p = ROOT / "knowledge" / "troubleshooting_scenarios.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _load_abilities():
    p = ROOT / "knowledge" / "ability_nodes.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def build_coverage_matrix(traces=None):
    """Build a coverage matrix from scenario models and student traces.

    Returns dict with abilities[] each containing:
    - ability_id, ability_name
    - scenarios_covered: [{scenario_id, fault_contexts[], evidence_types[], last_verified}]
    - total_scenarios, total_fault_contexts
    - cross_scenario_validated: bool
    - single_scenario_only: bool
    - never_validated: bool
    """
    data = _load_models()
    models = data.get("models", [])
    scenarios_data = _load_scenarios()
    abilities_data = _load_abilities()

    # Build ability lookup
    ability_lookup = {}
    for node in abilities_data.get("nodes", []):
        ability_lookup[node["id"]] = {
            "name": node.get("name", node["id"]),
            "level": node.get("level", "basic"),
        }

    # Build scenario-ability mapping from scenarios.json
    scenario_ability_map = {}
    for s in scenarios_data.get("scenarios", []):
        sid = s.get("id", "")
        scenario_ability_map[sid] = {
            "title": s.get("title", sid),
            "ability_ids": s.get("ability_ids", []),
        }

    # Augment with model hypotheses (each hypothesis has related_abilities)
    for model in models:
        sid = model.get("scenario_id", "")
        if sid not in scenario_ability_map:
            scenario_ability_map[sid] = {"title": model.get("title", sid), "ability_ids": []}
        for hyp in model.get("hypotheses", []):
            for aid in hyp.get("related_abilities", []):
                if aid not in scenario_ability_map[sid]["ability_ids"]:
                    scenario_ability_map[sid]["ability_ids"].append(aid)
        # Also from diagnostic actions
        for action in model.get("diagnostic_actions", []):
            for aid in action.get("related_abilities", []):
                if aid not in scenario_ability_map[sid]["ability_ids"]:
                    scenario_ability_map[sid]["ability_ids"].append(aid)

    # Build variant-ability mapping
    variant_ability_map = {}
    for model in models:
        sid = model.get("scenario_id", "")
        for variant in model.get("variants", []):
            vid = variant.get("id", "")
            fault_id = variant.get("fault_id", "")
            # Get abilities from the fault hypothesis
            fault_abilities = []
            for hyp in model.get("hypotheses", []):
                if hyp["id"] == fault_id:
                    fault_abilities = hyp.get("related_abilities", [])
                    break
            variant_ability_map[vid] = {
                "scenario_id": sid,
                "fault_id": fault_id,
                "ability_ids": fault_abilities,
            }

    # Build per-ability coverage
    all_ability_ids = set()
    for info in scenario_ability_map.values():
        all_ability_ids.update(info["ability_ids"])
    for info in variant_ability_map.values():
        all_ability_ids.update(info["ability_ids"])

    # Add trace-based verification (if provided)
    trace_coverage = _trace_coverage(traces) if traces else {}

    abilities = []
    for aid in sorted(all_ability_ids):
        info = ability_lookup.get(aid, {"name": aid, "level": "basic"})
        scenarios_covered = []
        fault_contexts = set()

        for sid, s_info in scenario_ability_map.items():
            if aid in s_info["ability_ids"]:
                # Find fault contexts for this ability in this scenario
                contexts = []
                for model in models:
                    if model.get("scenario_id") == sid:
                        for variant in model.get("variants", []):
                            v_abilities = variant_ability_map.get(variant["id"], {}).get("ability_ids", [])
                            if aid in v_abilities:
                                contexts.append({
                                    "variant_id": variant["id"],
                                    "fault_id": variant.get("fault_id", ""),
                                    "label": variant.get("label", ""),
                                })
                                fault_contexts.add(variant.get("fault_id", ""))

                # Check trace verification
                trace_key = f"{sid}:{aid}"
                last_verified = trace_coverage.get(trace_key, {}).get("last_verified")

                scenarios_covered.append({
                    "scenario_id": sid,
                    "scenario_title": s_info.get("title", sid),
                    "fault_contexts": contexts,
                    "evidence_types": ["process"],  # process evidence from scenario participation
                    "last_verified": last_verified,
                })

        total_scenarios = len(scenarios_covered)
        total_fault_contexts = len(fault_contexts)
        cross_validated = total_scenarios >= 2 and total_fault_contexts >= 2
        single_only = total_scenarios == 1
        never_validated = total_scenarios == 0

        abilities.append({
            "ability_id": aid,
            "ability_name": info["name"],
            "level": info.get("level", "basic"),
            "scenarios_covered": scenarios_covered,
            "total_scenarios": total_scenarios,
            "total_fault_contexts": total_fault_contexts,
            "cross_scenario_validated": cross_validated,
            "single_scenario_only": single_only,
            "never_validated": never_validated,
        })

    # Neighbor pairs
    neighbor_pairs = data.get("neighbor_counterexample_pairs", [])

    return {
        "abilities": abilities,
        "total_abilities": len(abilities),
        "cross_validated_count": sum(1 for a in abilities if a["cross_scenario_validated"]),
        "single_scenario_count": sum(1 for a in abilities if a["single_scenario_only"]),
        "never_validated_count": sum(1 for a in abilities if a["never_validated"]),
        "neighbor_counterexample_pairs": neighbor_pairs,
        "scenario_count": len(scenario_ability_map),
        "variant_count": len(variant_ability_map),
    }


def _trace_coverage(traces):
    """Parse student traces to find which abilities were verified and when."""
    result = {}
    if not traces:
        return result
    for trace in traces:
        sid = trace.get("scenario_id", "")
        for event in trace.get("events", []):
            ability_ids = event.get("ability_ids", [])
            timestamp = event.get("timestamp") or datetime.now().isoformat()
            for aid in ability_ids:
                key = f"{sid}:{aid}"
                if key not in result or timestamp > result[key].get("last_verified", ""):
                    result[key] = {
                        "scenario_id": sid,
                        "ability_id": aid,
                        "last_verified": timestamp,
                    }
    return result


def get_coverage_summary():
    """Get a concise coverage summary for API responses."""
    matrix = build_coverage_matrix()
    return {
        "total_abilities": matrix["total_abilities"],
        "cross_validated": matrix["cross_validated_count"],
        "single_scenario_only": matrix["single_scenario_count"],
        "never_validated": matrix["never_validated_count"],
        "neighbor_pairs_count": len(matrix["neighbor_counterexample_pairs"]),
    }


def get_abilities_needing_validation():
    """Get abilities that lack cross-scenario validation."""
    matrix = build_coverage_matrix()
    return [
        {
            "ability_id": a["ability_id"],
            "ability_name": a["ability_name"],
            "reason": "single_scenario" if a["single_scenario_only"] else "never_validated",
            "total_scenarios": a["total_scenarios"],
            "total_fault_contexts": a["total_fault_contexts"],
        }
        for a in matrix["abilities"]
        if not a["cross_scenario_validated"]
    ]
