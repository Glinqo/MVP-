# Copy Paste Pack

## 系统角色

见 `prompts/system_prompt.md`。

## 诊断样例输入

```json
{
  "student_id": "S001",
  "answers": [
    {"question_id": "Q001", "selected_option": "PLC 输入公共端类型"},
    {"question_id": "Q002", "answer": "把现场元件、PLC 地址和变量对应起来，方便调试。"},
    {"question_id": "Q003", "selected_option": "上升沿触发"},
    {"question_id": "Q004", "answer": "要查气压、节流阀、负载和是否卡滞。"},
    {"question_id": "Q005", "answer": "先查电源，再看输入，然后看程序、输出和执行机构。"}
  ]
}
```

## 诊断样例输出

```json
{
  "total_score": 1,
  "level": "ready",
  "weak_nodes": [],
  "error_codes": []
}
```

## 学生故障描述样例

```text
自动分拣实训中，传感器灯亮，但 PLC 输入监控有时没有变化，计数也会重复增加。
```

