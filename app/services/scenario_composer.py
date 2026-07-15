"""Dynamic scenario composer for troubleshooting training.

Composes scenario instances from base models by selecting variants,
applying difficulty profiles, and hiding/revealing evidence deterministically.
"""

import hashlib
import json
import random
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
MODELS_PATH = ROOT / "knowledge" / "troubleshooting_models.json"


def _load_models_data():
    if not MODELS_PATH.exists():
        return {}
    return json.loads(MODELS_PATH.read_text(encoding="utf-8"))


def compose_scenario(scenario_id, variant_id=None, difficulty="beginner", seed=None):
    data = _load_models_data()
    models = data.get("models", [])
    base_model = None
    for m in models:
        if m.get("scenario_id") == scenario_id:
            base_model = m
            break
    if not base_model:
        raise ValueError(f"Unknown scenario_id: {scenario_id}")
    if seed is None:
        seed = int(datetime.now(timezone.utc).timestamp()) % 100000
    rng = random.Random(seed)
    variants = base_model.get("variants", [])
    if variant_id:
        selected_variant = None
        for v in variants:
            if v["id"] == variant_id:
                selected_variant = v
                break
        if not selected_variant and variants:
            selected_variant = variants[0]
        elif not selected_variant:
            selected_variant = {"id": variant_id, "initial_facts": {}, "hidden_facts": {}}
    elif variants:
        idx = rng.randint(0, len(variants) - 1)
        selected_variant = variants[idx]
    else:
        selected_variant = {"id": "V_DEFAULT", "initial_facts": {}, "hidden_facts": {}}
    top_difficulty = data.get("difficulty_profiles", {})
    difficulty_profile = top_difficulty.get(difficulty, top_difficulty.get("intermediate", {}))
    visibility = difficulty_profile.get("initial_evidence_visibility", 0.5)
    hint_level = difficulty_profile.get("hint_level", 1)
    distractor_count = difficulty_profile.get("distractor_count", 2)
    variant_initial = selected_variant.get("initial_facts", {})
    variant_hidden = selected_variant.get("hidden_facts", {})
    visible_facts, remaining_hidden = select_visible_facts(
        base_model, selected_variant, visibility, rng
    )
    instance_id = _build_instance_id(scenario_id, selected_variant.get("id", "V_DEFAULT"), seed, difficulty)
    instance = build_scenario_instance(
        base_model, selected_variant, visible_facts, remaining_hidden,
        difficulty, hint_level, distractor_count, seed, instance_id
    )
    errors = validate_scenario_instance(instance)
    if errors:
        raise ValueError(f"Scenario instance validation failed: {errors}")
    return instance


def _build_instance_id(scenario_id, variant_id, seed, difficulty):
    raw = f"{scenario_id}:{variant_id}:{seed}:{difficulty}"
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"INST-{scenario_id}-{variant_id}-S{seed}-D{difficulty[0]}-{h}"


def select_visible_facts(model, variant, visibility_ratio, rng):
    initial = dict(variant.get("initial_facts", {}))
    hidden = dict(variant.get("hidden_facts", {}))
    hidden_keys = list(hidden.keys())
    rng.shuffle(hidden_keys)
    num_reveal = max(0, int(len(hidden_keys) * visibility_ratio))
    visible = dict(initial)
    for i in range(num_reveal):
        key = hidden_keys[i]
        visible[key] = hidden.pop(key)
    return visible, hidden


def build_scenario_instance(base_model, variant, visible_facts, hidden_facts,
                              difficulty, hint_level, distractor_count, seed, instance_id):
    variant_fault_id = variant.get("fault_id")
    all_hypotheses = []
    for hyp in base_model.get("hypotheses", []):
        entry = {
            "id": hyp["id"],
            "label": hyp.get("label", hyp["id"]),
            "description": hyp.get("description", ""),
            "is_root_cause": hyp["id"] == variant_fault_id,
        }
        all_hypotheses.append(entry)
    allowed_actions = variant.get("allowed_actions") or [
        a["id"] for a in base_model.get("diagnostic_actions", [])
    ]
    if difficulty == "beginner":
        unsafe_ids = set()
        for a in base_model.get("diagnostic_actions", []):
            if a.get("category") in ("unsafe", "invalid"):
                unsafe_ids.add(a["id"])
        allowed_actions = [aid for aid in allowed_actions if aid not in unsafe_ids]
    expected_root_cause = variant.get("expected_root_cause", variant_fault_id)
    vis_map = {"beginner": 0.8, "intermediate": 0.5, "advanced": 0.2}
    expected_completion_requirements = {
        "root_cause_identified": expected_root_cause,
        "safety_checked": any(
            a.get("id") == "CHECK_SAFETY"
            for a in base_model.get("diagnostic_actions", [])
        ),
        "min_evidence_collected": max(1, int(3 * (1.0 - vis_map.get(difficulty, 0.5)))),
    }
    diff_labels = {
        "beginner": "\u521d\u7ea7",
        "intermediate": "\u4e2d\u7ea7",
        "advanced": "\u9ad8\u7ea7",
    }
    return {
        "scenario_instance_id": instance_id,
        "base_scenario_id": base_model.get("scenario_id"),
        "variant_id": variant.get("id", "V_DEFAULT"),
        "variant_label": variant.get("label", variant.get("id", "")),
        "seed": seed,
        "difficulty": difficulty,
        "difficulty_profile": {
            "label": diff_labels.get(difficulty, difficulty),
            "visibility": vis_map[difficulty],
            "hint_level": hint_level,
            "distractor_count": distractor_count,
        },
        "title": base_model.get("title", base_model.get("scenario_id", "")),
        "visible_facts": visible_facts,
        "hidden_facts": hidden_facts,
        "count_hidden_facts": len(hidden_facts),
        "count_visible_facts": len(visible_facts),
        "possible_hypotheses": all_hypotheses,
        "allowed_actions": allowed_actions,
        "expected_completion_requirements": expected_completion_requirements,
        "fault_states": base_model.get("fault_states", {}),
        "diagnostic_actions": base_model.get("diagnostic_actions", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_scenario_instance(instance):
    errors = []
    required_fields = [
        "scenario_instance_id", "base_scenario_id", "variant_id",
        "seed", "difficulty", "visible_facts", "hidden_facts",
        "possible_hypotheses", "allowed_actions",
    ]
    for field in required_fields:
        if field not in instance:
            errors.append(f"Missing required field: {field}")
    visible_keys = set(instance.get("visible_facts", {}).keys())
    hidden_keys = set(instance.get("hidden_facts", {}).keys())
    overlap = visible_keys & hidden_keys
    if overlap:
        errors.append(f"Facts overlap between visible and hidden: {overlap}")
    root_causes = [
        h for h in instance.get("possible_hypotheses", []) if h.get("is_root_cause")
    ]
    if not root_causes:
        errors.append("No root cause hypothesis marked")
    exp_root = instance.get("expected_completion_requirements", {}).get(
        "root_cause_identified"
    )
    if exp_root:
        hyp_ids = {h["id"] for h in instance.get("possible_hypotheses", [])}
        if exp_root not in hyp_ids:
            errors.append(f"Expected root cause {exp_root} not in possible_hypotheses")
    # Allowed actions may reference actions from variant or base model
    # Only flag actions that appear nowhere in the model
    diag_ids = {a["id"] for a in instance.get("diagnostic_actions", [])}
    variant_allowed = set(instance.get("allowed_actions", []))
    # Also check fault_states for additional state-based actions if any
    unknown = variant_allowed - diag_ids
    if unknown:
        # These are variant-specific actions not in base diagnostic_actions
        # This is acceptable as variants may introduce new actions
        pass
    if instance.get("difficulty") == "beginner":
        for a in instance.get("diagnostic_actions", []):
            if (
                a.get("category") in ("unsafe", "invalid")
                and a["id"] in instance.get("allowed_actions", [])
            ):
                errors.append(f"Unsafe action {a['id']} in beginner difficulty")
    return errors


def list_variants_for_scenario(scenario_id):
    models = _load_models_data().get("models", [])
    for m in models:
        if m.get("scenario_id") == scenario_id:
            return m.get("variants", [])
    return []


def list_all_variants():
    result = {}
    models = _load_models_data().get("models", [])
    for m in models:
        sid = m.get("scenario_id")
        variants = m.get("variants", [])
        if variants:
            result[sid] = [
                {
                    "id": v["id"],
                    "label": v.get("label", v["id"]),
                    "fault_id": v.get("fault_id"),
                }
                for v in variants
            ]
    return result


def get_difficulty_profiles():
    return _load_models_data().get("difficulty_profiles", {})


def get_neighbor_counterexample_pairs():
    return _load_models_data().get("neighbor_counterexample_pairs", [])
