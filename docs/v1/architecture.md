# 系统架构设计 v1.0

## 1. 总体架构

```
┌──────────────────────────────────────────────────────────┐
│                    浏览器 (Vue 3 + TS)                     │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌───────────────┐  │
│  │ 聊天页面 │ │ 图谱页面  │ │ 配置页 │ │ 日志/统计页面  │  │
│  └────┬────┘ └────┬─────┘ └───┬────┘ └───────┬───────┘  │
│       │           │           │               │          │
└───────┼───────────┼───────────┼───────────────┼──────────┘
        │           │           │               │
   HTTP │           │           │               │
        ▼           ▼           ▼               ▼
┌──────────────────────────────────────────────────────────┐
│              RuoYi Spring Boot 后端 (Java)                │
│                                                          │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌───────────────┐  │
│  │ 安全模块 │ │ 系统模块  │ │ 聊天模块│ │  智能体管理    │  │
│  │(RuoYi复用)│ │(RuoYi复用)│ │ (新增) │ │   (新增)      │  │
│  └─────────┘ └──────────┘ └───┬────┘ └───────────────┘  │
│                               │                          │
│                         HTTP  │  (30s timeout)           │
│                               ▼                          │
│                    ┌─────────────────┐                   │
│                    │  Agent Client   │                   │
│                    │  (新增 Java 模块)│                   │
│                    └────────┬────────┘                   │
└─────────────────────────────┼────────────────────────────┘
                              │
                        HTTP  │
                              ▼
┌──────────────────────────────────────────────────────────┐
│              Python 智能体服务 (FastAPI)                   │
│                                                          │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌───────────────┐  │
│  │ 对话引擎 │ │ 意图识别  │ │ 知识检索│ │  图谱引擎      │  │
│  │ chat.py │ │intent.py │ │retrieval│ │  graph.py      │  │
│  └─────────┘ └──────────┘ └────────┘ └───────────────┘  │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌───────────────┐  │
│  │ 排故场景 │ │ 自测评分  │ │ 学生画像│ │ 证据/版本管理   │  │
│  │scenario  │ │ scoring  │ │ learner │ │ evidence_store │  │
│  └─────────┘ └──────────┘ └────────┘ └───────────────┘  │
│                                                          │
│  ┌───────────────────────────────────────────────────┐   │
│  │         数据层 (JSON + SQLite → 保持不变)           │   │
│  │  knowledge/*.json | data/sessions.db | evidence.db │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘

┌──────────┐     ┌──────────┐
│  MySQL   │     │  Redis   │
│(Spring侧)│     │(Spring侧)│
└──────────┘     └──────────┘
```

## 2. 模块划分

### 2.1 Spring Boot 后端模块

```
mechatronics-admin/
├── mechatronics-common/        # 通用工具(RuoYi复用)
├── mechatronics-framework/     # 框架核心(RuoYi复用)
├── mechatronics-system/        # 系统管理(RuoYi复用，扩展)
├── mechatronics-chat/          # 【新增】聊天模块
│   ├── controller/
│   │   ├── ChatController.java        # 聊天 CRUD
│   │   └── ChatAgentController.java   # 消息发送/接收
│   ├── service/
│   │   ├── ChatService.java
│   │   ├── ConversationService.java
│   │   └── AgentClientService.java    # 调用 Python 的 HTTP 客户端
│   ├── domain/
│   │   ├── Conversation.java
│   │   └── Message.java
│   └── mapper/
│       ├── ConversationMapper.java
│       └── MessageMapper.java
├── mechatronics-agent/         # 【新增】智能体配置
│   ├── controller/
│   │   └── AgentConfigController.java
│   ├── service/
│   │   └── AgentConfigService.java
│   ├── domain/
│   │   └── AgentConfig.java
│   └── mapper/
│       └── AgentConfigMapper.java
├── mechatronics-graph/         # 【新增】图谱展示（代理）
│   ├── controller/
│   │   └── GraphController.java       # 代理 Python 图谱 API
│   └── service/
│       └── GraphService.java
├── mechatronics-scenario/      # 【新增】排故场景
│   ├── controller/
│   │   └── ScenarioController.java
│   └── service/
│       └── ScenarioService.java
├── mechatronics-statistics/    # 【新增】调用统计
│   ├── controller/
│   │   └── StatisticsController.java
│   ├── service/
│   │   └── CallLogService.java
│   ├── domain/
│   │   └── CallLog.java
│   └── mapper/
│       └── CallLogMapper.java
└── mechatronics-admin/         # 启动类
```

### 2.2 Python 智能体服务

```
python-agent/
├── main.py                     # FastAPI 入口
├── api/
│   ├── chat_api.py             # /api/agent/chat/*
│   ├── graph_api.py            # /api/agent/graph/*
│   ├── scenario_api.py         # /api/agent/scenario/*
│   └── student_api.py          # /api/agent/student/*
├── services/                   # 从现有 app/services/ 导入
│   ├── chat.py                 # 对话引擎（当前文件）
│   ├── intent.py               # 意图识别
│   ├── intent_handlers.py      # 意图处理器
│   ├── graph.py                # 图谱构建
│   ├── graph_update_engine.py  # 图谱更新引擎
│   ├── retrieval.py            # 知识检索
│   ├── scenario.py             # 排故场景
│   ├── scoring.py              # 评分
│   ├── safety.py               # 安全检查
│   ├── learner_context.py      # 学生画像
│   └── ...
├── knowledge/                  # 符号链接到原 knowledge/
├── data/                       # 符号链接到原 data/
└── requirements.txt            # FastAPI, uvicorn
```

**设计决策**：Python 服务最小化改动，FastAPI 仅作为 HTTP 包装层，核心业务逻辑直接复用 `app/services/` 中的现有函数。

### 2.3 Vue 3 前端模块

```
mechatronics-ui/
├── src/
│   ├── views/
│   │   ├── chat/               # 【新】聊天页面
│   │   │   ├── index.vue               # 聊天主页
│   │   │   ├── ChatPanel.vue           # 聊天面板
│   │   │   ├── ConversationList.vue    # 会话列表
│   │   │   └── MessageItem.vue         # 消息项
│   │   ├── graph/              # 【新】图谱页面
│   │   │   ├── index.vue               # 图谱主页
│   │   │   ├── ForceGraph.vue          # D3.js 力导向图组件
│   │   │   └── NodeDetail.vue          # 节点详情抽屉
│   │   ├── scenario/           # 【新】排故场景
│   │   │   ├── index.vue
│   │   │   └── ScenarioStage.vue
│   │   ├── agent/              # 【新】智能体配置
│   │   │   └── config.vue
│   │   └── statistics/         # 【新】调用统计
│   │       └── index.vue
│   ├── api/
│   │   ├── chat.js             # 聊天 API 封装
│   │   ├── graph.js            # 图谱 API 封装
│   │   ├── scenario.js         # 场景 API 封装
│   │   └── agent.js            # 智能体配置 API
│   ├── components/             # 复用组件
│   │   ├── MarkdownRenderer.vue # Markdown 渲染
│   │   └── ...
│   └── router/
│       └── index.js            # 路由配置
```

## 3. 调用链路

### 3.1 聊天消息

```
用户输入 "传感器灯亮但PLC无输入"
  │
  ├─ 1. Vue: POST /api/chat/message {conversationId, content, agentId}
  │
  ├─ 2. Spring ChatController:
  │     a. 权限校验（用户只能操作自己的会话）
  │     b. 保存用户消息到 MySQL
  │     c. AgentClientService.httpPost("http://agent:8000/api/agent/chat/message", body)
  │     d. 保存智能体回复到 MySQL
  │     e. 写调用日志 (userId, agentId, tokens, duration, success)
  │
  ├─ 3. Python FastAPI:
  │     a. chat_message(payload) → 现有 chat.py 逻辑
  │     b. 返回 {answer, highlighted_abilities, knowledge_refs, ...}
  │
  └─ 4. Vue: 渲染 Markdown 回复
```

### 3.2 图谱渲染

```
用户点击"岗位能力图谱"
  │
  ├─ 1. Vue: GET /api/graph/job
  │
  ├─ 2. Spring GraphController:
  │     a. AgentClientService.httpGet("http://agent:8000/api/agent/graph/job")
  │
  ├─ 3. Python FastAPI:
  │     a. build_job_ability_graph() → 返回 {nodes, edges}
  │
  └─ 4. Vue: D3.js ForceGraph 渲染
```

## 4. 数据流向

```
┌────────┐     ┌───────────────┐     ┌────────────┐
│  MySQL  │◄────│ Spring Boot   │     │ Python Agent│
│         │     │               │────►│             │
│session  │     │  chat CRUD    │ HTTP│  chat logic │
│message  │     │  user/auth    │     │  graph      │
│agent    │     │  statistics   │     │  retrieval  │
│call_log │     │               │◄────│  scenario   │
└────────┘     └───────┬───────┘     └──────┬─────┘
                       │                    │
                 ┌─────▼─────┐     ┌───────▼──────┐
                 │   Redis   │     │ SQLite + JSON │
                 │  session  │     │ (现有数据层)   │
                 │  cache    │     └──────────────┘
                 └───────────┘
```

**关键边界**：
- MySQL 只存 Spring Boot 侧数据：用户、会话、消息、配置、日志
- SQLite + JSON 只存 Python 侧数据：知识库、图谱节点、证据事件、学习记录
- Python 侧数据保持独立，不迁移到 MySQL，降低风险

## 5. Python 服务接口设计

Python FastAPI 暴露接口给 Spring Boot 调用（**不暴露给前端**）：

| 方法 | 路径 | 对应现有函数 |
|------|------|------------|
| POST | `/api/agent/chat/start` | chat_start() |
| POST | `/api/agent/chat/message` | chat_message() |
| POST | `/api/agent/chat/stream` | chat_message() SSE |
| GET | `/api/agent/graph/job` | build_job_ability_graph() |
| GET | `/api/agent/graph/student?sid=...` | build_student_ability_graph() |
| GET | `/api/agent/scenarios` | list_scenarios() |
| POST | `/api/agent/scenario/start` | start_scenario() |
| POST | `/api/agent/scenario/step` | step_scenario() |
| GET | `/api/agent/quiz` | public_questions() |
| POST | `/api/agent/quiz/personalized` | personalized_quiz() |
| POST | `/api/agent/explain` | explain() |
| POST | `/api/agent/plan/personalized` | personalized_plan() |
| GET | `/api/agent/health` | health check |