# 待确认问题 v1.0

本文档记录设计过程中无法基于现有代码确认的问题。后续需与项目负责人逐一确认。

---

## 1. 架构层面

### Q1: RuoYi-Vue-Plus 具体版本？
**影响**：框架初始化、Maven 依赖、前端项目结构
**建议**：使用最新稳定版（如 v5.x）

### Q2: Python Agent 是否需要单独部署为独立服务？
**影响**：部署架构（Docker Compose 编排）
**当前假设**：Python Agent 作为独立进程启动 FastAPI，与 Spring Boot 通过 localhost HTTP 通信

### Q3: 是否需要支持多智能体切换？（第一版还是第二版）
**影响**：前端会话列表是否需要显示"所属智能体"，新建会话时是否需要选择智能体
**当前假设**：第一版单智能体，但数据库层面预留 `agent_id` 字段

---

## 2. 数据层面

### Q4: 学生技能状态表 `me_student_ability` 是否需要？
**影响**：MySQL 表数量、Spring Boot 接口设计
**当前假设**：**暂不创建**。前端通过 Spring Boot 代理到 Python Agent 获取学生能力状态，不在 MySQL 侧保留副本。理由：Python 侧的 `ability_state_cache` 已经是权威源，维护双写增加复杂度。

### Q5: 现有 `data/sessions/` 目录下的数百个 JSON 会话文件如何处理？
**影响**：数据迁移策略
**建议**：不迁移。历史 JSON 文件保留在 Python 侧，Python Agent 仍可读取作为学习证据。MySQL 侧仅存储网页系统新产生的会话。

### Q6: 知识库文章更新频率？
**影响**：是否需要在 Spring Boot 侧做知识库 CRUD，还是继续由 Python 侧独立管理
**当前假设**：第一版知识库由 Python 侧独立管理（JSON 文件），Spring Boot 仅代理搜索请求

---

## 3. 接口层面

### Q7: 前端聊天消息分页策略？
**影响**：API 设计、前端滚动加载
**建议**：第一版简单分页（一次性加载全量消息），会话消息量预计不大（< 100 条）。第二版改为滚动加载。

### Q8: Spring Boot 代理 Python 的 session_id 生成策略？
**影响**：会话 ID 由 Spring Boot 生成还是 Python 生成
**建议**：Spring Boot 生成 `conversationId`（MySQL 主键），持久化存储。Python 侧 `session_id` 使用 Spring Boot 传来的 ID，用于 SQLite 记录学习事件。

---

## 4. 前端层面

### Q9: 是否需要保留现有 landing page（身份选择 + 岗位选择）？
**影响**：前端路由设计
**当前假设**：不保留。改用 RuoYi 登录页 + 权限体系。学生登录后默认进入智能体聊天页。

### Q10: 现有 D3.js 图谱代码迁移到 Vue 的工作量？
**影响**：前端开发排期
**建议**：`graph-renderer.js` 中的 D3 逻辑封装为 Vue 组件，核心渲染代码（约 400 行）基本可复用，主要工作在外层组件化和 Vue 生命周期管理。

---

## 5. 部署与运维

### Q11: 第一版是否需要 Docker 化？
**影响**：Phase 10 排期
**当前假设**：第一版不需要。开发阶段 Spring Boot + Python 直接本机启动。第二版再做 Docker Compose。

### Q12: 生产环境 Python Agent 是否需要多实例？
**影响**：负载均衡策略
**当前假设**：第一版单实例。Python Agent 的并发瓶颈在 LLM API 调用（外部），不在本地计算。

---

## 6. 兼容性

### Q13: 现有 E2E 测试和 Eval 体系是否需要保留？
**影响**：测试策略
**建议**：保留。`evals/` 目录和 `tests/` 目录继续在 Python 侧运行，不纳入 Spring Boot 测试体系。网页系统新增独立的 API 测试。

### Q14: 现有 GitHub Actions / CI 是否需要调整？
**影响**：CI/CD 配置
**当前假设**：第一版不修改 CI。后续第二版增加 Spring Boot + Vue 构建流程。

---

## 7. 待确认总结

| 编号 | 问题 | 建议处理 | 阻塞项 |
|------|------|----------|--------|
| Q1 | RuoYi 版本 | 最新 v5.x | Phase 2 |
| Q2 | Python 独立服务 | 是 | Phase 2 |
| Q3 | 多智能体支持 | 第一版不做，DB预留 | Phase 3 |
| Q4 | 学生技能表 | 暂不创建 | Phase 3 |
| Q5 | 历史会话迁移 | 不迁移 | 无 |
| Q6 | 知识库管理方式 | Python 独立管理 | 无 |
| Q9 | Landing page | 不保留，用RuoYi登录 | Phase 4 |
| Q10 | D3.js 迁移 | 核心逻辑可复用 | Phase 4 |