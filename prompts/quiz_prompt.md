# Quiz Prompt

## 任务

根据指定能力点生成诊断或自测题。题目必须贴合“传感器 NPN/PNP 接线与 PLC 输入信号排查”实训场景。

## 输入变量

```json
{
  "ability_id": "{{ability_id}}",
  "ability_node": "{{ability_node}}",
  "knowledge_points": "{{knowledge_points}}",
  "common_errors": "{{common_errors}}",
  "difficulty": "{{difficulty}}",
  "question_count": "{{question_count}}"
}
```

## 约束条件

- 题目专业结论优先引用知识库条目。
- 涉及接线、通电测量或设备动作的题目，解析中必须包含安全提醒。
- 题型仅使用 `single_choice`、`multiple_choice`、`ordering`。
- 正确答案必须确定，便于代码模块评分。
- 不让 LLM 自由评分，不生成开放式主观打分题。
- 每道题必须绑定 `ability_id` 和 `knowledge_refs`。

## 输出格式

```json
{
  "questions": [
    {
      "id": "Q_NEW_01",
      "type": "single_choice",
      "ability_id": "plc_input_common_terminal",
      "question": "三线 PNP 传感器接入 PLC 输入点时，最需要同时确认哪一项？",
      "options": [
        {"id": "A", "text": "PLC 输入公共端是否接到匹配电位"},
        {"id": "B", "text": "HMI 页面颜色"}
      ],
      "correct_answer": "A",
      "explanation": "PNP 输出类型必须与 PLC 输入公共端匹配。涉及接线调整时，先断电并确认设备安全状态。",
      "wrong_feedback": "请复习 PNP 输出与 PLC 输入公共端的匹配关系。",
      "knowledge_refs": ["K012", "K016", "K020"],
      "source": "PLC 实训指导书/教师确认资料/课程标准待补充"
    }
  ]
}
```

