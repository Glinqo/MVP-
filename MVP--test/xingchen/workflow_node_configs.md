# Workflow Node Configs

本文件用于在科大讯飞星辰 Agent 开发平台中逐节点配置 MVP 工作流。每个节点都写明变量、Prompt、知识库、代码模块和人工配置项。

## 变量命名约定

```json
{
  "user_input": "学生原始输入",
  "intent_result": "意图识别 JSON",
  "clarify_result": "追问 JSON",
  "retrieved_knowledge": "知识库检索结果",
  "graph_result": "岗位能力图谱 JSON，包含 mermaid 字段",
  "quiz_result": "诊断题展示结果",
  "student_answers": {"answers": {"Q01": "A"}},
  "score_result": "代码模块评分 JSON",
  "diagnosis_result": "薄弱点诊断 JSON",
  "learning_path_result": "学习路径 JSON",
  "feedback_result": "最终反馈 JSON"
}
```

## 1. Start：学生输入

- 节点名称：Start：学生输入
- 节点类型：开始节点/用户输入节点
- 输入变量：无
- 输出变量：`user_input`, `role_hint`
- 使用 Prompt：不使用
- 是否调用知识库：否
- 是否调用代码模块：否
- 失败兜底文案：`请描述你在传感器接线或 PLC 输入监控中遇到的现象。`
- 星辰平台中需要人工配置的地方：
  - 欢迎语：`请描述传感器动作灯、PLC 输入灯、在线监控状态，或直接开始 8 题诊断。`
  - 默认 `role_hint = "student"`。
  - 保存用户输入到 `user_input`。

## 2. Intent：意图识别

- 节点名称：Intent：意图识别
- 节点类型：大模型节点
- 输入变量：`user_input`, `role_hint`, `conversation_context`
- 输出变量：`intent_result`
- 使用 Prompt：`prompts/intent_classifier_prompt.md`
- 是否调用知识库：否
- 是否调用代码模块：否
- 失败兜底文案：`我还不能判断你的需求，请补充你是要排故、答题、看图谱，还是生成学习路径。`
- 星辰平台中需要人工配置的地方：
  - 粘贴 `prompts/intent_classifier_prompt.md`。
  - 设置输出为 JSON。
  - 配置分支：
    - `intent_result.intent == "clarify"` -> Clarify。
    - 其他诊断/图谱/测验/路径意图 -> Retrieve。

## 3. Clarify：信息不足追问

- 节点名称：Clarify：信息不足追问
- 节点类型：大模型节点
- 输入变量：`user_input`, `intent_result`, `known_slots`, `ability_nodes`
- 输出变量：`clarify_result`
- 使用 Prompt：`prompts/clarify_prompt.md`
- 是否调用知识库：可选，建议读取 `knowledge/ability_nodes.json`
- 是否调用代码模块：否
- 失败兜底文案：`请补充：传感器动作灯是否亮、PLC 输入灯是否亮、在线监控地址是否变化。`
- 星辰平台中需要人工配置的地方：
  - 粘贴 `prompts/clarify_prompt.md`。
  - 配置输出后回到 Start 或等待学生补充。
  - 如果追问涉及接线或设备调试，保留 `safety_notice` 字段。

## 4. Retrieve：知识库检索

- 节点名称：Retrieve：知识库检索
- 节点类型：知识库检索节点
- 输入变量：`user_input`, `intent_result`, `score_result`
- 输出变量：`retrieved_knowledge`, `ability_nodes`, `knowledge_points`, `resources`, `training_tasks`
- 使用 Prompt：不使用
- 是否调用知识库：是
- 是否调用代码模块：否
- 失败兜底文案：`未检索到匹配资料，先使用基础排查顺序：安全、电源、传感器、接线、公共端、地址、程序。`
- 星辰平台中需要人工配置的地方：
  - 上传 `knowledge/ability_nodes.json`。
  - 上传 `knowledge/knowledge_50.json`。
  - 上传 `knowledge/resources.json`。
  - 上传 `knowledge/training_tasks.json`。
  - 建议 TopK：5 到 8。
  - 将知识库检索输出绑定到 `retrieved_knowledge`。

## 5. Graph：岗位能力图谱生成

- 节点名称：Graph：岗位能力图谱生成
- 节点类型：大模型节点
- 输入变量：`ability_nodes`, `knowledge_points`, `score_result`, `focus_abilities`
- 输出变量：`graph_result`
- 使用 Prompt：`prompts/graph_generator_prompt.md`
- 是否调用知识库：是
- 是否调用代码模块：否
- 失败兜底文案：`暂时无法生成图谱，请按：电气安全检查 -> NPN/PNP 类型识别 -> PLC 输入公共端判断 -> PLC 输入监控 -> 输入点无响应排查 学习。`
- 星辰平台中需要人工配置的地方：
  - 粘贴 `prompts/graph_generator_prompt.md`。
  - 输出格式设置为 JSON。
  - 将 `graph_result.mermaid` 用于 Markdown 或前端展示。

## 6. Quiz：诊断题输出

- 节点名称：Quiz：诊断题输出
- 节点类型：大模型节点/内容节点/表单节点
- 输入变量：`diagnostic_questions`, `retrieved_knowledge`, `graph_result`
- 输出变量：`quiz_result`, `student_answers`
- 使用 Prompt：`prompts/quiz_prompt.md`
- 是否调用知识库：是
- 是否调用代码模块：否
- 失败兜底文案：`诊断题加载失败，请先回答基础题：调整传感器接线前是否应先断电并确认设备状态？`
- 星辰平台中需要人工配置的地方：
  - 推荐将 `diagnosis/diagnostic_questions.json` 配置为固定题库。
  - 将学生答案整理为 `student_answers`：

```json
{
  "answers": {
    "Q01": "A",
    "Q02": ["A", "B", "C", "D"]
  }
}
```

## 7. Score：代码模块评分

- 节点名称：Score：代码模块评分
- 节点类型：代码节点
- 输入变量：`student_answers`
- 输出变量：`score_result`
- 使用 Prompt：不使用
- 是否调用知识库：否
- 是否调用代码模块：是，`xingchen/code_module_scoring.js`
- 失败兜底文案：`评分暂时失败，请检查答案格式是否为 {"answers":{"Q01":"A"}}。`
- 星辰平台中需要人工配置的地方：
  - 粘贴 `xingchen/code_module_scoring.js`。
  - 确保代码节点可读取或内置：
    - `diagnosis/diagnostic_questions.json`
    - `diagnosis/scoring_rules.json`
  - 输入绑定：`student_answers`。
  - 输出绑定：`score_result`。

## 8. Diagnose：薄弱点诊断

- 节点名称：Diagnose：薄弱点诊断
- 节点类型：大模型节点
- 输入变量：`score_result`, `ability_nodes`, `knowledge_points`, `diagnostic_questions`
- 输出变量：`diagnosis_result`
- 使用 Prompt：`prompts/diagnosis_prompt.md`
- 是否调用知识库：是
- 是否调用代码模块：否
- 失败兜底文案：`评分结果已生成，但解释失败。请先查看 score、correct_count、weak_abilities 和 recommended_path。`
- 星辰平台中需要人工配置的地方：
  - 粘贴 `prompts/diagnosis_prompt.md`。
  - 禁止模型重新评分。
  - 诊断必须使用 `score_result.weak_abilities`。

## 9. Recommend：学习路径和实训任务推荐

- 节点名称：Recommend：学习路径和实训任务推荐
- 节点类型：大模型节点
- 输入变量：`score_result`, `diagnosis_result`, `knowledge_points`, `resources`, `training_tasks`, `ability_nodes`
- 输出变量：`learning_path_result`
- 使用 Prompt：`prompts/learning_path_prompt.md`
- 是否调用知识库：是
- 是否调用代码模块：否
- 失败兜底文案：`建议先完成：电气安全检查 -> NPN/PNP 传感器类型识别 -> 接线图判断训练 -> PLC 输入监控训练。`
- 星辰平台中需要人工配置的地方：
  - 粘贴 `prompts/learning_path_prompt.md`。
  - 将 `score_result.recommended_path` 作为主路径。
  - 将 `knowledge/training_tasks.json` 绑定为任务来源。

## 10. Feedback：已掌握/仍不会/需要更基础讲解

- 节点名称：Feedback：已掌握/仍不会/需要更基础讲解
- 节点类型：大模型节点
- 输入变量：`score_result`, `diagnosis_result`, `learning_path_result`, `user_input`
- 输出变量：`feedback_result`
- 使用 Prompt：可复用 `prompts/diagnosis_prompt.md` 和 `prompts/learning_path_prompt.md`，或在星辰中配置最终回答模板
- 是否调用知识库：可选
- 是否调用代码模块：否
- 失败兜底文案：`本次反馈：先确认安全，再按推荐路径完成下一次实训；如果仍不会，请从电气安全和 NPN/PNP 基础重新学习。`
- 星辰平台中需要人工配置的地方：
  - 配置最终输出模板。
  - 根据 `score_result.feedback_level` 选择表达：
    - `掌握较好`：强调已掌握，并给巩固任务。
    - `需要专项训练`：列出仍不会的薄弱点和专项训练。
    - `需要补基础`：给更基础讲解和低门槛实训任务。

