"""Transfer engine: compute knowledge/procedure/transfer/safety scores.

Evaluates student ability to transfer skills across different scenarios.
Transfer requires at least two different fault contexts with correct application.
Same scenario repeated does not increase transfer_score unbounded.
"""

from collections import defaultdict
from .diagnostic_trace import list_student_traces
from .graph import build_student_ability_graph
from .strategy_profile import build_strategy_profile, build_cumulative_strategy_profile
from .coverage_matrix import build_coverage_matrix


def compute_transfer_scores(session_id):
    """Compute knowledge mastery, procedure mastery, transfer score,
    and safety score for each ability node.

    Returns dict with abilities[] each containing all four scores.
    """
    student_graph = build_student_ability_graph(session_id)
    nodes = student_graph.get("nodes", [])
    traces = list_student_traces(session_id)
    profile = build_cumulative_strategy_profile(session_id)

    # Parse traces into per-ability evidence
    ability_evidence = _collect_ability_evidence(traces)
    coverage = build_coverage_matrix(traces)

    # Build coverage lookup by ability_id
    coverage_by_ability = {}
    for a in coverage.get("abilities", []):
        coverage_by_ability[a["ability_id"]] = a

    # Per-scenario strategy profiles for bias detection
    scenario_profiles = {}
    for t in traces:
        sid = t.get("scenario_id", "")
        if sid and sid not in scenario_profiles:
            scenario_profiles[sid] = build_strategy_profile(session_id, sid)

    abilities = []
    for node in nodes:
        ability_id = node.get("id", "")
        mastery = node.get("mastery_score", 0)
        knowledge_mastery = int(round(mastery * 100)) if mastery <= 1.0 else int(round(mastery))

        evidence = ability_evidence.get(ability_id, {})
        cov = coverage_by_ability.get(ability_id, {})

        # Procedure mastery: based on scenario completions and process conformance
        procedure_mastery = _compute_procedure_mastery(evidence, node)

        # Transfer score: requires cross-scenario evidence
        transfer_score = _compute_transfer_score(evidence, cov, scenario_profiles, profile)

        # Safety score
        safety_score = _compute_safety_score(evidence, node, profile)

        abilities.append({
            "ability_id": ability_id,
            "ability_name": node.get("label", ability_id),
            "status": node.get("status", "unknown"),
            "knowledge_mastery": knowledge_mastery,
            "procedure_mastery": procedure_mastery,
            "transfer_score": transfer_score,
            "safety_score": safety_score,
            "confidence": node.get("confidence", 0),
            "cross_scenario_validated": cov.get("cross_scenario_validated", False),
        })

    return {
        "session_id": session_id,
        "abilities": abilities,
        "summary": {
            "avg_knowledge": _avg([a["knowledge_mastery"] for a in abilities]),
            "avg_procedure": _avg([a["procedure_mastery"] for a in abilities]),
            "avg_transfer": _avg([a["transfer_score"] for a in abilities]),
            "avg_safety": _avg([a["safety_score"] for a in abilities]),
            "cross_validated_count": sum(1 for a in abilities if a["cross_scenario_validated"]),
        },
    }


def _collect_ability_evidence(traces):
    """Collect per-ability evidence from student traces."""
    evidence = defaultdict(lambda: {
        "scenarios": set(),
        "fault_contexts": set(),
        "correct_uses": 0,
        "total_uses": 0,
        "unsafe_events": 0,
        "recent_scenarios": [],
        "strategy_biases": [],
    })

    for trace in traces:
        sid = trace.get("scenario_id", "")
        # Parse trace events from session events (scenario id tracked)
        for event in trace.get("events", []):
            ability_ids = event.get("ability_ids", [])
            outcome = event.get("outcome") or event.get("action_category", "")
            is_correct = outcome in ("correct", "optimal", "valid")
            is_unsafe = outcome == "unsafe" or event.get("action_category") == "unsafe"
            metadata = event.get("metadata", {})
            fault_context = metadata.get("fault_context", sid)

            for aid in ability_ids:
                ev = evidence[aid]
                ev["scenarios"].add(sid)
                if fault_context:
                    ev["fault_contexts"].add(fault_context)
                ev["total_uses"] += 1
                if is_correct:
                    ev["correct_uses"] += 1
                if is_unsafe:
                    ev["unsafe_events"] += 1
                if sid not in ev["recent_scenarios"]:
                    ev["recent_scenarios"].append(sid)
                if event.get("strategy_bias"):
                    ev["strategy_biases"].append(event.get("strategy_bias"))

    return dict(evidence)


def _compute_procedure_mastery(evidence, node):
    """Procedure mastery: accuracy across uses, capped at 100."""
    total = evidence.get("total_uses", 0)
    correct = evidence.get("correct_uses", 0)
    if total == 0:
        ms = node.get("mastery_score", 0)
        return int(round(ms * 100)) if ms <= 1.0 else int(round(ms))
    return min(100, int(round(correct / max(total, 1) * 100)))


def _compute_transfer_score(evidence, coverage, scenario_profiles, cumulative_profile):
    """Compute transfer score based on cross-scenario evidence.

    Rules:
    - 0 scenarios -> 0
    - 1 scenario only -> max 30 (can't prove transfer)
    - 2+ scenarios with different fault contexts -> up to 100
    - Same fault context repeated -> capped at 40
    - Persistent strategy bias across scenarios -> penalty
    """
    scenarios = evidence.get("scenarios", set())
    fault_contexts = evidence.get("fault_contexts", set())
    correct = evidence.get("correct_uses", 0)
    total = evidence.get("total_uses", 0)

    n_scenarios = len(scenarios)
    n_faults = len(fault_contexts)

    if n_scenarios == 0 or total == 0:
        return 0

    # Base score from correctness
    accuracy = correct / max(total, 1)
    base = accuracy * 100

    if n_scenarios == 1:
        # Single scenario: cap at 30
        base = min(base, 30)
    elif n_faults < 2:
        # Multiple scenarios but same fault context: cap at 40
        base = min(base, 40)
    else:
        # True cross-scenario: bonus for each unique fault context
        context_bonus = min(20, (n_faults - 1) * 10)
        base = min(100, base * 0.8 + context_bonus)

    # Penalty for persistent strategy bias
    weaknesses = cumulative_profile.get("weaknesses", [])
    for w in weaknesses:
        if w.get("persistence") == "persistent" and w.get("severity") in ("critical", "high"):
            base = max(0, base - 15)

    return int(round(base))


def _compute_safety_score(evidence, node, profile):
    """Safety score based on unsafe events and safety compliance."""
    unsafe = evidence.get("unsafe_events", 0)
    total = evidence.get("total_uses", 0)

    if total == 0:
        return 100  # Default: assume safe

    unsafe_ratio = unsafe / total
    base = max(0, 100 - unsafe_ratio * 100)

    # Additional penalty from safety-related strategy weaknesses
    weaknesses = profile.get("weaknesses", [])
    for w in weaknesses:
        if w.get("tag") == "safety_procedure_gap":
            severity_penalty = {"critical": 40, "high": 25, "medium": 15, "low": 5}
            base = max(0, base - severity_penalty.get(w.get("severity", "medium"), 15))

    return int(round(base))


def _avg(values):
    if not values:
        return 0
    return round(sum(values) / len(values), 1)
