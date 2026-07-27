# API 接口设计 v1.0

## 设计原则

1. 所有前端请求到 Spring Boot，Spring Boot 代理到 Python Agent
2. Python Agent 接口仅供 Spring Boot 调用（内网，不暴露到前端）
3. RESTful 风格，JSON 格式，UTF-8 编码
4. 分页接口统一 `pageNum`/`pageSize`
5. 所有接口需登录（除 health）

## 1. Spring Boot → 前端接口

### 1.1 聊天模块

| 方法 | 路径 | 说明 | 请求体/参数 |
|------|------|------|-----------|
| GET | `/api/chat/conversations` | 当前用户会话列表 | ?pageNum=1&pageSize=20 |
| POST | `/api/chat/conversations` | 新建会话 | `{agentId, title?}` |
| PUT | `/api/chat/conversations/{id}` | 重命名会话 | `{title}` |
| DELETE | `/api/chat/conversations/{id}` | 删除会话 | - |
| GET | `/api/chat/conversations/{id}/messages` | 获取会话消息 | ?pageNum=1&pageSize=50 |
| POST | `/api/chat/conversations/{id}/messages` | 发送消息 | `{content}` → 返回完整智能体回复 |

**POST /messages 响应示例**：

```json
{
  "id": 1001,
  "role": "assistant",
  "content": "先确认 DC24V 和 0V...",
  "tokens": 156,
  "highlighted_abilities": ["sensor_wiring_judgement", "plc_input_common_terminal"],
  "knowledge_refs": [{"id": "K003", "title": "PNP/NPN 接线规范"}],
  "safety_notice": null
}
```

### 1.2 图谱模块（代理到 Python）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/graph/job` | 岗位能力图谱 |
| GET | `/api/graph/student` | 学生个人图谱 |
| GET | `/api/graph/job/versions` | 图谱版本列表 |
| GET | `/api/graph/job/versions/diff` | 版本差异 |
| POST | `/api/graph/job/ingest` | 导入 JD 材料（教师） |
| POST | `/api/graph/job/proposals/confirm` | 确认图谱提案（教师） |

### 1.3 排故场景（代理到 Python）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/scenarios` | 场景列表 |
| POST | `/api/scenarios/start` | 启动场景 |
| POST | `/api/scenarios/step` | 提交步骤选择 |

### 1.4 自测（代理到 Python）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/quiz` | 获取自测题目 |
| POST | `/api/quiz/submit` | 提交答案 |
| POST | `/api/quiz/personalized` | 获取个性化题目 |

### 1.5 培养方案（代理到 Python）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/plan/personalized` | 获取培养方案 |

### 1.6 智能体配置

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/agent/config` | 智能体配置列表 | 管理员 |
| GET | `/api/agent/config/{id}` | 单个配置 | 管理员 |
| POST | `/api/agent/config` | 创建配置 | 管理员 |
| PUT | `/api/agent/config/{id}` | 更新配置 | 管理员 |
| DELETE | `/api/agent/config/{id}` | 删除配置 | 管理员 |

### 1.7 调用统计

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/statistics/call-logs` | 调用日志列表 | 管理员 |
| GET | `/api/statistics/summary` | 统计概要 | 管理员 |

### 1.8 知识搜索（代理到 Python）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/knowledge/search?query=PLC` | 知识库搜索 |

## 2. Python Agent 接口（仅 Spring Boot 访问）

### 2.1 聊天

| 方法 | 路径 | 请求体 |
|------|------|--------|
| POST | `/api/agent/chat/start` | `{session_id, agent_config?}` |
| POST | `/api/agent/chat/message` | `{session_id, message, context?}` |
| POST | `/api/agent/chat/stream` | 同上，SSE 流式 |

### 2.2 图谱

| 方法 | 路径 |
|------|------|
| GET | `/api/agent/graph/job` |
| GET | `/api/agent/graph/student?session_id=...` |
| POST | `/api/agent/graph/job/ingest` |
| POST | `/api/agent/graph/job/proposals/confirm` |

### 2.3 场景 / 自测 / 方案

| 方法 | 路径 |
|------|------|
| GET | `/api/agent/scenarios` |
| POST | `/api/agent/scenario/start` |
| POST | `/api/agent/scenario/step` |
| GET | `/api/agent/quiz` |
| POST | `/api/agent/quiz/personalized` |
| POST | `/api/agent/plan/personalized` |
| GET | `/api/agent/knowledge/search?query=...` |

### 2.4 健康检查

| 方法 | 路径 | 响应 |
|------|------|------|
| GET | `/api/agent/health` | `{"status":"ok","version":"0.1.0"}` |

## 3. 通用响应格式

### 成功

```json
{
  "code": 200,
  "msg": "操作成功",
  "data": { ... }
}
```

### 分页

```json
{
  "code": 200,
  "msg": "查询成功",
  "rows": [...],
  "total": 100
}
```

### 错误

```json
{
  "code": 500,
  "msg": "智能体服务超时"
}
```

## 4. 错误码

| code | 说明 |
|------|------|
| 200 | 成功 |
| 400 | 参数错误 |
| 401 | 未登录 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
| 503 | Python 智能体服务不可用 |
| 504 | Python 智能体服务超时 |