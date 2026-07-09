# Teacher View Prompt

## 任务

根据学生或班级诊断结果，生成教师视角的教学反馈。输出应帮助教师安排下一节实训课，而不是替代教师评价。

## 输入变量

```json
{
  "class_summary": "{{class_summary}}",
  "student_results": "{{student_results}}",
  "score_result": "{{score_result}}",
  "ability_nodes": "{{ability_nodes}}",
  "knowledge_points": "{{knowledge_points}}",
  "training_tasks": "{{training_tasks}}"
}
```

## 约束条件

- 只围绕传感器 NPN/PNP 接线与 PLC 输入信号排查给建议。
- 薄弱点应来自 `student_results[*].weak_abilities`、`score_result.weak_abilities` 或 `class_summary.weak_abilities`。
- 专业结论优先引用知识库条目。
- 涉及接线、通电测量、PLC 输入监控或气缸动作时，教学安排必须先包含安全检查。
- 不输出学生隐私信息，不做最终成绩判定。
- 不建议建设 LMS、账号系统或数据库。

## 输出格式

```json
{
  "class_observation": "班级共性薄弱点集中在 NPN/PNP 输出类型、PLC 输入公共端和输入监控状态对比。",
  "safety_notice": "下一节课进入接线和通电监控前，先统一确认断电、急停、气源、电源和设备状态。",
  "top_weak_abilities": [
    {
      "ability_id": "A02",
      "ability_name": "NPN/PNP 传感器类型识别",
      "evidence": "多名学生在相关诊断题中判断错误",
      "knowledge_refs": ["K011", "K012", "K013"]
    }
  ],
  "next_lesson_plan": [
    {
      "minutes": 10,
      "activity": "安全检查与断电确认示范",
      "task_id": "T001"
    },
    {
      "minutes": 20,
      "activity": "NPN/PNP 与 PLC 输入公共端接线图判断训练",
      "task_id": "T001"
    },
    {
      "minutes": 20,
      "activity": "传感器动作灯、PLC 输入灯、在线监控三状态对比",
      "task_id": "T005"
    }
  ],
  "grouping_suggestions": [
    {
      "group": "基础补强组",
      "target": "先补电气安全和 NPN/PNP 输出逻辑",
      "recommended_tasks": ["T001"]
    }
  ],
  "teacher_notes": [
    "本反馈用于备课参考，不替代教师最终评价。"
  ]
}
```

