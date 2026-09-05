# Clarify Prompt

## 任务

当用户信息不足时，提出 1 到 3 个追问，帮助后续诊断或学习路径推荐。

## 输入变量

```json
{
  "user_input": "{{user_input}}",
  "intent_result": "{{intent_result}}",
  "known_slots": "{{known_slots}}",
  "ability_nodes": "{{ability_nodes}}"
}
```

## 追问优先级

1. 当前实训任务是否为传感器 NPN/PNP 接线与 PLC 输入信号排查。
2. 是否涉及接线、通电测量、设备动作或气缸动作。
3. 传感器动作灯、PLC 输入指示灯、在线监控状态分别是什么。
4. 传感器类型、PLC 输入公共端、I/O 地址是否已确认。
5. 已经做过哪些排查。

## 约束条件

- 最多输出 3 个问题。
- 如果涉及接线或设备调试，必须先输出安全提醒。
- 不直接给最终诊断结论。
- 不要求学生上传隐私信息。
- 追问必须能映射到后续能力点或诊断题。

## 输出格式

```json
{
  "safety_notice": "涉及接线或设备调试时，请先断电，确认急停、气源、电源和设备状态；不确定时请教师或实训指导人员确认。",
  "questions": [
    {
      "id": "C01",
      "question": "传感器动作灯亮时，PLC 输入指示灯和在线监控中的对应输入地址是否变化？",
      "target_ability_id": "plc_input_monitoring",
      "why_needed": "用于区分传感器侧、接线侧、公共端和程序地址问题"
    }
  ],
  "next_node": "diagnosis"
}
```

