# -*- coding: utf-8 -*-
"""AI jiao xue zhu jiao - Stage 5"""

import json, logging, re
from typing import Dict

logger = logging.getLogger(__name__)
DEFAULT_JOB = "automation_line_commissioning_maintenance_newcomer"

# Intent keywords (using unicode escapes to avoid file encoding issues)
INTENTS = [
    ("class_weak_abilities", ["\u6700\u8584\u5f31", "\u8584\u5f31\u80fd\u529b", "\u54ea\u4e9b\u80fd\u529b", "\u80fd\u529b\u6700\u5dee"]),
    ("class_overview", ["\u6574\u4f53\u60c5\u51b5", "\u5168\u73ed", "\u73ed\u7ea7\u60c5\u51b5", "\u73ed\u7ea7\u600e\u4e48\u6837", "\u603b\u4f53\u60c5\u51b5"]),
    ("common_issues", ["\u5171\u6027\u95ee\u9898", "\u5171\u540c\u95ee\u9898", "\u666e\u904d\u95ee\u9898"]),
    ("pending_comments", ["\u5f85\u5ba1\u6838", "\u5f85\u53d1\u5e03", "\u672a\u5ba1\u6838", "\u5ba1\u6838\u8bc4\u8bed"]),
    ("job_proposals", ["\u5f85\u5ba1\u6838.*\u63d0\u6848", "\u5c97\u4f4d.*\u66f4\u65b0", "\u5c97\u4f4d.*\u63d0\u6848"]),
    ("publish_check", ["\u53ef\u4ee5\u53d1\u5e03", "\u53d1\u5e03.*\u8bc4\u8bed"]),
    ("student_lookup", ["\u67e5\u4e00\u4e0b", "\u770b\u4e00\u4e0b", "\u67e5", "\u627e"]),
    ("student_summary", ["\u6700\u8fd1\u600e\u4e48\u6837", "\u5b66\u4e60\u60c5\u51b5", "\u8868\u73b0\u600e\u4e48\u6837"]),
    ("generate_comment", ["\u751f\u6210\u8bc4\u8bed", "\u4e00\u6bb5\u8bc4\u8bed", "\u5199.*\u8bc4\u8bed"]),
]

def _recognize_intent(msg, ctx, ui):
    import sys
    print("AI_INTENT_DEBUG msg=%s len=%d" % (repr(msg[:30]), len(msg)), file=sys.stderr, flush=True)
    for intent, patterns in INTENTS:
        for pat in patterns:
            if re.search(pat, msg):
                return intent
    if "\u8584\u5f31" in msg or "\u80fd\u529b" in msg: return "class_weak_abilities"
    if "\u5171\u6027" in msg: return "common_issues"
    if "\u8bc4\u8bed" in msg or "\u5ba1\u6838" in msg: return "pending_comments"
    if "\u5b66\u751f" in msg or "\u67e5" in msg: return "student_lookup"
    if "\u73ed\u7ea7" in msg or "\u5168\u73ed" in msg: return "class_overview"
    if "\u5c97\u4f4d" in msg or "\u63d0\u6848" in msg: return "job_proposals"
    return "general"

def handle_teacher_message(message, job_role=None, teacher_id="", history=None, ui_context=None, context=None):
    jr = job_role or DEFAULT_JOB
    ui_ctx = ui_context or {}
    conv_ctx = context or {}
    intent = _recognize_intent(message, conv_ctx, ui_ctx)
    result = _dispatch(intent, message, jr, teacher_id, conv_ctx, ui_ctx)
    try:
        from app.services.llm_client import is_configured, chat_completion
        if is_configured() and result.get("answer"):
            p = _polish(result.get("answer",""), intent)
            if p: result["answer"] = p; result["llm_used"] = True
    except Exception: pass
    result["intent"] = intent
    new_ctx = dict(conv_ctx)
    for k in ["last_students","last_ability_id","last_issue_id","last_comment_ids"]:
        v = result.get("context_update",{}).get(k)
        if v is not None: new_ctx[k] = v
    result["context_update"] = new_ctx
    return result

def _dispatch(intent, msg, jr, tid, ctx, ui):
    r = {"answer": "OK", "evidence": [], "data_cards": [], "actions": [], "context_update": {}}
    # V2 Engine available for all intents
    try: from app.services.v2_facade import discover_issues
    except: discover_issues = None
    if intent == "class_overview":
        try: from app.services.class_insights import get_class_overview; ov = get_class_overview(jr); r["answer"] = f"该岗位共有{ov.get('total_students',0)}名有测评记录的学生。" if ov.get("has_data") else "暂无有效测评数据。"
        except: pass
    elif intent == "class_weak_abilities":
        try: from app.services.class_insights import get_class_ability_graph; g = get_class_ability_graph(jr)
        except: g = {"nodes":[]}
        scored = sorted([n for n in g.get("nodes",[]) if n.get("class_stats",{}).get("mean_mastery") is not None], key=lambda n:n["class_stats"]["mean_mastery"])
        if scored:
            top = scored[:3]; names = ", ".join([n.get("label","") or n.get("id","") for n in top])
            r["answer"] = f"最薄弱的三个能力：{names}。"
            r["actions"] = [{"type":"navigate","module":"classInsights","label":"查看平均能力图谱"}]
        else: r["answer"] = "暂无有效能力数据。"
    elif intent == "common_issues":
        try: from app.services.class_insights import get_common_issues; issues = get_common_issues(jr)
        except: issues = []
        r["answer"] = f"共识别{len(issues)}个共性问题。" if issues else "当前未发现明显共性问题。"
    elif intent == "pending_comments":
        try: from app.services.teacher_comments import list_comments; d = list_comments(job_role=jr); s = d.get("stats",{})
        except: s = {}
        r["answer"] = f"草稿{s.get('draft',0)}条，已审核{s.get('reviewed',0)}条。"
        r["actions"] = [{"type":"navigate","module":"teacherComments","label":"教学评语"}]
    elif intent in ("student_lookup", "student_summary"):
        m = re.search(r"(\d{3}|[\u4e00-\u9fff]{2,4})", msg)
        sid = m.group(0) if m else (ctx.get("last_students",[None])[0] if ctx else None)
        if sid:
            try: from app.services.teacher_students import get_teacher_student_detail; d = get_teacher_student_detail(str(sid), jr)
            except: d = {}
            if not d.get("error"):
                w = ", ".join([str(x) for x in (d.get("weak_abilities") or [])[:3]]) or "暂无"
                r["answer"] = f"学生{d.get('nickname','')}（{sid}），状态：{d.get('status','')}。薄弱：{w}。"
                r["actions"] = [{"type":"open_student","student_id":str(sid),"label":"查看详情"}]
                r["context_update"] = {"last_students": [str(sid)]}
    elif intent == "job_proposals":
        try: from scripts.pipeline.evidence_store import get_pending_proposals; p = get_pending_proposals(jr)
        except: p = []
        r["answer"] = f"当前{len(p)}条待审核岗位提案。"
        r["actions"] = [{"type":"navigate","module":"teacherJobGraph","label":"岗位图谱"}]
    else:
        r["answer"] = "我可以帮你：查看班级学情、发现薄弱能力、共性问题、查找学生、生成评语草稿。请问需要了解什么？"
        r["actions"] = [
            {"type":"navigate","module":"classInsights","label":"班级洞察"},
            {"type":"navigate","module":"studentMgmt","label":"学生管理"},
            {"type":"navigate","module":"teacherComments","label":"教学评语"},
        ]
    return r

def _polish(answer, intent):
    try: from app.services.llm_client import chat_completion; return chat_completion([{"role":"user","content":f"润色（<150字）：{answer}"}]).strip()
    except: return ""
