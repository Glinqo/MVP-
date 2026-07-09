# Graph Generator Prompt

## 任务

根据能力节点、知识点和当前薄弱点生成轻量能力图谱。必须输出 Mermaid，并同时输出结构化节点和边，便于本地后续服务或可选平台节点使用。

## 输入变量

```json
{
  "ability_nodes": "{{ability_nodes}}",
  "knowledge_points": "{{knowledge_points}}",
  "score_result": "{{score_result}}",
  "focus_abilities": "{{focus_abilities}}"
}
```

## 约束条件

- Mermaid 必须可解析，使用 `flowchart TD` 或 `flowchart LR`。
- Mermaid 节点文本包含 `/`、括号、冒号等特殊字符时，必须使用引号。
- 图谱聚焦 MVP 场景，不超过 15 个节点。
- 必须包含安全节点、NPN/PNP 判断、PLC 输入公共端、PLC 输入监控和输入点无响应排查。
- 专业关系优先来自 `ability_nodes` 的 `parent_id`、`prerequisites`、`related_knowledge`。
- 不编造不存在的能力节点 ID。

## 输出格式

```json
{
  "graph_title": "传感器 NPN/PNP 到 PLC 输入排查能力图谱",
  "mermaid": "flowchart TD\n  safety[\"电气安全检查\"] --> sensor[\"NPN/PNP 传感器类型识别\"]\n  sensor --> common[\"PLC 输入公共端判断\"]",
  "nodes": [
    {
      "id": "electrical_safety_check",
      "label": "电气安全检查",
      "status": "required",
      "knowledge_refs": ["K001", "K002"]
    }
  ],
  "edges": [
    {
      "from": "electrical_safety_check",
      "to": "sensor_type_identification",
      "type": "requires"
    }
  ],
  "safety_notice": "涉及接线和设备调试时，先断电并确认急停、气源、电源和设备状态。"
}
```
