path = r'C:/Users/17578/Desktop/MVP-/app/services/chat.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# Fix 1: welcome_questions to accept job_role
idx = c.find('def welcome_questions():')
end = c.index('\ndef chat_start', idx)
new_wq = '''def welcome_questions(job_role=None):
    from .retrieval import search_knowledge
    from .data_loader import job_profile_by_id, primary_job_profile
    profile = job_profile_by_id(job_role) if job_role else primary_job_profile()
    job_name = profile.get("role_name", "当前岗位")
    abilities = profile.get("core_abilities", [])[:3]
    questions = [
        f"{job_name}岗位的核心安全规范有哪些？",
        "我该如何理解本岗位的技术图纸和工艺文件？",
    ]
    if abilities:
        questions.append(f"{job_name}岗位中{abilities[0]}需要掌握哪些知识？")
    return questions[:3]
'''
c = c[:idx] + new_wq + c[end:]

# Fix 2: call welcome_questions with job_role
c = c.replace('"suggested_questions": welcome_questions(),', '"suggested_questions": welcome_questions(job_role),')

# Fix 3: suggested_questions_from_assist with job_role
idx2 = c.find('def suggested_questions_from_assist(assist_result):')
end2 = c.index('\n\ndef tool_suggestions_from_assist', idx2)
new_sa = '''def suggested_questions_from_assist(assist_result, job_role=None):
    if assist_result.get("status") == "need_clarification":
        return [item.get("question") for item in assist_result.get("clarifying_questions", []) if item.get("question")][:3]
    ability_questions = []
    for ability in assist_result.get("highlighted_abilities", [])[:3]:
        name = ability.get("name") or ability.get("id")
        ability_questions.append(f"我该怎么补上\u201c{name}\u201d？")
    base = [
        "这个问题最可能出在哪里？",
        "我下一步实训应该做哪个任务？",
    ]
    return (ability_questions + base)[:4]
'''
c = c[:idx2] + new_sa + c[end2:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print('chat.py updated')