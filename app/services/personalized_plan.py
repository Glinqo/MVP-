from .data_loader import load_data, primary_job_profile
from .graph import build_student_ability_graph
from .graph_update_engine import normalize_ability_id
from .learner_context import learner_context_pack
from .safety import safety_notice


PRIORITY_STATUS = {"weak": 0, "improving": 1, "recommended_next": 2, "touched": 3, "unknown": 4, "mastered": 5}


def resource_matches(resource, ability_id, knowledge_ids):
    ability_ids = set(resource.get("ability_ids", []) + resource.get("node_ids", []))
    resource_knowledge = set(resource.get("knowledge_ids", []))
    return ability_id in ability_ids or bool(resource_knowledge.intersection(knowledge_ids))


def knowledge_for_ability(ability_id, limit=3):
    data = load_data()
    ability = data["ability_by_id"].get(ability_id, {})
    knowledge_ids = list(ability.get("related_knowledge", []))
    items = []
    seen = set()
    for knowledge_id in knowledge_ids:
        item = data["knowledge_by_id"].get(knowledge_id)
        if item and knowledge_id not in seen:
            items.append(item)
            seen.add(knowledge_id)
    for item in data["knowledge"]:
        if item.get("ability_node_id") == ability_id and item.get("id") not in seen:
            items.append(item)
            seen.add(item.get("id"))
    return items[:limit]


def tasks_for_ability(ability_id, limit=2):
    tasks = []
    for task in load_data()["tasks"]:
        if ability_id in task.get("node_ids", []):
            tasks.append(
                {
                    "id": task.get("id"),
                    "title": task.get("title"),
                    "difficulty": task.get("difficulty"),
                    "estimated_minutes": task.get("estimated_minutes"),
                    "deliverable": task.get("deliverable"),
                    "source": task.get("source"),
                }
            )
    return tasks[:limit]


def resources_for_ability(ability_id, knowledge_ids):
    video_resources = []
    text_resources = []
    for resource in load_data()["resources"]:
        if not resource_matches(resource, ability_id, knowledge_ids):
            continue
        compact = {
            "id": resource.get("id"),
            "title": resource.get("title"),
            "type": resource.get("type"),
            "url": resource.get("url"),
            "use_when": resource.get("use_when"),
            "source": resource.get("source"),
        }
        if resource.get("type") == "video":
            video_resources.append(compact)
        else:
            text_resources.append(compact)
    return text_resources[:3], video_resources[:3]


def checkpoint_questions(ability_id, limit=2):
    questions = []
    for question in load_data()["questions_data"].get("questions", []):
        q_ability = normalize_ability_id(question.get("ability_id"))
        if q_ability != ability_id:
            continue
        questions.append(
            {
                "id": question.get("id"),
                "type": question.get("type"),
                "question": question.get("question"),
                "ability_id": ability_id,
                "source": question.get("source"),
            }
        )
    return questions[:limit]


def plan_stage(ability_node, index):
    ability_id = ability_node.get("id")
    ability = load_data()["ability_by_id"].get(ability_id, {})
    knowledge_items = knowledge_for_ability(ability_id)
    knowledge_ids = [item.get("id") for item in knowledge_items if item.get("id")]
    text_resources, video_resources = resources_for_ability(ability_id, knowledge_ids)
    tasks = tasks_for_ability(ability_id)
    first_knowledge = knowledge_items[0] if knowledge_items else {}
    text_explanation = (
        f"{ability.get('name', ability_id)}：{ability.get('description', '')}"
        f" 建议先补“{first_knowledge.get('topic', '基础概念')}”。{first_knowledge.get('content', '')}"
    ).strip()
    return {
        "stage_id": f"stage_{index:02d}",
        "stage_title": f"第 {index} 阶段：补强{ability.get('name', ability_id)}",
        "ability_id": ability_id,
        "ability_name": ability.get("name", ability_id),
        "status": ability_node.get("status"),
        "mastery_score": ability_node.get("mastery_score"),
        "confidence": ability_node.get("confidence"),
        "why_now": ability_node.get("update_reasons", [])[:3] or ["岗位能力链中需要补齐该能力"],
        "knowledge_cards": [
            {
                "id": item.get("id"),
                "topic": item.get("topic"),
                "content": item.get("content"),
                "source": item.get("source"),
            }
            for item in knowledge_items
        ],
        "text_explanation": text_explanation,
        "video_resources": video_resources,
        "video_note": "暂无视频资源" if not video_resources else "",
        "resource_links": text_resources,
        "practice_tasks": tasks,
        "checkpoint_questions": checkpoint_questions(ability_id),
    }


def stage_minutes(stage, default=25):
    task_minutes = [
        task.get("estimated_minutes")
        for task in stage.get("practice_tasks", [])
        if isinstance(task.get("estimated_minutes"), int)
    ]
    return min(45, max(default, sum(task_minutes) if task_minutes else default))


def build_today_training_sheet(stages, context_pack):
    primary = stages[0] if stages else {}
    secondary = stages[1] if len(stages) > 1 else {}
    primary_task = (primary.get("practice_tasks") or [{}])[0]
    checkpoints = (primary.get("checkpoint_questions") or [])[:2]
    if secondary.get("checkpoint_questions"):
        checkpoints.extend(secondary.get("checkpoint_questions", [])[:1])

    steps = [
        {
            "step_id": "T01",
            "title": "安全口令与现象复述",
            "minutes": 5,
            "action": "先说清设备是否断电、急停/气源状态，再用一句话复述现场现象。",
            "deliverable": "写下“传感器灯/PLC 输入灯/在线监控”三联状态。",
            "source": "project_curated",
        },
        {
            "step_id": "T02",
            "title": "补关键知识卡",
            "minutes": 10,
            "action": f"阅读并复述：{primary.get('ability_name', '当前薄弱能力')}相关知识卡。",
            "deliverable": "能解释一个关键判断：为什么公共端、输出类型或 I/O 地址会影响输入信号。",
            "source": "knowledge_50 + student_graph",
        },
        {
            "step_id": "T03",
            "title": "完成小实训",
            "minutes": stage_minutes(primary),
            "action": primary_task.get("title") or "完成当前能力节点的关联训练任务。",
            "deliverable": primary_task.get("deliverable") or "提交排查顺序、判断依据和结果记录。",
            "source": primary_task.get("source") or "training_tasks",
        },
        {
            "step_id": "T04",
            "title": "检查点复测",
            "minutes": 8,
            "action": "用检查题或口头复述验证是否真的会判断，而不是只记住答案。",
            "deliverable": "标记：已掌握 / 仍不会 / 需要更基础讲解。",
            "source": "diagnostic_questions + feedback",
        },
    ]
    return {
        "title": "今日训练单",
        "objective": primary.get("stage_title", "建立一次个人图谱证据并完成一个补强训练"),
        "estimated_minutes": sum(step["minutes"] for step in steps),
        "learner_snapshot": context_pack.get("summary"),
        "target_abilities": [
            item.get("ability_name")
            for item in [primary, secondary]
            if item.get("ability_name")
        ],
        "steps": steps,
        "checkpoint_questions": checkpoints,
        "safety_notice": safety_notice("接线 调试 PLC 传感器"),
        "source": "student_graph + knowledge_50 + training_tasks",
    }


def build_seven_day_plan(stages):
    if not stages:
        stages = [
            {
                "ability_id": "electrical_safety_check",
                "ability_name": "电气安全检查",
                "knowledge_cards": [],
                "practice_tasks": [],
                "checkpoint_questions": [],
            }
        ]
    templates = [
        ("建立安全口令和现场证据表", "安全检查 + 三联状态记录", "产生一次问答命中证据"),
        ("补知识卡并画接线判断表", "概念解释 + 接线关系", "薄弱节点从 weak 进入 improving"),
        ("完成一次接线/公共端判断训练", "小实训任务", "提交任务完成证据"),
        ("做一次错题讲解和追问", "讲题 + 追问", "讲解事件写入个人图谱"),
        ("进入排故角色扮演", "场景判断", "至少完成一个正确步骤"),
        ("做预设自测或个性化练习", "复测验证", "更新确定性评分证据"),
        ("复盘并生成下一轮训练单", "反馈闭环", "记录已掌握/仍不会反馈"),
    ]
    plan = []
    for index, (title, focus, graph_goal) in enumerate(templates):
        stage = stages[min(index // 2, len(stages) - 1)]
        knowledge_topics = [item.get("topic") for item in stage.get("knowledge_cards", []) if item.get("topic")]
        task = (stage.get("practice_tasks") or [{}])[0]
        checkpoint = (stage.get("checkpoint_questions") or [{}])[0]
        plan.append(
            {
                "day": index + 1,
                "title": title,
                "focus": focus,
                "ability_id": stage.get("ability_id"),
                "ability_name": stage.get("ability_name"),
                "knowledge_topics": knowledge_topics[:3],
                "task": {
                    "id": task.get("id"),
                    "title": task.get("title") or "暂无匹配任务，使用今日训练单的现场证据记录任务",
                    "deliverable": task.get("deliverable") or "提交学习记录和排查依据",
                    "source": task.get("source", "training_tasks"),
                },
                "checkpoint": {
                    "id": checkpoint.get("id"),
                    "question": checkpoint.get("question") or "用自己的话说明今天训练的判断依据。",
                    "source": checkpoint.get("source", "diagnostic_questions"),
                },
                "graph_update_goal": graph_goal,
                "source": "student_graph + personalized_plan_template",
            }
        )
    return plan


def prioritize_requested_node(nodes, requested_ability_id):
    if not requested_ability_id:
        return nodes
    requested_ability_id = normalize_ability_id(requested_ability_id)
    requested = [node for node in nodes if node.get("id") == requested_ability_id]
    rest = [node for node in nodes if node.get("id") != requested_ability_id]
    return requested + rest


def personalized_plan(payload=None):
    payload = payload or {}
    session_id = payload.get("session_id")
    plan_mode = payload.get("plan_mode", "staged")
    requested_ability_id = payload.get("ability_id")
    graph = build_student_ability_graph(session_id)
    context_pack = learner_context_pack(graph.get("session_id"))
    nodes = graph.get("nodes", [])
    sorted_nodes = sorted(
        nodes,
        key=lambda node: (
            PRIORITY_STATUS.get(node.get("status"), 9),
            node.get("mastery_score", 30),
            -node.get("evidence_count", 0),
        ),
    )
    sorted_nodes = prioritize_requested_node(sorted_nodes, requested_ability_id)
    priority_nodes = [node for node in sorted_nodes if node.get("status") != "mastered"][:5]
    if not priority_nodes:
        priority_nodes = sorted_nodes[:3]

    stages = [plan_stage(node, index + 1) for index, node in enumerate(priority_nodes[:5])]
    weak_names = [stage["ability_name"] for stage in stages[:3]]
    today_sheet = build_today_training_sheet(stages, context_pack)
    seven_day_plan = build_seven_day_plan(stages)
    return {
        "session_id": graph.get("session_id"),
        "plan_mode": plan_mode,
        "job_profile": primary_job_profile(),
        "learner_context": context_pack,
        "student_summary": (
            "当前优先补强：" + "、".join(weak_names)
            if weak_names
            else "当前缺少足够学习证据，建议先完成一次问答或自测。"
        ),
        "priority_abilities": [
            {
                "ability_id": stage["ability_id"],
                "ability_name": stage["ability_name"],
                "status": stage["status"],
                "mastery_score": stage["mastery_score"],
                "confidence": stage["confidence"],
            }
            for stage in stages
        ],
        "learning_plan": stages,
        "today_training_sheet": today_sheet,
        "seven_day_plan": seven_day_plan,
        "safety_notice": safety_notice("接线 调试 PLC 传感器"),
        "next_review": "完成推荐实训任务后，重新做预设自测，并把不会的题目用于追问讲解。",
        "source": "student_graph + knowledge_50 + resources + training_tasks",
    }
