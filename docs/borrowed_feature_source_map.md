# Borrowed Feature Source Map

更新日期：2026-07-09

目标：把值得借鉴的学生端功能从开源项目中定位到真实源码，再按本仓库的轻量 MVP 边界进行移植。本文不把第三方源码原样复制进仓库；对无许可证或限制性许可证项目，只借鉴交互和架构模式。

## 1. 源码扫描版本

| 项目 | 仓库 | 扫描 commit | 许可证判断 |
| --- | --- | --- | --- |
| KnowBook AI | https://github.com/starsstreaming/KnowBook | `95d0d2b4221eebc92cf5ec58f961b3c34c54b99b` | LICENSE 为 All Rights Reserved，不复制代码 |
| Educational_RAG_System | https://github.com/Happy-Chen-CH/Educational_RAG_System | `07b1a42a7c032a338f7630fded10a214f682615a` | 未发现 LICENSE，不复制代码 |
| Inno Agent | https://github.com/hhyqhh/inno-agent | `9ef4d65d10f470cd62d94ce245ff1ac9a0e08bfc` | MIT |
| DeepTutor | https://github.com/HKUDS/DeepTutor | `df6922bb1bc186c938f5c9fb8e7762abe16ea16e` | Apache-2.0 |
| PAL 2.0 | https://github.com/bkshgtm/PersonalizedAdaptiveLearning | `aa309a6846414d1d9a3b6ccf0a3a2b7c2eeaf737` | 未发现 LICENSE，不复制代码 |
| EduAdapt AI | https://github.com/mwasifanwar/eduadapt-ai | `9341e3fb242b82d2053af5c024a8cfeadecc21e5` | 未发现 LICENSE，不复制代码 |
| OATutor LLM Learner | https://github.com/CAHLR/OATutor-LLM-Learner | `0d376e23302485bebef6e1cad04da3816a164cd6` | MIT |
| Multi-Agent Study Assistant | https://github.com/A-R007/Multi-Agent-Study-Assistant | `3c1c88b95a9d13408bd62b6b686737eb6a135983` | 未发现 LICENSE，不复制代码 |
| Asset Intelligence Graph-RAG | https://github.com/Prajwalkadam29/asset-intelligence-graph-rag | `a94fe9bb03ff98e010250f06b783981b267467d2` | MIT |

## 2. 功能与源码对应

| 可借鉴功能 | 对应源码位置 | 源码里做了什么 | 本 MVP 移植方式 |
| --- | --- | --- | --- |
| 回答带引用、图谱路径和练习联动 | KnowBook `backend/knowbook_api/views.py`：`ask`、`_attach_answer_metadata`、`graph_explain`；`backend/chunking.py`：`retrieve_chunks`；`backend/graph.py`：`extract_graph` | 问答先检索 chunk，补 citations，再高亮 graphPath，并生成 exercises | 在 `/api/chat/message` 增加 `evidence_used`、`reasoning_steps`、`knowledge_refs`；当前问题图谱继续用本地能力节点 |
| 节点解释 | KnowBook `backend/knowbook_api/services.py`：`chunks_for_node`、`graph_path_context`、`fallback_node_explanation` | 点击图谱节点后，按节点关联 chunk、邻居、路径生成解释 | 新增轻量 `/api/explain`，支持 ability/knowledge/question/task 四类讲解 |
| 父子块检索和混合检索 | Educational_RAG_System `rag_qa/core/document_processor.py`：`process_documents`；`rag_qa/core/rag_system.py`：`retrieve_and_merge`；`rag_qa/core/vector_store.py`：`hybrid_search_with_rerank`；`mysql_qa/retrieval/bm25_search.py`：`BM25Search.search` | 父块保存完整上下文，子块用于精确召回；策略选择后做混合检索和重排 | 不上 Milvus/BM25 依赖；在 `retrieval.py` 做规则命中 + 关键词 + 能力链重排 + 来源返回 |
| 分层学习者记忆 | Inno Agent `apps/inno-agent/src/memory/learner/context-pack.ts`、`profile-store.ts`、`auto-profile.ts`、`learner-tools.ts`；`agent/inno-extension.ts` | L1 学习者画像、L2 wiki、L3 会话检索分层；每轮前注入 learner context pack | 我们只保留 session 级事件与个人能力图谱；新增“learner context pack”供 chat 和 plan 使用 |
| 跨会话召回的阈值思想 | Inno Agent `apps/inno-agent/src/memory/l3/recall.ts`、`sqlite-store.ts`、`indexer.ts` | 会话内容切块入 SQLite FTS，按阈值召回，失败不阻塞主流程 | 本 MVP 不做长期跨会话；借鉴“召回失败不阻塞”和“只注入短上下文” |
| 单一 Agent loop 支撑多功能 | DeepTutor `deeptutor/agents/chat/agent_loop.py`、`agentic_pipeline.py`、`chat_agent.py`；`deeptutor/api/routers/plugins_api.py` | Chat、Quiz、Research、Mastery Path 共用运行时，功能只是 capability 切换 | 本 MVP 保持一个 `chat_message` 主入口，工具面板只是同一 session 状态的不同视图 |
| 题目讲解/批改 | DeepTutor `deeptutor/api/routers/quiz_judge.py`、`question_notebook.py`、`sessions.py` | 题目、参考答案、学生答案进入讲解/评估接口，并可存入 question notebook | 新增 `/api/explain`，题目讲解不自由改分，只解释标准答案与错因 |
| Mastery Path/学习路径 | DeepTutor `deeptutor/api/routers/mastery_path.py`；PAL `learning_paths/views.py`、`learning_paths/models.py`；EduAdapt `core/learning_optimizer.py`、`core/content_recommender.py` | 根据掌握情况生成路径、匹配资源、安排阶段 | 继续用 `personalized_plan.py`，增加今日训练单/7 天计划和阶段化行动 |
| 知识追踪/掌握度 | PAL `ml_models/ml/dkt.py`、`ml_models/ml/sakt.py`；OATutor README 与前端资源；EduAdapt `models/knowledge_tracer.py`、`assessment/progress_tracker.py` | 用 DKT/SAKT/BKT/进度追踪预测掌握度 | 不引入深度模型；用 `graph_update_engine.py` 的规则分数 + confidence 先做可解释掌握度 |
| 多 Agent 分工 | Multi-Agent Study Assistant `study_agents.py`、`agent_handler.py`、`prompts.yaml`、`rag_helper.py` | 学习分析、路线、出题、讲解、资源、RAG 拆成多个专职 Agent | 不引入多 Agent runtime；按服务拆分：chat/explain/retrieval/graph/plan/quiz |
| 制造业 Graph-RAG | Asset Intelligence Graph-RAG `backend/rag/retrieval.py`、`backend/rag/synthesis.py`、`backend/compatibility/scoring.py`、`backend/ingestion/yaml_ingestor.py` | 工业实体图谱 + 检索 + 兼容性评分 + 综合回答 | 把“岗位-能力-知识-现象-排故步骤-任务”关系用于结构化检索，不上 Neo4j |

## 3. 第一批直接移植的学生端功能

### 3.1 结构化证据回答

来源：
- KnowBook 的 `answer + citations + relatedGraphNodes + exercises`
- DeepTutor 的单一 chat loop + capability context

本 MVP 输出：

```json
{
  "answer": "",
  "safety_notice": "",
  "evidence_used": [],
  "reasoning_steps": [],
  "knowledge_refs": [],
  "ability_hits": [],
  "next_questions": []
}
```

### 3.2 半屏讲解抽屉

来源：
- DeepTutor `quiz_judge.py` 的题目讲解/评估入口
- KnowBook `graph_explain` 的节点解释入口
- Duolingo Max `Explain My Answer` 的产品模式

本 MVP 新增：
- `POST /api/explain`
- 支持 `question`、`ability`、`knowledge`、`task`、`message` 五类讲解
- 讲解事件写入个人图谱，作为 improving 证据

### 3.3 轻量混合检索

来源：
- Educational_RAG_System 的 BM25 + RAG 两级检索
- KnowBook 的倒排索引和 citation
- Asset Graph-RAG 的图谱感知检索

本 MVP 新增或增强：
- `search_knowledge` 返回 `matched_terms`、`match_reason`、`ability_name`
- 优先按 problem pattern 和 ability 关联知识重排
- 专业结论保留 `source`

### 3.4 可解释学习者上下文

来源：
- Inno Agent 的 L1 context pack
- DeepTutor 的 inspectable memory

本 MVP 新增：
- `learner_context_pack(session_id)`：压缩个人图谱弱点、最近事件、推荐下一步
- chat/plan/explain 都能读取同一个上下文包

## 4. 暂不移植

- 自动课件上传生成知识图谱：KnowBook 做得好，但超出当前学生端闭环。
- Milvus/Neo4j/Redis/MySQL：收益不如复杂度，暂不引入。
- 真正多 Agent 自治循环：容易慢和不可控，先以模块化服务实现。
- DKT/SAKT 深度模型训练：当前数据量不足，先用可解释规则。
- 跨会话长期画像：不做账号系统，保持 session 级。

## 5. 本轮已移植落地

| 已移植功能 | 借鉴来源 | 本地实现文件 | 验证方式 |
| --- | --- | --- | --- |
| 结构化证据回答 | KnowBook `answer + citations + relatedGraphNodes`；DeepTutor 单一 chat loop | `app/services/chat.py` | `/api/chat/message` 返回 `evidence_used`、`reasoning_steps`、`knowledge_refs`、`next_questions` |
| 半屏即时讲解 | DeepTutor `quiz_judge.py`、`question_notebook.py`；KnowBook `graph_explain`；Duolingo Max `Explain My Answer` | `app/services/explanation.py`、`web/app.js`、`web/index.html`、`web/styles.css` | `/api/explain` 支持 question/ability/knowledge/task/message；前端题目和图谱节点可打开讲解抽屉 |
| 个性化题讲解兼容 | DeepTutor Question Notebook 的题目上下文讲解 | `app/services/explanation.py` | 临时生成题 `P01` 可通过 `knowledge_id` fallback 讲解 |
| 可解释轻量检索 | EduRAG BM25/父子块思想；KnowBook citation | `app/services/retrieval.py` | `/api/knowledge/search` 和聊天知识引用返回 `matched_terms`、`match_reason`、`ability_name` |
| 个人图谱下一步动作 | Inno/DeepTutor inspectable learner model | `app/services/graph.py` | 学生图谱节点包含 `next_best_action` |
| 排故角色扮演 | Duolingo Max `Roleplay`；DeepTutor Guided Learning | `knowledge/troubleshooting_scenarios.json`、`app/services/scenario.py`、`web/app.js`、`web/index.html`、`web/styles.css` | `/api/scenarios`、`/api/scenario/start`、`/api/scenario/step`；答错写入 weak，答对写入 improving |
| 学习者上下文包 | Inno Agent `context-pack.ts`、PAL 学生画像接口 | `app/services/learner_context.py`、`app/services/chat.py`、`app/server.py` | `/api/student/bootstrap` 和 `/api/chat/message` 返回 `learner_context`，LLM prompt 注入短上下文 |
| 今日训练单/7 天计划 | PAL learning path、EduAdapt adaptive path、DeepTutor Mastery Path | `app/services/personalized_plan.py`、`web/app.js`、`web/index.html`、`web/styles.css` | `/api/plan/personalized` 返回 `today_training_sheet`、`seven_day_plan`、`learning_plan` 三层计划 |

## 6. 后续扩展路线

用户新增目标要求后续继续联网调研岗位资料、扩充知识库和题库、形成更真实的岗位能力图谱，并在代码稳定后上传 GitHub。下一阶段执行顺序：

1. 联网检索权威岗位资料、职业标准、课程标准和企业招聘能力要求，补充 `source` 字段。
2. 扩展 `knowledge_50.json`、`diagnostic_questions.json`、`training_tasks.json`，优先覆盖传感器接线、PLC 输入排故、气动执行机构排查。
3. 将岗位能力图谱从演示样例升级为带证据、权重、采集时间的真实图谱快照。
4. 继续借鉴 Graph-RAG 与学习路径项目，优化图谱可视化、检索效率和学生端工作台体验。
5. 完成测试后再建立 GitHub 仓库并推送代码。
