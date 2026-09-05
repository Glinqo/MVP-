# -*- coding: utf-8 -*-
"""Phase 5: Response Experience Optimization tests."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.response_composer import compose_response, _detect_response_mode
from app.services.safety import get_safety_level, safety_notice

PASS, FAIL = 0, 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS: " + name)
    else:
        FAIL += 1
        print("  FAIL: " + name + "  " + detail)

# 1. compose_response basic structure
print("1. compose_response structure")
r = compose_response("PLC input light off?", [], None, None)
check("has answer", "answer" in r)
check("answer is string", isinstance(r["answer"], str))
check("has _debug", "_debug" in r)
check("_debug has mode", "mode" in r["_debug"])

# 2. mode detection
print("\n2. mode detection")
class Mock:
    def to_dict(self):
        return {"tool": "get_ability_detail", "tool_name": "get_ability_detail"}
    def get(self, key, default=None):
        return {"tool": "get_ability_detail", "tool_name": "get_ability_detail"}.get(key, default)
    tool_name = "get_ability_detail"
mocks = [Mock()]
m = _detect_response_mode("what is plc", mocks, None)
check("mode detected", m is not None and len(m) > 0, "got: " + str(m))

# 3. safety levels
print("\n3. safety levels")
check("normal text is none", get_safety_level("how does plc work") == "none")
check("wiring triggers warning", get_safety_level("i will rewire the plc while power is on") == "warning")
check("safety_notice with context returns string", isinstance(safety_notice("rewire while power on"), str))

# 4. compose with safety
print("\n4. compose with safety")
r2 = compose_response("i will bypass the safety circuit", [], None, None)
check("has safety block", "safety" in r2)
if "safety" in r2:
    check("safety level not none", r2["safety"].get("level", "none") != "none")

# 5. empty tool_results
print("\n5. empty tool_results")
r4 = compose_response("hello", [], None, None)
check("empty tools gives answer", isinstance(r4["answer"], str) and len(r4["answer"]) > 0)
check("_debug mode present", "_debug" in r4 and "mode" in r4["_debug"])

# Summary
print("\nResults: " + str(PASS) + " passed, " + str(FAIL) + " failed")
if FAIL:
    sys.exit(1)
