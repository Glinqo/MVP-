# Diagnosis Prompt

## 任务

把代码模块返回的诊断结果解释成学生能理解的反馈。必须使用 `score_result.weak_abilities`，不允许自由编造薄弱能力或重新评分。

## 输入变量

```json
{
  "user_input": "{{user_input}}",
  "score_result": "{{score_result}}",
  "ability_nodes": "{{ability_nodes}}",
  "knowledge_points": "{{knowledge_points}}",
  "diagnostic_questions": "{{diagnostic_questions}}"
}
```

## 约束条件

- `score`、`correct_count`、`total_count`、`feedback_level` 必须原样来自 `score_result`。
- 薄弱点只能来自 `score_result.weak_abilities`。
- 推荐路径只能基于 `score_result.recommended_path` 展开解释。
- 如果 `weak_abilities` 为空，不要编造薄弱点，只给巩固建议。
- 专业解释优先引用 `knowledge_points` 中匹配的知识条目。
- 涉及接线、通电测量、PLC 输入监控或设备动作时，必须先给安全提醒。
- 不替代教师最终评价。

## 输出格式

```json
{
  "summary": "本次诊断得分 75 分，答对 6/8 题，反馈等级为：需要补基础。",
  "safety_notice": "涉及接线、测量或设备调试时，请先断电，确认急停、气源、电源和设备状态；不确定时请教师或实训指导人员确认。",
  "score": 75,
  "correct_count": 6,
  "total_count": 8,
  "feedback_level": "需要补基础",
  "weaknesses": [
    {
      "ability_id": "A02",
      "ability_name": "NPN/PNP 传感器类型识别",
      "reason": "NPN/PNP 输出类型与公共端关系判断错误",
      "knowledge_refs": [
        {"id": "K011", "topic": "NPN 输出基本逻辑"},
        {"id": "K012", "topic": "PNP 输出基本逻辑"}
      ]
    }
  ],
  "recommended_path": [
    "电气安全检查",
    "NPN/PNP 传感器类型识别",
    "接线图判断训练",
    "PLC 输入监控训练"
  ],
  "next_actions": [
    "先复习 NPN/PNP 输出方向和 PLC 输入公共端匹配关系。",
    "在断电状态下完成一次三线制传感器接线图判断训练。"
  ]
}
```
