# -*- coding: utf-8 -*-
"""Diagnosis Progress Policy - Phase 8."""
from .data_loader import load_data

def get_candidate_causes(pattern_id, context):
    data = load_data()
    patterns = data.get("problem_patterns", [])
    pattern = None
    for p in patterns:
        if p.get("id") == pattern_id:
            pattern = p
            break
    if not pattern:
        return []
    candidates = pattern.get("fault_candidates", [])
    result = []
    for i, c in enumerate(candidates):
        if isinstance(c, str):
            cause = {"cause_id": pattern_id + "_c" + str(i), "description": c, "checks": [], "ruled_out": False, "supported": False}
        elif isinstance(c, dict):
            cause = {"cause_id": c.get("id", pattern_id + "_c" + str(i)), "description": c.get("description", ""), "checks": c.get("checks", []), "ruled_out": False, "supported": False}
            for cond in c.get("ruled_out_by", []):
                if str(context.get(cond.get("field",""),"")).lower() == str(cond.get("value","")).lower():
                    cause["ruled_out"] = True
                    break
            for cond in c.get("supported_by", []):
                if str(context.get(cond.get("field",""),"")).lower() == str(cond.get("value","")).lower():
                    cause["supported"] = True
                    break
        else:
            continue
        result.append(cause)
    return result

def get_remaining_causes(candidate_causes):
    return [c for c in candidate_causes if not c.get("ruled_out")]

def init_diagnosis_progress():
    return {"phase":"collecting_info","candidate_causes":[],"checks_done":[],"stalled_count":0,"last_context_snapshot":{}}

def update_diagnosis_progress(progress, pattern_id, context):
    if not progress:
        progress = init_diagnosis_progress()
    progress["candidate_causes"] = get_candidate_causes(pattern_id, context)
    remaining = get_remaining_causes(progress["candidate_causes"])
    if not remaining:
        progress["phase"] = "resolved"
    elif len(remaining) == 1:
        progress["phase"] = "verifying"
    elif any(str(context.get(k,"")).lower() not in ("","unknown") for k in context):
        progress["phase"] = "narrowing"
    else:
        progress["phase"] = "collecting_info"
    prev = progress.get("last_context_snapshot",{})
    new_info = any(str(context.get(k,"")).lower() not in ("","unknown") and str(prev.get(k,"")).lower() in ("","unknown") for k in context)
    if not new_info and prev:
        progress["stalled_count"] = progress.get("stalled_count",0) + 1
    else:
        progress["stalled_count"] = 0
    progress["last_context_snapshot"] = dict(context)
    return progress

def select_next_best_check(pattern_id, context, progress):
    data = load_data()
    patterns = data.get("problem_patterns", [])
    pattern = None
    for p in patterns:
        if p.get("id") == pattern_id:
            pattern = p
            break
    if not pattern:
        return {"action":"escalate","reason":"No pattern found"}
    required = pattern.get("required_context",[])
    for field in required:
        val = str(context.get(field,"")).lower()
        if val in ("","unknown","未确认"):
            for q in pattern.get("clarifying_questions",[]):
                if q.get("field") == field:
                    return {"action":"ask_slot","slot":field,"question":q.get("question",""),"priority":"required_context","reason":"Missing slot: "+field}
    remaining = get_remaining_causes(get_candidate_causes(pattern_id, context))
    if len(remaining) <= 1:
        if remaining:
            desc = str(remaining[0].get("description",""))[:80]
            return {"action":"conclude","cause":remaining[0],"priority":"conclusion","reason":"One cause: "+desc}
        return {"action":"conclude","cause":None,"priority":"no_causes","reason":"All ruled out"}
    first_checks = pattern.get("first_checks", [])
    if first_checks:
        chk = first_checks[0]
        if isinstance(chk, dict):
            return {"action":"perform_check","check":chk,"priority":"next_step","reason":chk.get("description","Check")}
        return {"action":"perform_check","check":{"description":str(chk)},"priority":"next_step","reason":str(chk)}
    return {"action":"escalate","priority":"stalled","reason":"No checks"}

def is_diagnosis_stalled(progress):
    return progress.get("stalled_count",0) >= 2 if progress else False

def diagnosis_progress_summary(progress):
    if not progress:
        return None
    remaining = get_remaining_causes(progress.get("candidate_causes",[]))
    return {"phase":progress.get("phase"),"total_causes":len(progress.get("candidate_causes",[])),"remaining_causes":len(remaining),"stalled_count":progress.get("stalled_count",0),"is_stalled":progress.get("stalled_count",0)>=2}
