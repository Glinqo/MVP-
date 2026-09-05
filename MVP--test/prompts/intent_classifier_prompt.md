# Intent Classifier Prompt

## 任务

判断用户输入在本地 MVP 工作流中应该进入哪个节点，并只输出 JSON。

## 输入变量

```json
{
  "user_input": "{{user_input}}",
  "role_hint": "{{role_hint}}",
  "conversation_context": "{{conversation_context}}"
}
```

## 可选意图

- `clarify`：信息不足，需要追问。
- `diagnosis`：用户提交诊断答案，或描述传感器/PLC 输入/气缸动作等实训故障。
- `quiz`：用户要求出题、自测、练习题。
- `graph`：用户要求能力图谱、知识图谱或 Mermaid 图。
- `learning_path`：用户要求学习路径、补救训练、下一步实训任务。
- `teacher_view`：教师要求班级薄弱点、教学建议或反馈模板。
- `knowledge_qa`：用户询问知识点解释。

## 约束条件

- 只围绕“传感器 NPN/PNP 接线与 PLC 输入信号排查”MVP 场景分类。
- 如果用户描述接线、通电、设备动作、气缸动作或 PLC 调试，`slots.requires_safety_notice` 必须为 `true`。
- 不扩展到完整机电一体化课程体系。
- 不输出自然语言解释，只输出 JSON。

## 输出格式

```json
{
  "intent": "diagnosis",
  "confidence": 0.86,
  "role": "student",
  "reason": "用户描述传感器动作灯亮但 PLC 输入无响应，需要进入诊断节点",
  "slots": {
    "scenario": "传感器 NPN/PNP 接线与 PLC 输入信号排查",
    "course_area": ["sensor", "plc_input", "wiring"],
    "requires_safety_notice": true,
    "mentioned_signals": ["传感器动作灯", "PLC 输入点"],
    "next_node": "diagnosis"
  }
}
```
