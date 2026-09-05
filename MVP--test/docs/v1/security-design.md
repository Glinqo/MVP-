# 安全设计 v1.0

## 1. 风险分析与处理

### 风险 1：用户通过修改 conversationId 访问他人会话

**风险等级**：高
**处理方案**：
- Spring Boot 侧：查询会话时追加 `WHERE user_id = ${当前登录用户ID}` 条件
- 即使前端传入其他用户的 conversationId，SQL 也不会返回数据
- 删除/重命名操作同样校验所有权

### 风险 2：前端直接传入 userId 导致越权

**风险等级**：高
**处理方案**：
- 所有接口从 `SecurityContextHolder` 获取当前登录用户
- 忽略请求体中的 `userId`、`user_id` 等字段
- 消息发送、会话创建等接口不从请求体读用户身份

### 风险 3：Markdown/HTML 内容导致 XSS

**风险等级**：中
**处理方案**：
- 前端使用 `marked.js` + `DOMPurify` 渲染 Markdown
- 禁止原始 HTML 标签（如 `<script>`、`<iframe>`）
- 链接加 `rel="noopener noreferrer" target="_blank"`
- Python 侧输出也可做一次 HTML 实体转义

### 风险 4：API Key 泄露

**风险等级**：高
**处理方案**：
- API Key 仅存储在 Python 服务的 `.env` 文件中
- 不进入 MySQL 数据库
- `me_call_log` 不记录完整请求体，脱敏后写入
- 前端代码中不出现任何 API Key
- Spring Boot 不转发 API Key 给前端

### 风险 5：文件上传伪造类型

**风险等级**：中（第一版不实现文件上传）

**处理方案（第二版预留）**：
- 服务端校验 MIME 类型 + 文件头魔数
- 白名单：PDF、DOCX、MD、TXT、PNG、JPG
- 重命名存储，不保留原始文件名

### 风险 6：文件过大

**风险等级**：低
**处理方案**：
- Spring Boot 配置 `spring.servlet.multipart.max-file-size=10MB`
- 前端在上传前校验文件大小

### 风险 7：Prompt Injection

**风险等级**：中
**处理方案**：
- Python 侧 `safety.py` 现有安全过滤保持
- 用户消息中的 "忽略之前的指令"、"system:" 等模式检测
- 不将用户消息直接拼接到系统提示词之前

### 风险 8：智能体服务请求超时

**风险等级**：中
**处理方案**：
- Spring Boot 设置 HTTP 客户端超时 30s
- 超时后返回标准化错误：`{"code":504, "msg":"智能体服务超时，请重试"}`
- 写入 `me_call_log` 记录超时

### 风险 9：重复点击导致重复消息

**风险等级**：中
**处理方案**：
- 前端：发送按钮点击后立即 disabled，收到回复后恢复
- 后端：消息去重，相同 `(conversationId, userId, content)` 在 5 秒内不重复处理

### 风险 10：SSE 断开后重复回复（第二版）

**处理方案**：
- 客户端维护消息接收状态
- 断线重连时先查询最后一条消息 ID，从断点续传

### 风险 11：日志泄露用户消息或密钥

**风险等级**：中
**处理方案**：
- `me_call_log` 的 `request_body` 和 `response_body` 做脱敏处理
- 日志中不出现 API Key
- 生产环境日志级别 INFO，不打印完整消息体

### 风险 12：Python 服务暴露到公网

**风险等级**：高
**处理方案**：
- Python FastAPI 只监听 `127.0.0.1` 或内网 IP
- 防火墙不开放 Python 服务端口
- Spring Boot 通过内网 HTTP 访问

### 风险 13：恶意用户频繁调用模型

**风险等级**：中
**处理方案**：
- Spring Boot 侧 Redis 限流：每用户每分钟 ≤ 10 次
- `me_call_log` 记录每次调用，可追溯

## 2. 安全架构分层

```
┌──────────────────────────────────┐
│        前端 (Vue 3)              │
│  ├── 输入校验 (前端)              │
│  ├── XSS 防护 (DOMPurify)        │
│  └── Token 存储 (HttpOnly 建议)   │
└──────────────┬───────────────────┘
               │ HTTPS + JWT
┌──────────────▼───────────────────┐
│     Spring Boot (Java)           │
│  ├── Spring Security (RuoYi)     │
│  ├── 权限注解 @PreAuthorize      │
│  ├── 数据权限 (user_id 过滤)      │
│  ├── 接口限流 (Redis)             │
│  ├── 请求日志 (me_call_log)       │
│  └── 超时控制 (30s)              │
└──────────────┬───────────────────┘
               │ 内网 HTTP
┌──────────────▼───────────────────┐
│     Python FastAPI (Agent)       │
│  ├── API Key 隔离 (.env)         │
│  ├── Prompt 安全过滤 (safety.py) │
│  └── 本机监听 (127.0.0.1)        │
└──────────────────────────────────┘
```

## 3. 第一版安全清单

| 措施 | 状态 |
|------|------|
| 会话归属校验 (WHERE user_id = ?) | 必须 |
| 用户身份从 SecurityContext 获取 | 必须 |
| Markdown XSS 防护 | 必须 |
| API Key 不入库 | 必须 |
| Python 服务不暴露公网 | 必须 |
| 接口调用日志写入 | 必须 |
| 30s 超时控制 | 必须 |
| 前端防抖（按钮 disabled） | 必须 |
| Redis 限流 | 建议 |
| 日志脱敏 | 建议 |
| 消息去重 | 建议 |