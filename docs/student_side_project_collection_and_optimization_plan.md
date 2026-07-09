# Student-Side Project Collection And Optimization Plan

调研日期：2026-07-09

本计划聚焦学生端，把现有 MVP 做强，而不是扩展成 LMS、账号系统、数据库系统或通用 Agent 平台。目标是把“学生自由提问 -> 直接回答/追问 -> 能力图谱更新 -> 讲解/练习/实训任务 -> 反馈再更新”这条闭环做扎实。

## 1. 可借鉴项目清单

| 项目 | 做得好的地方 | 对本 MVP 的借鉴方式 | 不直接照搬的部分 |
| --- | --- | --- | --- |
| KnowBook AI | 资料上传/粘贴后切分 chunk，抽取知识点，生成知识图谱，问答带引用，图谱高亮相关路径，练习批改后标记薄弱节点 | 学生提问后，把答案、知识点、能力节点和图谱高亮绑定；补强“回答引用来源”和“节点为什么被命中” | 不引入 Django/SQLite/ECharts 大框架，不做通用课程资料上传平台 |
| Educational_RAG_System | 两级检索：BM25 精确命中优先，置信度不足再走语义 RAG；父子块切分；缓存热门查询 | 先做轻量关键词/标签检索，再按 `ability_id`、`knowledge_id` 和问题模式重排；后续可选向量检索 | 不引入 MySQL、Redis、Milvus、BERT、BGE-Reranker 这一整套重服务 |
| Inno Agent | L1 学习者画像、L2 知识库、L3 会话记录分层记忆；可检查、可修正的学习者模型；“持久事实写入工具而非藏在回答里” | 把学生图谱事件、能力状态、知识来源分层保存；每次回答前注入简短 learner context pack | 不做跨平台 IM、复杂 scheduler、完整 agent runtime |
| DeepTutor | 单一 agent loop 支撑 Chat、Quiz、Guided Learning、Mastery Path；三层 Memory Graph 能追溯证据 | 保持一个学生主对话入口，工具只是同一学习状态的不同视图；个人图谱节点要能展开证据 | 不做多用户部署、伙伴 Agent、技能市场、复杂知识库引擎 |
| PAL 2.0 | 知识追踪、掌握度预测、个性化学习路径、资源推荐、先修关系图谱 | 用规则版 mastery score/confidence 替代深度模型，先把路径推荐与先修能力补齐 | 不引入 DKT/SAKT/PyTorch/PostgreSQL/Celery |
| EduAdapt AI | 学生交互 -> 知识追踪 -> 个性化引擎 -> 内容匹配/路径调整；资源推荐考虑相关度、难度和学习效果 | 给资源和任务增加 `difficulty`、`estimated_time`、`why_recommended`，用规则打分排序 | 不做强化学习训练，只借鉴奖励函数思想 |
| OATutor | BKT 估计技能掌握度，优先选择最低掌握度问题；可前端部署，强调可配置启发式 | 给个人能力图谱增加轻量 BKT 风格更新：答错降分、讲题/任务/反馈逐步加分 | 不迁移完整 BKT UI 或 Firebase/LTI |
| Multi-Agent Study Assistant | 6 个专门 Agent：学习分析、路线、出题、讲解、资源、RAG；职责清晰 | 用“模块化 Agent 服务/提示词”实现，不启动真正多 Agent 自治循环 | 不引入 Phidata、Streamlit、LangChain、ChromaDB |
| Asset Intelligence Graph-RAG | 制造业数字主线：实体图谱 + 混合检索 + 图谱感知推理 + 兼容性评分 | 把“岗位 -> 能力 -> 知识 -> 现象 -> 排故步骤 -> 任务”的关系作为图谱检索上下文 | 不上 Neo4j，不做复杂零部件兼容性评分 |
| Khanmigo | 不等学生问出完美问题，而是在做题/学习过程中即时提供帮助；引导学生思考 | 学生端回答后给“下一步更有价值的问题”，并在题目/图谱/任务旁提供随时追问入口 | 不能照搬“永远不直接给答案”；职业排故场景必须先直接给安全和排故建议 |
| Duolingo Max | `Explain My Answer` 和 `Roleplay` 两个高频功能，适合把 AI 嵌入练习过程 | 增加“讲解我的答案”和“现场师傅角色扮演排故”两个学生端强功能 | 不做语言学习式游戏化路径 |
| Coursera Coach | 嵌在课程上下文内，能答疑、总结、给练习、推荐视频片段/资源 | 个性化培养方案中只从资源库给视频/文本资源，不让模型编造链接 | 不做课程平台集成 |
| Quizlet Q-Chat | 自适应提问、检测理解、根据内容生成互动学习 | 自测和练习题从“提交评分”升级成“做题后即时讲解 + 继续追问” | 不把学生端变成刷题工具 |

## 2. 学生端应吸收的核心做法

### 2.1 从“聊天框”升级为“学习工作台”

当前聊天主屏方向是正确的，但要补足三个学生会真实需要的能力：

1. 直接回答现场问题：先说可能原因和先查什么。
2. 讲清为什么：把答案拆成“现场证据 -> 判断依据 -> 能力缺口 -> 知识点”。
3. 帮学生问下去：每次回答后给 2-4 个高价值追问，例如“怎么判断公共端接错？”“PLC 输入灯亮但监控不变说明什么？”

建议输出结构固定为：

```json
{
  "answer": "",
  "safety_notice": "",
  "evidence_used": [],
  "reasoning_steps": [],
  "ability_hits": [],
  "knowledge_refs": [],
  "next_questions": [],
  "recommended_actions": []
}
```

### 2.2 增加“半屏讲解”

学生在图谱、题目、知识卡、培养方案中点击“问 AI 讲解”时，不必完全跳回聊天界面。建议改成半屏讲解抽屉：

- 左侧保留当前题目/节点/任务。
- 右侧打开 AI 讲解窗口。
- 讲解窗口支持继续追问。
- 每次讲解都写入 `question_explained` 或 `knowledge_explained` 学习事件。

这借鉴 Duolingo Max 的 `Explain My Answer`：解释嵌在练习现场，而不是把学生打断带走。

### 2.3 增加“排故角色扮演”

职业新人最需要的不是泛泛知识问答，而是模拟现场判断。建议新增一个轻量模式：

```text
师傅给现场现象 -> 学生选择下一步检查 -> Agent 返回观察结果 -> 学生继续判断 -> 更新能力图谱
```

第一版只做 4 个脚本场景：

- 传感器灯亮，PLC 输入灯不亮，监控不变。
- 传感器灯亮，PLC 输入灯亮，监控不变。
- 传感器灯不亮或不稳定。
- 气缸不动作，分电气/程序/气路排查。

### 2.4 把个人图谱改成“可解释掌握度”

个人能力图谱不能只显示 weak/mastered，要显示为什么：

- `mastery_score`：0-100。
- `confidence`：低/中/高，代表证据是否足够。
- `evidence_count`：来自问答、错题、讲题、任务、反馈的数量。
- `last_event`：最近一次造成变化的事件。
- `next_best_action`：下一步最值得做什么。

更新规则先保持确定性：

| 事件 | 建议更新 |
| --- | --- |
| 聊天命中能力 | `touched`，小幅增加证据，不直接判弱 |
| 问题模式命中关键缺口 | 标记 `recommended_next` 或 `weak` |
| 自测答错 | 明确降分，状态变 `weak` |
| 看讲解 | 小幅加分，状态可到 `improving` |
| 任务完成 | 中幅加分，提高 confidence |
| 反馈“已掌握” | 加分但安全相关能力不直接满分 |
| 反馈“仍不会” | 降分，推荐更基础讲解 |

### 2.5 个性化培养方案必须像“下一节课行动单”

培养方案不要像课程大纲，应该像学生今天就能照着做的行动单：

```text
第 1 步：看懂当前故障
第 2 步：补一个关键知识点
第 3 步：做一个可提交的实训任务
第 4 步：用 2 道题或 1 个现场判断复测
第 5 步：反馈已掌握/仍不会
```

每个阶段必须包含：

- 能力点。
- 知识点文本讲解。
- 资源链接，尤其是视频，必须来自 `resources.json`。
- 实训任务。
- 检查点。
- 图谱更新预期。

### 2.6 检索改成“轻量混合检索”

借鉴 EduRAG，但不引入重型依赖。第一版实现：

1. 精确规则命中：问题模式、能力 ID、知识 ID、常见错误。
2. 关键词命中：中文短词、同义词、设备词、状态词。
3. 结构重排：命中能力链上游/下游的知识优先。
4. 来源约束：专业结论必须带 `source`。
5. 可选 LLM：只基于检索包解释，不自由发散。

后续如果要升级，再考虑本地 SQLite FTS 或轻量 embedding，不直接上 Milvus。

## 3. 建议精简或隐藏的功能

为了做好学生端，以下功能不要放在第一视觉优先级：

- 星辰平台导入：保留文档，不进入学生主流程。
- 岗位图谱更新建议：保留教师/评审演示入口，学生端默认隐藏。
- 教师摘要：学生端只保留一个入口，不占主屏。
- Mermaid 文本：保留导出/文档用途，学生端主要看 SVG/HTML 图谱。
- 通用知识库搜索：降级为“和当前问题相关的知识”，不要做百科搜索框。
- 多 Agent 自治运行：暂不做。先用模块化服务和专门 prompt，避免不可控和慢。

## 4. 推荐学生端新信息架构

```text
主屏：岗位培训 AI 对话
  - 岗位身份条
  - 现场问题输入
  - Agent 回答
  - 高价值追问
  - 快捷功能按钮

半屏：即时讲解抽屉
  - 题目讲解
  - 能力节点讲解
  - 知识卡讲解
  - 任务步骤讲解

全屏工具：
  - 个人能力图谱
  - 当前问题图谱
  - 岗位能力图谱
  - 个性化培养方案
  - 排故角色扮演
  - 自测与错题讲解
  - 知识与资源
```

## 5. 后端优化架构

不建议引入真正多 Agent 框架。建议保持一个轻量 orchestrator，内部拆为“专职服务”：

```text
Chat Orchestrator
  -> Safety Guard
  -> Problem Pattern Matcher
  -> Lightweight Retriever
  -> Answer Composer
  -> Graph Update Engine
  -> Plan Builder
  -> Quiz/Explanation Service
  -> Resource Ranker
```

LLM 使用策略：

- 规则能回答的故障路径先规则回答。
- LLM 用于自然语言解释、类比、追问建议和讲解。
- 评分、图谱状态、资源链接、薄弱点不交给 LLM 自由决定。
- LLM 输入必须是小包上下文，不塞全量知识库。

效率优化：

- 启动时预加载 JSON 并建立内存索引。
- `ability_id -> knowledge/tasks/resources/questions` 建索引。
- `knowledge_id -> source/resources` 建索引。
- 会话事件采用 append-only，学生图谱用快照缓存。
- 新增 `/api/student/bootstrap` 一次返回岗位、初始图谱、推荐问题、工具清单。
- 全屏工具懒加载，不在首页一次请求所有数据。

## 6. 开发优先级

### P0：学生端讲解体验变强

目标：学生问问题后，答案更像“师傅在带我排故”。

- 优化 `/api/chat/message` 输出结构。
- 增加 `evidence_used`、`reasoning_steps`、`next_questions`。
- 在前端消息中渲染“判断依据”和“下一步追问”。
- 讲题按钮打开半屏讲解抽屉。

验收：

- 输入“传感器灯亮但 PLC 没输入”，能看到安全提醒、直接判断、依据、追问、能力命中。
- 点击一道自测题“问 AI 讲解”，半屏打开，不丢失当前题目。

### P1：个人能力图谱可解释

目标：学生能看懂“我哪里弱、为什么弱、下一步怎么补”。

- 图谱节点增加 `next_best_action`。
- 节点详情显示事件证据时间线。
- 讲题、任务、反馈事件更新掌握度。
- 安全相关节点不允许被简单标记为 100% 掌握。

验收：

- 答错公共端题后，公共端节点显示 weak、原因、错题来源、补救任务。
- 点击“已掌握”后状态最多到 improving/mastered，但保留安全复核提醒。

### P2：个性化培养方案行动化

目标：培养方案像一节课可执行训练单。

- 输出 3-5 个阶段。
- 每阶段绑定能力、知识、资源、任务、检查点。
- 视频只从 `resources.json` 读取。
- 支持“生成今日训练单”和“生成 7 天补强计划”。

验收：

- 弱点为 NPN/PNP 和公共端时，计划优先安排线型识别、公共端判断、三联状态记录。
- 没有视频资源时显示“暂无视频资源”，不编造链接。

### P3：排故角色扮演

目标：把传统做题变成现场判断训练。

- 新增 `knowledge/troubleshooting_scenarios.json`。
- 新增 `/api/scenario/start`、`/api/scenario/step`。
- 学生选择下一步检查，系统返回结果并更新能力图谱。

验收：

- 学生能完成“传感器灯亮但 PLC 输入灯不亮”排故脚本。
- 错误检查顺序会映射到相关能力弱点。

### P4：轻量混合检索

目标：回答更稳、更可溯源。

- 建立关键词、同义词和能力链索引。
- 引入父子块结构：知识条目是父块，关键句/错误/任务是子块。
- 检索结果返回 `source` 和命中原因。

验收：

- 问“公共端为什么影响输入”，检索优先返回公共端、NPN/PNP、PLC 输入模块相关知识。
- 每条专业解释都能追溯到知识条目或项目整理来源。

## 7. 先不做的升级

- 不接入 Milvus/Neo4j/PostgreSQL。
- 不做真实账号和长期画像。
- 不做完整课程资料上传与自动知识图谱生成。
- 不做企业岗位需求爬虫。
- 不做完全自治多 Agent 辩论或计划执行。
- 不做真实 PLC 设备控制。

## 8. 参考来源

- 本地补充材料：`D:\Desktop\challenge2026\与竞赛相关的AI开源模型.docx`
- KnowBook AI: https://github.com/starsstreaming/KnowBook
- Educational_RAG_System: https://github.com/Happy-Chen-CH/Educational_RAG_System
- Inno Agent: https://github.com/hhyqhh/inno-agent
- DeepTutor: https://github.com/HKUDS/DeepTutor
- PAL 2.0: https://github.com/bkshgtm/PersonalizedAdaptiveLearning
- EduAdapt AI: https://github.com/mwasifanwar/eduadapt-ai
- OATutor: https://github.com/CAHLR/OATutor-LLM-Learner
- Multi-Agent Study Assistant: https://github.com/A-R007/Multi-Agent-Study-Assistant
- Asset Intelligence Graph-RAG: https://github.com/Prajwalkadam29/asset-intelligence-graph-rag
- Khanmigo: https://www.khanmigo.ai/
- Duolingo Max: https://blog.duolingo.com/duolingo-max/
- Coursera Coach: https://blog.coursera.org/coursera-coach-leveraging-genai-to-empower-learners/
- Quizlet Q-Chat: https://www.prnewswire.com/news-releases/quizlet-launches-q-chat-ai-tutor-built-with-openai-api-301759014.html
