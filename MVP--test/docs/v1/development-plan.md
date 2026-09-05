# 开发计划 v1.0

## 阶段总览

```
Phase 1:         Phase 2:        Phase 3:        Phase 4:         Phase 5:
需求与设计       基础环境        数据库+会话     聊天前端         接入Python
(当前)          RuoYi跑通       +模拟回复       +代理层         智能体
   1周             1周             2周             2周             2周

Phase 6:         Phase 7:        Phase 8:        Phase 9:         Phase 10:
SSE流式         文件/知识库      权限/安全        自动化测试       部署上线
（第二版）       （第二版）       （完善）         （完善）         （第二版）
```

## Phase 1 — 需求与系统设计（当前）

**目标**：完成需求分析、架构设计、数据库设计、接口设计。输出设计文档。

**主要任务**：
- [x] 分析当前仓库结构和代码基线
- [x] 明确第一版需求范围
- [x] 设计系统整体架构
- [x] 设计数据库
- [x] 设计 API 接口
- [x] 设计 UI 页面
- [x] 安全风险分析
- [x] 制定开发阶段

**交付物**：`docs/v1/` 下 8 份设计文档

**前置条件**：无

**验收标准**：设计文档完整、逻辑一致、无明显偏差

## Phase 2 — 基础环境运行

**目标**：RuoYi-Vue-Plus 框架跑通，Python Agent 服务独立启动。

**主要任务**：
1. 克隆 RuoYi-Vue-Plus，修改包名和项目名为 `mechatronics-admin`
2. 配置 MySQL 数据库连接
3. 配置 Redis 连接
4. 跑通登录/用户管理/角色管理等基础功能
5. Python 侧：安装 FastAPI + uvicorn，创建 `main.py` 入口
6. Python 侧：导入现有 `app/services/` 模块，验证可导入
7. 跑通 `GET /api/agent/health`

**交付物**：
- Spring Boot 项目可启动
- Python FastAPI 项目可启动
- 两个服务均通过 health check

**前置条件**：数据库设计完成，开发环境（JDK 17+, Maven, Python 3.10+, Node 18+）就绪

**风险**：RuoYi 框架版本兼容性问题
**验收标准**：两个服务各自启动成功，health 接口返回 ok

## Phase 3 — 数据库与会话模块（模拟回复）

**目标**：MySQL 表创建，会话 CRUD + 消息存储，用模拟回复打通流程。

**主要任务**：
1. 执行 SQL 创建 `me_agent_config`, `me_conversation`, `me_message`, `me_call_log` 表
2. 实现 `ConversationService`：创建/列表/重命名/删除（带用户权限校验）
3. 实现 `MessageService`：查询会话消息（分页）
4. 实现 `ChatAgentController`：接收消息 → 保存用户消息 → 返回模拟回复 → 保存助手消息
5. 模拟回复：固定文本 "你好，我是机电培训AI助手（模拟回复）"
6. 实现 `AgentClientService`：HTTP 客户端骨架（暂不真正调用 Python）
7. 接口全部通过 Postman 测试

**交付物**：
- 4 张 MySQL 表创建完成
- 会话 CRUD API 全部可用
- 消息发送/接收 API 可用（模拟回复）

**前置条件**：Phase 2 完成，MySQL 服务可用

**风险**：无
**验收标准**：
- POST 创建会话 → 返回 sessionId
- GET 会话列表 → 返回用户专属会话
- POST 发送消息 → 返回模拟回复
- GET 会话消息 → 返回消息历史
- 用户 A 无法看到用户 B 的会话

## Phase 4 — 聊天前端 + 代理层

**目标**：Vue 3 聊天页面开发，Spring Boot 代理层完善，前后端联调。

**主要任务**：
1. Vue 项目创建，路由配置，登录拦截
2. `ConversationList.vue`：会话列表 + 新建/重命名/删除
3. `ChatPanel.vue`：消息渲染（Markdown）+ 自动滚动
4. `MessageItem.vue`：用户消息 + 智能体消息样式
5. `ChatInput.vue`：输入框 + Enter 发送 + 按钮防抖
6. `MarkdownRenderer.vue`：集成 marked.js + DOMPurify
7. 前端 API 封装（`api/chat.js`）
8. 前后端联调：登录 → 创建会话 → 发送消息 → 查看回复

**交付物**：
- 聊天页面完整可用（模拟回复）
- 会话列表持久化
- Markdown 渲染正常

**前置条件**：Phase 3 完成

**风险**：RuoYi-Vue-Plus 前端结构调整工作量大
**验收标准**：
- 登录后进入聊天页
- 新建会话 + 删除会话正常
- 发送消息收到回复
- 刷新页面后会话和消息仍在
- 切换会话消息不串流

## Phase 5 — 接入 Python 智能体

**目标**：Spring Boot 通过 HTTP 调用 Python Agent，替换模拟回复为真实智能体回复。

**主要任务**：
1. Python 侧：完善 FastAPI 路由，封装所有现有服务函数
2. `AgentClientService`：实现 HTTP 客户端（OkHttp/WebClient）
3. 配置 Python Agent 地址（`application.yml`）
4. 超时控制 30s
5. 错误处理：Python 不可用时返回友好提示
6. `CallLogService`：记录每次调用日志（user/agent/model/tokens/duration）
7. 端到端联调：前端 → Spring Boot → Python → 返回 → 前端渲染

**交付物**：
- Python Agent 所有接口通过 FastAPI 可用
- Spring Boot → Python 调用链路通畅
- 调用日志表有数据

**前置条件**：Phase 4 完成，Python 智能体可独立运行

**风险**：
- Python 模块导入路径适配（中等）
- Python Agent 可能需要额外依赖（低）
**验收标准**：
- 发送 "传感器灯亮但PLC无输入" → 返回真实诊断回答
- 命中能力节点正确
- 调用日志有记录

## Phase 6 — SSE 流式输出（第二版）

**目标**：智能体回复改为 SSE 逐 token 推送。

**主要任务**：
1. Python 侧：`/api/agent/chat/stream` SSE 端点
2. Spring Boot 侧：转发 SSE 流到前端
3. 前端：`EventSource` 或 `fetch` 接收流 → 逐字渲染
4. 停止生成功能
5. 重新生成功能

**交付物**：流式聊天体验（类似 ChatGPT）

**前置条件**：Phase 5 完成

**风险**：SSE 代理层实现复杂度中等

## Phase 7 — 文件与知识库（第二版）

**目标**：文件上传、解析、知识库检索、回答引用。

**主要任务**：略（第二版设计时细化）

## Phase 8 — 权限、安全与日志（完善）

**目标**：完善安全机制（第三版上线前）。

**主要任务**：
1. Redis 限流（每用户每分钟 10 次）
2. 日志脱敏（API Key、用户消息体）
3. 消息去重
4. 权限测试：学生不能访问管理端接口

## Phase 9 — 自动化测试（完善）

**主要任务**：
1. Spring Boot 单元测试（ConversationService, MessageService）
2. API 集成测试（Postman Collection / JUnit）
3. Python Agent 回归测试（复用现有 test_*.py）

## Phase 10 — 部署上线（第二版）

**主要任务**：
1. Docker Compose 编排（MySQL + Redis + Spring Boot + Python Agent）
2. Nginx 反向代理配置
3. 环境变量管理
4. 上线检查清单