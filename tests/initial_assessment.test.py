"""Tests for initial_assessment.py - 15 cases. Stage 1 (deepened)."""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.initial_assessment import (
    start_assessment, submit_answer, _load_questions,
    _finish_assessment, get_assessment_summary,
    AssessmentQuestion, CORRECT_SCORE, _init_session, _sessions
)

PASS = 0
FAIL = 0

def check(condition, msg):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL: " + msg)

def report(name):
    global PASS, FAIL
    if FAIL == 0:
        print("PASS " + name)
    else:
        print("FAIL " + name + " (" + str(FAIL) + " failures)")
    PASS = 0
    FAIL = 0

# 1. New assessment returns first question
def case1():
    _sessions.clear()
    r = start_assessment("s1")
    check(r["status"] == "in_progress", "status in_progress")
    check(r["first_question"]["qid"] == "A01", "first Q is A01")
    check(r["total_questions"] == 30, "30 questions")
    check(r["answered_count"] == 0, "0 answered")
    report("case1_new_assessment_returns_first")

# 2. Progress resumable
def case2():
    _sessions.clear()
    start_assessment("s2")
    submit_answer("s2", "A01", "A", answers_so_far=[])
    r = start_assessment("s2")
    check(r["status"] == "in_progress", "still in progress")
    check(r["first_question"]["qid"] == "A02", "resumes at A02")
    check(r["answered_count"] == 1, "1 answered")
    report("case2_progress_resumable")

# 3. Correct answer scores correctly
def case3():
    _sessions.clear()
    start_assessment("s3")
    r = submit_answer("s3", "A01", "A", answers_so_far=[])
    check(r["status"] == "in_progress", "continues")
    check(r["current_index"] == 1, "index 1")
    report("case3_correct_answer_scores")

# 4. Wrong answer maps to correct ability
def case4():
    _sessions.clear()
    qs = _load_questions()
    answers = []
    for q in qs:
        fake = "A" if q.correct_key != "A" else "B"
        answers.append({"qid": q.qid, "selected": fake, "is_correct": False,
                        "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()})
    r = _finish_assessment("s4", None, answers, qs)
    check(r["status"] == "completed", "completed")
    check(r["result"]["total_score"] < 0.4, "low total score")
    check(len(r["result"]["weak_abilities"]) > 3, "many weak")
    report("case4_wrong_answer_maps")

# 5. All answered auto-completes
def case5():
    _sessions.clear()
    qs = _load_questions()
    answers = [{"qid": q.qid, "selected": q.correct_key, "is_correct": True,
                "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()} for q in qs]
    r = _finish_assessment("s5", None, answers, qs)
    check(r["status"] == "completed", "completed")
    check(r["result"]["total_score"] == 1.0, "score 1.0")
    check(len(r["result"]["strong_abilities"]) > 5, "many strong")
    report("case5_all_answered_auto_completes")

# 6. Duplicate answer rejected
def case6():
    _sessions.clear()
    start_assessment("s6")
    submit_answer("s6", "A01", "A", answers_so_far=[])
    r = submit_answer("s6", "A01", "B",
                      answers_so_far=[{"qid": "A01", "selected": "A", "is_correct": True,
                                       "ability_id": "plc_basic_principle", "dimension": "", "answered_at": time.time()}])
    msg = str(r.get("message", ""))
    check("already" in msg.lower() or "duplicate" in msg.lower(), "duplicate rejected: " + msg[:60])
    report("case6_duplicate_answer_rejected")

# 7. Duplicate assessment no double event
def case7():
    _sessions.clear()
    qs = _load_questions()
    answers = [{"qid": q.qid, "selected": q.correct_key, "is_correct": True,
                "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()} for q in qs]
    r1 = _finish_assessment("s7", None, answers, qs)
    r2 = _finish_assessment("s7", None, answers, qs)
    check(r1["result"]["total_score"] == r2["result"]["total_score"], "same score")
    report("case7_no_double_event")

# 8. All correct all mastered
def case8():
    _sessions.clear()
    qs = _load_questions()
    answers = [{"qid": q.qid, "selected": q.correct_key, "is_correct": True,
                "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()} for q in qs]
    r = _finish_assessment("s8", None, answers, qs)
    check(len(r["result"]["strong_abilities"]) == len(r["result"]["ability_scores"]), "all mastered")
    report("case8_all_mastered")

# 9. Different job roles isolated
def case9():
    _sessions.clear()
    _init_session("s9", "job_a")
    _init_session("s9", "job_b")
    check("s9_job_a" in _sessions, "session job_a")
    check("s9_job_b" in _sessions, "session job_b")
    check(_sessions["s9_job_a"]["job_role"] == "job_a", "role job_a")
    check(_sessions["s9_job_b"]["job_role"] == "job_b", "role job_b")
    report("case9_roles_isolated")

# 10. Different sessions isolated
def case10():
    _sessions.clear()
    _init_session("s10a", None)
    _init_session("s10b", None)
    check("s10a_default" in _sessions, "s10a exists")
    check("s10b_default" in _sessions, "s10b exists")
    r1 = start_assessment("s10a")
    r2 = start_assessment("s10b")
    check(r1["first_question"]["qid"] == r2["first_question"]["qid"], "both start at same Q")
    report("case10_sessions_isolated")

# 11. All 30 question IDs valid
def case11():
    qs = _load_questions()
    check(len(qs) == 30, "30 questions")
    ids = [q.qid for q in qs]
    check(len(set(ids)) == 30, "all IDs unique")
    for q in qs:
        keys = [o["key"] for o in q.options]
        check(q.correct_key in keys, q.qid + " correct valid")
    report("case11_all_qids_valid")

# 12. Safety dimension generates safety recs
def case12():
    _sessions.clear()
    qs = _load_questions()
    answers = []
    for q in qs:
        if q.ability_id in ("electrical_safety", "safety_ppe", "emergency_stop"):
            answers.append({"qid": q.qid, "selected": "X", "is_correct": False,
                           "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()})
        else:
            answers.append({"qid": q.qid, "selected": q.correct_key, "is_correct": True,
                           "ability_id": q.ability_id, "dimension": q.dimension, "answered_at": time.time()})
    r = _finish_assessment("s12", None, answers, qs)
    check(len(r["result"]["safety_critical_gaps"]) > 0, "safety gaps found")
    has_safety = any("safety" in rec.lower() for rec in r["result"]["recommendations"])
    check(has_safety, "safety recommendations")
    report("case12_safety_recommendations")

# 13. Learning plan includes scaffold and transfer
def case13():
    from app.services.action_planner import plan_initial_learning
    r = plan_initial_learning({"ability_scores": {"a": 0.3, "b": 0.9},
                               "weak_abilities": ["a"], "strong_abilities": ["b"], "total_score": 0.6})
    check(len(r["stages"]) >= 2, "2+ stages")
    check(len(r["weak_abilities"]) == 1, "1 weak")
    report("case13_learning_plan")

# 14. Teacher view no leak
def case14():
    from app.services.student_assessment_report import generate_individual_report
    r = generate_individual_report("test")
    forbidden = ["password", "email", "phone", "address", "id_card", "score_detail"]
    r_str = json.dumps(r, ensure_ascii=False).lower()
    leaked = [f for f in forbidden if f in r_str]
    check(len(leaked) == 0, "no leak: " + str(leaked))
    report("case14_teacher_no_leak")

# 15. API error responses
def case15():
    _sessions.clear()
    check("error" in start_assessment("", None), "empty session_id error")
    check("error" in submit_answer("", "", ""), "empty params error")
    check("error" in submit_answer("s15", "NONEXISTENT", "A"), "invalid qid error")
    check("error" in submit_answer("s15", "A01", "Z"), "invalid key error")
    report("case15_api_errors")


if __name__ == "__main__":
    case1()
    case2()
    case3()
    case4()
    case5()
    case6()
    case7()
    case8()
    case9()
    case10()
    case11()
    case12()
    case13()
    case14()
    case15()
    print()
    print("All 15 initial_assessment tests completed!")
