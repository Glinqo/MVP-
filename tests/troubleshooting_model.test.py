"""
Test 1: Data integrity of troubleshooting models.

Validates:
1. Every existing scenario has a corresponding troubleshooting model
2. All action IDs are unique within a scenario
3. All hypothesis IDs are unique within a scenario
4. All ability IDs exist in ability_nodes.json
5. All existing step options can be mapped to action IDs (not enforced, noted)
6. All action-referenced hypotheses exist
7. Completion requirement format is legal
"""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.data_loader import load_data


def main():
    errors = []
    data = load_data()
    ability_by_id = data["ability_by_id"]
    scenarios = data["troubleshooting_scenarios"]

    models_path = ROOT / "knowledge" / "troubleshooting_models.json"
    if not models_path.exists():
        errors.append("troubleshooting_models.json not found")
        print("FAIL: " + "\n".join(errors))
        sys.exit(1)

    models_data = json.loads(models_path.read_text(encoding="utf-8"))
    models = {m["scenario_id"]: m for m in models_data.get("models", [])}

    print(f"Loaded {len(models)} models for {len(scenarios)} scenarios")

    # 1. Every existing scenario has a model
    for scenario in scenarios:
        sid = scenario.get("id")
        if sid not in models:
            errors.append(f"Scenario {sid} has no troubleshooting model")
        else:
            print(f"  OK: scenario {sid} -> model found")

    # 2-7. Per-model checks
    for sid, model in models.items():
        actions = model.get("diagnostic_actions", [])
        hypotheses = model.get("hypotheses", [])
        strategy_biases = model.get("strategy_biases", {})

        # 2. Action IDs unique
        action_ids = [a["id"] for a in actions]
        dupes = [aid for aid in action_ids if action_ids.count(aid) > 1]
        if dupes:
            errors.append(f"Model {sid}: duplicate action IDs: {list(set(dupes))}")
        else:
            print(f"  OK: model {sid} has {len(actions)} unique actions")

        # 3. Hypothesis IDs unique
        hyp_ids = [h["id"] for h in hypotheses]
        dupes = [hid for hid in hyp_ids if hyp_ids.count(hid) > 1]
        if dupes:
            errors.append(f"Model {sid}: duplicate hypothesis IDs: {list(set(dupes))}")
        else:
            print(f"  OK: model {sid} has {len(hypotheses)} unique hypotheses")

        # 4. All ability IDs exist in ability_nodes.json
        for action in actions:
            for aid in action.get("related_abilities", []):
                if aid not in ability_by_id:
                    errors.append(f"Model {sid}, action {action['id']}: ability_id '{aid}' not in ability_nodes.json")
        for hyp in hypotheses:
            for aid in hyp.get("related_abilities", []):
                if aid not in ability_by_id:
                    errors.append(f"Model {sid}, hypothesis {hyp['id']}: ability_id '{aid}' not in ability_nodes.json")
        for bias_id, bias_def in strategy_biases.items():
            for aid in bias_def.get("related_abilities", []):
                if aid not in ability_by_id:
                    errors.append(f"Model {sid}, bias {bias_id}: ability_id '{aid}' not in ability_nodes.json")
        print(f"  OK: model {sid} ability references valid")

        # 6. Action-referenced hypotheses exist
        for action in actions:
            required_hyp = action.get("requires_hypothesis")
            if required_hyp and required_hyp not in hyp_ids:
                errors.append(f"Model {sid}, action {action['id']}: references unknown hypothesis '{required_hyp}'")

        # 7. Completion requirements format
        completion = model.get("completion_requirements", {})
        if not isinstance(completion, dict):
            errors.append(f"Model {sid}: completion_requirements is not a dict")
        else:
            required_state = completion.get("required_state", {})
            required_actions = completion.get("required_actions", [])
            closure_action = completion.get("closure_action")
            if not isinstance(required_state, dict):
                errors.append(f"Model {sid}: required_state is not a dict")
            if not isinstance(required_actions, list):
                errors.append(f"Model {sid}: required_actions is not a list")
            for ra in required_actions:
                if ra not in action_ids:
                    errors.append(f"Model {sid}: required_action '{ra}' not in diagnostic_actions")
            if closure_action and closure_action not in action_ids:
                errors.append(f"Model {sid}: closure_action '{closure_action}' not in diagnostic_actions")
        print(f"  OK: model {sid} completion requirements valid")

    if errors:
        print(f"\nFAIL: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"\nPASS: all {len(models)} models validated")

    # Bonus: map old scenario steps to model actions (information only)
    print("\n--- Old-to-new mapping (informational) ---")
    for scenario in scenarios:
        sid = scenario.get("id")
        model = models.get(sid)
        if not model:
            continue
        actions = {a["id"]: a for a in model.get("diagnostic_actions", [])}
        print(f"\n  Scenario: {scenario.get('title')} ({sid})")
        for step in scenario.get("steps", []):
            print(f"    Step {step['id']}: '{step['prompt']}'")
            for opt in step.get("options", []):
                matched_action = None
                for aid, action in actions.items():
                    if opt.get("text", "").startswith(action.get("label", "")[:8]):
                        matched_action = aid
                        break
                status = f" -> action: {matched_action}" if matched_action else " (no direct action match)"
                print(f"      Option {opt['id']}: {'CORRECT' if opt.get('is_correct') else 'wrong'}{status}")


if __name__ == "__main__":
    main()
