# Learning Path Prompt

## 任务

根据代码模块输出的薄弱点，为学生生成一节实训课内可执行的学习路径。必须按薄弱点推荐路径和实训任务。

## 输入变量

```json
{
  "score_result": "{{score_result}}",
  "knowledge_points": "{{knowledge_points}}",
  "resources": "{{resources}}",
  "training_tasks": "{{training_tasks}}",
  "ability_nodes": "{{ability_nodes}}"
}
```

## 约束条件

- 只使用 `score_result.weak_abilities` 和 `score_result.recommended_path` 作为薄弱点来源。
- 每个薄弱点至少匹配 1 个知识条目和 1 个实训任务。
- 优先顺序：安全检查 -> NPN/PNP 类型识别 -> 接线图判断 -> PLC 输入公共端 -> I/O 地址映射 -> PLC 输入监控 -> 输入点无响应排查。
- 涉及接线、通电测量或设备动作时，必须把安全检查作为第 1 步。
- 输出路径总时长建议控制在 45 到 60 分钟内。
- 不推荐大型课程体系，不推荐账号系统或 LMS 操作。

## 输出格式

```json
{
  "path_title": "NPN/PNP 传感器到 PLC 输入监控补强路径",
  "safety_notice": "实训前先断电，确认急停、气源、电源和设备状态；通电监控需教师或实训指导人员确认。",
  "target_weak_abilities": [
    {
      "ability_id": "A02",
      "ability_name": "NPN/PNP 传感器类型识别",
      "reason": "NPN/PNP 输出类型与公共端关系判断错误"
    }
  ],
  "steps": [
    {
      "order": 1,
      "path_item": "电气安全检查",
      "goal": "确认接线和调试前的安全边界",
      "knowledge_refs": ["K001", "K002", "K003"],
      "task_id": "T001",
      "task_title": "三种传感器输入验证",
      "estimated_minutes": 10,
      "expected_evidence": "完成断电、急停、气源、电源状态确认记录"
    }
  ],
  "exit_check": [
    "能说出 PNP 有效输出与 PLC 输入公共端的匹配关系。",
    "能在 I/O 映射表中指出传感器输出线接入的 PLC 地址。"
  ]
}
```
