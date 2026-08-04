import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.scenario import scenario_by_id, start_scenario, step_scenario, list_scenarios

SCENARIO_ID = "SCN_SENSOR_LED_ON_PLC_LED_OFF"



def collect_strings(value):
    """Recursively collect all strings from a nested dict/list."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(collect_strings(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(collect_strings(item))
        return result
    return []

class ScenarioTests:
    """Tests for scenario demo phase 1 - 3-stage teaching flow."""

    def setup_method(self):
        pass

    # === Scenario Loading ===

    def test_scenario_loads_by_id(self):
        s = scenario_by_id(SCENARIO_ID)
        assert s["id"] == SCENARIO_ID
        assert len(s["steps"]) == 3

    def test_scenario_steps_have_display_fields(self):
        s = scenario_by_id(SCENARIO_ID)
        for step in s["steps"]:
            assert "progress" in step
            assert step["progress"]["total"] == 3
            assert "scene_status" in step
            assert "evidence" in step
            assert "hint" in step and step["hint"] is not None
            for opt in step["options"]:
                assert "description" in opt
                assert "feedback_type" in opt
                assert opt["feedback_type"] in ("correct", "premature", "inefficient", "unsafe", "closure_missing", "incorrect")

    def test_scenario_has_summary(self):
        s = scenario_by_id(SCENARIO_ID)
        assert "summary" in s
        assert isinstance(s["summary"]["root_cause"], str) and len(s["summary"]["root_cause"]) > 0
        assert "verified_state" in s["summary"]
        assert s["summary"]["verified_state"]["online_value"] == 1
        assert len(s["summary"]["completed_items"]) == 4
        assert len(s["summary"]["ability_labels"]) == 3

    # === Start Scenario ===

    def test_start_returns_first_stage(self):
        result = start_scenario({"scenario_id": SCENARIO_ID})
        cs = result["current_step"]
        assert result["status"] == "in_progress"
        assert cs["progress"] == {"current": 1, "total": 3}
        assert len(cs["scene_status"]) == 5
        assert len(cs["evidence"]) == 2
        assert cs["hint"] is not None
        assert len(cs["options"]) == 3

    def test_start_returns_option_descriptions(self):
        result = start_scenario({"scenario_id": SCENARIO_ID})
        for opt in result["current_step"]["options"]:
            assert "description" in opt
            assert "feedback_type" in opt

    # === Wrong Operations ===

    def test_wrong_premature(self):
        result = step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S1", "choice_id": "B"})
        assert result["is_correct"] is False
        assert result["feedback_type"] == "premature"
        assert result["progress"]["current"] == 1
        assert result["completed"] is False
        assert result["current_step"]["id"] == "S1"

    def test_wrong_inefficient(self):
        result = step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S1", "choice_id": "C"})
        assert result["is_correct"] is False
        assert result["feedback_type"] == "inefficient"
        assert result["progress"]["current"] == 1
        assert result["completed"] is False
        assert result["current_step"]["id"] == "S1"

    # === Correct Progression ===

    def test_correct_s1_advances_to_s2(self):
        result = step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S1", "choice_id": "A"})
        assert result["is_correct"] is True
        assert result["feedback_type"] == "correct"
        assert result["progress"]["current"] == 1
        assert result["completed"] is False
        assert result["current_step"]["id"] == "S2"
        assert result["current_step"]["progress"] == {"current": 2, "total": 3}
        assert len(result["current_step"]["evidence"]) == 4

    def test_correct_s2_advances_to_s3(self):
        step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S1", "choice_id": "A"})
        result = step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S2", "choice_id": "A"})
        assert result["is_correct"] is True
        assert result["current_step"]["id"] == "S3"
        assert result["current_step"]["progress"] == {"current": 3, "total": 3}

    # === Safe Completion ===

    def test_correct_s3_completes_scenario(self):
        step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S1", "choice_id": "A"})
        step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S2", "choice_id": "A"})
        result = step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S3", "choice_id": "A"})
        assert result["is_correct"] is True
        assert result["completed"] is True
        assert result["status"] == "completed"
        assert result["summary"] is not None
        assert isinstance(result["summary"]["root_cause"], str)
        assert result["summary"]["verified_state"]["online_value"] == 1
        assert len(result["summary"]["completed_items"]) == 4
        assert len(result["summary"]["ability_labels"]) == 3

    # === Unsafe Operation ===

    def test_unsafe_blocked(self):
        step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S1", "choice_id": "A"})
        step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S2", "choice_id": "A"})
        result = step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S3", "choice_id": "C"})
        assert result["is_correct"] is False
        assert result["feedback_type"] == "unsafe"
        assert result["completed"] is False
        assert result["current_step"]["id"] == "S3"

    # === Closure Missing ===

    def test_closure_missing(self):
        step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S1", "choice_id": "A"})
        step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S2", "choice_id": "A"})
        result = step_scenario({"scenario_id": SCENARIO_ID, "step_id": "S3", "choice_id": "B"
    def test_scenario_text_is_not_corrupted(self):
        """Verify no corruption in scenario Chinese text."""
        scenario = scenario_by_id(SCENARIO_ID)
        strings = collect_strings(scenario)
        combined = "\n".join(strings)

        assert "??" not in combined
        assert "\ufffd" not in combined
        assert scenario["title"] == "\u4f20\u611f\u5668\u52a8\u4f5c\u706f\u4eae\uff0c\u4f46 PLC \u8f93\u5165\u706f\u4e0d\u4eae"
        assert "\u5224\u65ad\u6545\u969c\u8303\u56f4" in str(scenario["summary"]["completed_items"])
        assert "\u8f93\u5165\u516c\u5171\u7aef" in combined
        assert "\u4e09\u8054\u72b6\u6001\u9a8c\u8bc1" in combined

    def test_scenario_contains_sufficient_chinese_text(self):
        """Verify enough CJK characters to confirm text is not corrupted."""
        import re
        scenario = scenario_by_id(SCENARIO_ID)
        combined = "\n".join(collect_strings(scenario))
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", combined)
        assert len(chinese_chars) >= 150

    def test_scenario_action_cards_keep_keyboard_support(self):
        """Verify keyboard accessibility in app.js for action cards."""
        from pathlib import Path
        app_js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        assert "role=\"button\"" in app_js
        assert "tabindex=\"0\"" in app_js
        assert "aria-pressed" in app_js
        assert "event.key === \"Enter\"" in app_js
        assert "event.key === \" \"" in app_js

})
        assert result["is_correct"] is False
        assert result["feedback_type"] == "closure_missing"
        assert result["completed"] is False
        assert result["current_step"]["id"] == "S3"

    # === Scenario List ===

    def test_scenario_in_list(self):
        result = list_scenarios()
        assert "scenarios" in result
        ids = [s["id"] for s in result["scenarios"]]
        assert SCENARIO_ID in ids

    # === Smoke Test Compatibility ===

    def test_smoke_compat_step_ids(self):
        s = scenario_by_id(SCENARIO_ID)
        step_ids = [step["id"] for step in s["steps"]]
        assert "S1" in step_ids

    def test_smoke_compat_option_ids(self):
        s = scenario_by_id(SCENARIO_ID)
        s1 = s["steps"][0]
        option_ids = [opt["id"] for opt in s1["options"]]
        assert "A" in option_ids
        assert "B" in option_ids
        assert "C" in option_ids

    def test_smoke_compat_option_a_correct(self):
        s = scenario_by_id(SCENARIO_ID)
        s1 = s["steps"][0]
        for opt in s1["options"]:
            if opt["id"] == "A":
                assert opt["is_correct"] is True
            if opt["id"] == "B":
                assert opt["is_correct"] is False
