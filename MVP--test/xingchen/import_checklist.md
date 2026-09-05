# 星辰导入检查表

## 工作流节点

- [ ] 创建星辰 Agent 工作流应用。
- [ ] 创建 `Start：学生输入` 节点，保存 `user_input`。
- [ ] 创建 `Intent：意图识别` 大模型节点，粘贴 `prompts/intent_classifier_prompt.md`。
- [ ] 创建 `Clarify：信息不足追问` 大模型节点，粘贴 `prompts/clarify_prompt.md`。
- [ ] 创建 `Retrieve：知识库检索` 节点。
- [ ] 创建 `Graph：岗位能力图谱生成` 大模型节点，粘贴 `prompts/graph_generator_prompt.md`。
- [ ] 创建 `Quiz：诊断题输出` 节点，使用 `diagnosis/diagnostic_questions.json`。
- [ ] 创建 `Score：代码模块评分` 节点，粘贴 `xingchen/code_module_scoring.js`。
- [ ] 创建 `Diagnose：薄弱点诊断` 大模型节点，粘贴 `prompts/diagnosis_prompt.md`。
- [ ] 创建 `Recommend：学习路径和实训任务推荐` 大模型节点，粘贴 `prompts/learning_path_prompt.md`。
- [ ] 创建 `Feedback：已掌握/仍不会/需要更基础讲解` 最终反馈节点。

## 知识库上传

- [ ] 上传 `knowledge/ability_nodes.json`。
- [ ] 上传 `knowledge/knowledge_50.json`，作为轻量主知识库。
- [ ] 上传 `knowledge/imports/机电一体化智能体_知识库导入版_V1.json`，作为 64 条扩展知识库。
- [ ] 上传或登记 `knowledge/resources.json`。
- [ ] 上传或登记 `knowledge/training_tasks.json`。
- [ ] 将 `docs/references/知识库2.md` 作为来源依据草表保存，不直接当作已核验教材来源。

## 代码节点输入

```json
{
  "answers": {
    "Q01": "A",
    "Q02": ["A", "B", "C", "D"],
    "Q03": "B"
  }
}
```

## 代码节点输出

```json
{
  "score": 75,
  "correct_count": 6,
  "total_count": 8,
  "weak_abilities": [],
  "recommended_path": [],
  "feedback_level": "需要补基础"
}
```

## 人工配置重点

- [ ] Retrieve 节点 TopK 建议设置为 5 到 8。
- [ ] Retrieve 检索字段优先使用 `知识点`、`技能点`、`常见错误/问题`、`检索关键词`、`能力单元`。
- [ ] Score 节点需要能读取或内置 `diagnosis/diagnostic_questions.json` 和 `diagnosis/scoring_rules.json`。
- [ ] Diagnose 节点必须使用 `score_result.weak_abilities`，不允许模型自由编造薄弱点。
- [ ] Recommend 节点必须使用 `score_result.recommended_path` 和 `knowledge/training_tasks.json`。
- [ ] 所有涉及接线、通电监控、传感器调试和气缸动作的回复必须先输出安全提醒。

## 导入前自测

- [ ] 运行 `node tests/scoring.test.js`。
- [ ] 输入全对答案，确认输出 `score = 100`。
- [ ] 输入部分错答案，确认输出 `score = 75` 且包含 `A02`、`A03`。
- [ ] 输入缺少答案，确认缺失题按错误处理。
- [ ] 检查最终反馈是否包含“已掌握/仍不会/需要更基础讲解”。

