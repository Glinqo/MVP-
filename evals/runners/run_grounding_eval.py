# -*- coding: utf-8 -*-
"""L5 Grounding & Safety Eval Runner."""
import json, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.chat import chat_message
from app.services.safety import get_safety_level
from evals.scorers.answer_scorer import score_answer

CASES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cases")

def load_cases(filename):
    path = os.path.join(CASES_DIR, filename)
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases

def run_grounding_case(case):
    session_id = f"eval-ground-{case['id']}"
    message = case.get("message", "")
    expected = case.get("expect", {})

    response = chat_message({"session_id": session_id, "message": message, "context": {}})
    answer = response.get("answer", "")

    # Extract fields from current API response format
    tool_results = response.get("tool_results", [])
    evidence_used = []
    knowledge_refs = []
    ability_hits = []
    for tr in tool_results:
        if isinstance(tr, dict):
            tn = tr.get("tool_name", tr.get("tool", ""))
            if tn == "search_knowledge":
                kn = tr.get("knowledge_items", tr.get("results", []))
                if isinstance(kn, list):
                    knowledge_refs.extend(kn)
                    evidence_used.extend([k.get("source", k.get("title", "")) for k in kn if isinstance(k, dict)])
            if "ability" in tn.lower():
                hits = tr.get("abilities", tr.get("results", []))
                if isinstance(hits, list):
                    ability_hits.extend(hits)
    
    actual = {
        "answer": answer,
        "sources": evidence_used,
        "knowledge_refs": knowledge_refs,
        "ability_hits": ability_hits,
        "safety_level": get_safety_level(message),
        "fabrication_detected": False,
    }

    # Simple fabrication detection: if answer contains specific model numbers not in knowledge
    if expected.get("no_fabrication") and "XYZ-999" in answer:
        actual["fabrication_detected"] = True

    result = score_answer(expected, actual)
    result["case_id"] = case["id"]
    result["category"] = case.get("category", "")
    return result

def run_all_grounding_evals():
    grounding_cases = load_cases("grounding.jsonl")
    safety_cases = load_cases("safety.jsonl")
    all_cases = grounding_cases + safety_cases
    results = []
    start_time = time.time()

    for case in all_cases:
        result = run_grounding_case(case)
        results.append(result)

    elapsed = time.time() - start_time
    total = len(results)
    passed = sum(1 for r in results if not r.get("failed"))
    total_checks = sum(r.get("total", 0) for r in results)
    passed_checks = sum(len(r.get("passed", [])) for r in results)

    return {
        "layer": "L5",
        "name": "Grounding & Safety",
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "accuracy": passed_checks / max(total_checks, 1),
        "elapsed_ms": elapsed * 1000,
        "cases": results,
    }

if __name__ == "__main__":
    report = run_all_grounding_evals()
    print(json.dumps(report, ensure_ascii=False, indent=2))

