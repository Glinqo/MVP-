from .data_loader import load_data
from .graph import build_student_ability_graph
from .graph_update_engine import record_student_graph_event
from .scenario_composer import compose_scenario as compose_ts_scenario


def compact_ability(ability_id):
    ability = load_data()["ability_by_id"].get(ability_id, {})
    if not ability:
        return {"id": ability_id, "name": ability_id}
    return {
        "id": ability_id,
        "name": ability.get("name", ability_id),
        "source": ability.get("source") or ", ".join(ability.get("sources", [])[:2]),
    }


def scenario_by_id(scenario_id=None):
    scenarios = load_data()["troubleshooting_scenarios"]
    if scenario_id:
        for scenario in scenarios:
            if scenario.get("id") == scenario_id:
                return scenario
    if not scenarios:
        raise ValueError("no troubleshooting scenarios configured")
    return scenarios[0]


def step_by_id(scenario, step_id=None):
    steps = scenario.get("steps", [])
    if step_id:
        for step in steps:
            if step.get("id") == step_id:
                return step
    if not steps:
        raise ValueError("scenario has no steps")
    return steps[0]


def public_step(step):
    return {
        "id": step.get("id"),
        "prompt": step.get("prompt"),
        "ability_hits": [compact_ability(item) for item in step.get("ability_ids", [])],
        "options": [
            {
                "id": option.get("id"),
                "text": option.get("text"),
            }
            for option in step.get("options", [])
        ],
    }


def scenario_summary(scenario):
    return {
        "id": scenario.get("id"),
        "title": scenario.get("title"),
        "roleplay_frame": scenario.get("roleplay_frame"),
        "initial_symptom": scenario.get("initial_symptom"),
        "safety_notice": scenario.get("safety_notice"),
        "ability_hits": [compact_ability(item) for item in scenario.get("ability_ids", [])],
        "source": scenario.get("source"),
    }


def list_scenarios():
    return {
        "scenarios": [
            {
                "id": scenario.get("id"),
                "title": scenario.get("title"),
                "initial_symptom": scenario.get("initial_symptom"),
                "ability_hits": [compact_ability(item) for item in scenario.get("ability_ids", [])],
                "source": scenario.get("source"),
            }
            for scenario in load_data()["troubleshooting_scenarios"]
        ]
    }


def start_scenario(payload=None):
    payload = payload or {}
    scenario = scenario_by_id(payload.get("scenario_id"))
    first_step = step_by_id(scenario)
    session_id = payload.get("session_id")
    if session_id:
        record_student_graph_event(
            {
                "session_id": session_id,
                "event_type": "scenario_started",
                "ability_ids": scenario.get("ability_ids", []),
                "note": scenario.get("title"),
                "source": scenario.get("source", "project_curated"),
            }
        )
        # Phase 5: Compose scenario instance if variant/difficulty/seed specified
    composed_instance = None
    if payload.get("variant_id") or payload.get("difficulty") not in (None, "intermediate") or payload.get("seed"):
        try:
            composed_instance = compose_ts_scenario(
                scenario_id=scenario.get("id"),
                variant_id=payload.get("variant_id"),
                difficulty=payload.get("difficulty", "intermediate"),
                seed=payload.get("seed"),
            )
        except Exception:
            pass

    return {
        "status": "in_progress",
        "scenario": scenario_summary(scenario),
        "current_step": public_step(first_step),
        "student_graph": build_student_ability_graph(session_id) if session_id else None,
        "composed_instance": composed_instance,
    }


def step_scenario(payload=None):
    payload = payload or {}
    scenario = scenario_by_id(payload.get("scenario_id"))
    step = step_by_id(scenario, payload.get("step_id"))
    choice_id = payload.get("choice_id")
    option = None
    for item in step.get("options", []):
        if item.get("id") == choice_id:
            option = item
            break
    if not option:
        raise ValueError("choice_id not found")

    is_correct = bool(option.get("is_correct"))
    next_step = step_by_id(scenario, step.get("next_step_id")) if step.get("next_step_id") else None
    completed = is_correct and next_step is None
    session_id = payload.get("session_id")
    event_type = "scenario_step_completed" if is_correct else "scenario_step_mistake"
    ability_ids = step.get("ability_ids", [])
    if session_id:
        record_student_graph_event(
            {
                "session_id": session_id,
                "event_type": event_type,
                "ability_ids": ability_ids,
                "outcome": "correct" if is_correct else "incorrect",
                "note": f"{scenario.get('title')} / {step.get('id')} / 选择 {choice_id}",
                "source": scenario.get("source", "project_curated"),
            }
        )

    return {
        "status": "completed" if completed else "in_progress",
        "scenario": scenario_summary(scenario),
        "step_id": step.get("id"),
        "choice_id": choice_id,
        "is_correct": is_correct,
        "feedback": option.get("feedback"),
        "observation": option.get("observation"),
        "ability_hits": [compact_ability(item) for item in ability_ids],
        "current_step": public_step(next_step) if is_correct and next_step else (public_step(step) if not is_correct else None),
        "suggested_questions": [
            "为什么这一步要放在当前顺序？",
            "如果我选错了，对应哪个能力点薄弱？",
            "能不能把这个场景转换成一张排故检查表？",
        ],
        "student_graph": build_student_ability_graph(session_id) if session_id else None,
    }

# --- New structured diagnostic action interface (Phase 1) ---

# In-memory session store for diagnostic state (maps session_id -> state dict)
_diagnostic_sessions = {}


def _session_state(session_id):
    """Get or create diagnostic session state."""
    session_id = str(session_id or "default")
    if session_id not in _diagnostic_sessions:
        _diagnostic_sessions[session_id] = {
            "session_id": session_id,
            "scenario_id": None,
            "current_state": {},
            "action_history": [],
            "action_classifications": [],
        }
    return _diagnostic_sessions[session_id]


def action_scenario(payload=None):
    """
    Handle a diagnostic action through the behavior graph tracer.

    Uses model_tracer for state-machine-based classification and
    scaffolding_engine for adaptive hint generation.

    Accepts: action_id, scenario_id, session_id, runtime_state (optional).
    """
    from .diagnostic_events import build_diagnostic_event
    from .model_tracer import model_for_scenario, trace_action, state_flags_from_runtime
    from .scaffolding_engine import generate_hint

    payload = payload or {}
    scenario_id = payload.get("scenario_id")
    if not scenario_id:
        raise ValueError("scenario_id is required")

    action_id = payload.get("action_id")
    if not action_id:
        raise ValueError("action_id is required")

    model = model_for_scenario(scenario_id)
    if not model:
        raise ValueError(f"no troubleshooting model for scenario: {scenario_id}")

    session_id = payload.get("session_id", "default")
    state = _session_state(session_id)

    # Initialize state from model on first call or scenario change
    if state["scenario_id"] != scenario_id:
        state["scenario_id"] = scenario_id
        state["current_state"] = {"state_id": "STATE_INITIAL"}
        state["action_history"] = []
        state["action_classifications"] = []
        state["student_trace"] = []

    # Merge runtime_state from payload (for manual state injection)
    runtime_state = payload.get("runtime_state", {}) or {}
    state["current_state"].update(runtime_state)

    # --- Phase 2: Trace action through behavior graph ---
    trace_output = trace_action(model, state["current_state"], action_id, state["student_trace"])
    trace_result = trace_output["trace_result"]

    # Update session state
    state["current_state"] = trace_output["runtime_state"]
    new_trace_entry = trace_output["student_trace_snapshot"][-1] if trace_output["student_trace_snapshot"] else {}
    state["student_trace"] = trace_output["student_trace_snapshot"]
    state["action_history"].append(action_id)
    state["action_classifications"].append({
        "category": trace_result["classification"],
        "strategy_bias": (trace_result.get("deviations") or [None])[0] if trace_result.get("deviations") else None,
    })

    # --- Phase 1 compat: also compute through diagnostic_events ---
    from .diagnostic_events import (
        classify_action as legacy_classify,
        check_completion,
        evaluate_remaining_hypotheses,
        compute_strategy_bias,
    )
    legacy_classification = legacy_classify(model, action_id, state["current_state"], state["action_history"])
    completion = check_completion(model, state["current_state"], state["action_history"])
    hypotheses = evaluate_remaining_hypotheses(model, state["current_state"], state["action_history"])
    strategy_biases = compute_strategy_bias(state["action_classifications"])

    # --- Scaffolding hint ---
    state_flags = state_flags_from_runtime(model, state["current_state"])
    scaffolding = generate_hint(
        model, trace_result, state["student_trace"], state_flags,
        state["current_state"].get("state_id", "STATE_INITIAL"), action_id
    )

    # --- Action label ---
    action_label = action_id
    for a in model.get("diagnostic_actions", []):
        if a["id"] == action_id:
            action_label = a.get("label", action_id)
            break

    # --- Abilities ---
    ability_ids = []
    for a in model.get("diagnostic_actions", []):
        if a["id"] == action_id:
            ability_ids = a.get("related_abilities", [])
            break

    # --- Record to student graph ---
    scenario = scenario_by_id(scenario_id)
    if session_id and session_id != "default":
        event_type = "scenario_step_completed" if trace_result["classification"] in ("optimal", "valid") else "scenario_step_mistake"
        record_student_graph_event(
            {
                "session_id": session_id,
                "event_type": event_type,
                "ability_ids": ability_ids,
                "outcome": trace_result["classification"],
                "note": f"{scenario.get('title', scenario_id)} / ?? {action_id} / {trace_result['classification']}",
                "source": scenario.get("source", "project_curated"),
            }
        )

        # Diagnostic event with rich metadata
        diagnostic_event = build_diagnostic_event(
            session_id, scenario_id, action_id,
            {"category": trace_result["classification"], "category_label": trace_result["classification"],
             "is_valid": trace_result["accepted"], "blocked_by": trace_result.get("deviations", []),
             "evidence_gained": None, "strategy_bias": (trace_result.get("deviations") or [None])[0]},
            scenario.get("title", scenario_id), ability_ids,
            (trace_result.get("deviations") or [None])[0] if trace_result.get("deviations") else None,
            state["current_state"],
        )
        from .feedback import append_session_event
        append_session_event(session_id, diagnostic_event)

    # --- Phase 4: Counterfactual action analysis ---
    from .counterfactual_action import analyze_next_action
    from .hypothesis_engine import initialize_hypotheses
    state_flags_for_analysis = state_flags_from_runtime(model, state["current_state"])
    hyp_state = initialize_hypotheses(model)
    next_action_analysis = analyze_next_action(
        model, state_flags_for_analysis, state["action_history"],
        student_weak_abilities=None, existing_hypotheses=hyp_state
    )

    return {
        "status": "completed" if completion["is_complete"] else "in_progress",
        "scenario": scenario_summary(scenario),
        "action_id": action_id,
        "action_label": action_label,
        # Phase 2: trace result
        "trace_result": {
            "classification": trace_result["classification"],
            "matched_strategy_id": trace_result["matched_strategy_id"],
            "matched_transition_id": trace_result["matched_transition_id"],
            "state_before": trace_result["state_before"],
            "state_after": trace_result["state_after"],
            "deviations": trace_result["deviations"],
            "repeated_action": trace_result["repeated_action"],
            "is_terminal": trace_result["is_terminal"],
        },
        "strategies": trace_output["strategies"],
        # Scaffolding
        "scaffolding": scaffolding,
        # Phase 1 compat
        "action_category": legacy_classification["category"],
        "action_category_label": legacy_classification["category_label"],
        "is_valid": trace_result["accepted"],
        "blocked_by": legacy_classification.get("blocked_by", []),
        "evidence_gained": legacy_classification.get("evidence_gained"),
        "strategy_bias": (trace_result.get("deviations") or [None])[0] if trace_result.get("deviations") else None,
        "explanation": legacy_classification.get("explanation", ""),
        "ability_hits": [compact_ability(item) for item in ability_ids],
        "current_state": dict(state["current_state"]),
        "action_history": list(state["action_history"]),
        "hypotheses": hypotheses,
        "completion": completion,
        "strategy_biases": strategy_biases,
        "suggested_questions": [
            "????????????????",
            "????????????",
            "???????????",
        ],
        "student_graph": build_student_ability_graph(session_id) if session_id else None,
    }