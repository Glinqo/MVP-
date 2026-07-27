# 数据库设计 v1.0

## 设计原则

1. **MySQL 存储 Spring Boot 侧数据**：用户、会话、消息、智能体配置、日志
2. **SQLite + JSON 保持不变**：知识库、图谱节点、证据事件、学习记录（Python 侧）
3. **Redis 缓存**：用户 token、在线状态、接口限流

## 1. 新增表（需创建）

### 1.1 智能体配置表 `me_agent_config`

```sql
CREATE TABLE me_agent_config (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(64)  NOT NULL COMMENT '智能体名称',
    description VARCHAR(512) DEFAULT '' COMMENT '智能体描述',
    avatar      VARCHAR(256) DEFAULT '' COMMENT '头像URL',
    system_prompt TEXT        NOT NULL COMMENT '系统提示词',
    model_name  VARCHAR(64)  NOT NULL DEFAULT 'gpt-3.5-turbo' COMMENT '模型名称',
    temperature DECIMAL(3,2) NOT NULL DEFAULT 0.7 COMMENT '温度参数',
    max_history INT          NOT NULL DEFAULT 10 COMMENT '最大历史消息数',
    use_knowledge_base TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否启用知识库（第二版）',
    enabled     TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '启用状态 0=停用 1=启用',
    create_by   VARCHAR(64)  DEFAULT '' COMMENT '创建人',
    create_time DATETIME     DEFAULT CURRENT_TIMESTAMP,
    update_by   VARCHAR(64)  DEFAULT '',
    update_time DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '智能体配置表';
```

### 1.2 会话表 `me_conversation`

```sql
CREATE TABLE me_conversation (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT       NOT NULL COMMENT '用户ID',
    agent_id    BIGINT       NOT NULL COMMENT '智能体ID',
    title       VARCHAR(256) NOT NULL DEFAULT '新对话' COMMENT '会话标题',
    status      VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT 'active/deleted',
    create_time DATETIME     DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_agent_id (agent_id),
    INDEX idx_user_agent (user_id, agent_id)
) COMMENT '会话表';
```

### 1.3 消息表 `me_message`

```sql
CREATE TABLE me_message (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id BIGINT       NOT NULL COMMENT '会话ID',
    role            VARCHAR(16)  NOT NULL COMMENT 'user/assistant/system',
    content         MEDIUMTEXT   NOT NULL COMMENT '消息内容',
    tokens          INT          DEFAULT 0 COMMENT 'Token 用量',
    highlighted_abilities JSON  DEFAULT NULL COMMENT '命中的能力节点',
    knowledge_refs       JSON  DEFAULT NULL COMMENT '引用的知识条目',
    safety_notice        TEXT  DEFAULT NULL COMMENT '安全提示',
    create_time     DATETIME     DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_create_time (create_time)
) COMMENT '消息表';
```

### 1.4 调用日志表 `me_call_log`

```sql
CREATE TABLE me_call_log (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT       NOT NULL COMMENT '用户ID',
    agent_id        BIGINT       NOT NULL COMMENT '智能体ID',
    conversation_id BIGINT       NOT NULL COMMENT '会话ID',
    message_id      BIGINT       COMMENT '消息ID',
    model_name      VARCHAR(64)  COMMENT '模型名称',
    request_body    MEDIUMTEXT   COMMENT '请求体（脱敏后）',
    response_body   MEDIUMTEXT   COMMENT '响应体（脱敏后）',
    tokens_in       INT          DEFAULT 0 COMMENT '输入 Token',
    tokens_out      INT          DEFAULT 0 COMMENT '输出 Token',
    duration_ms     INT          DEFAULT 0 COMMENT '响应时长(毫秒)',
    success         TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否成功',
    error_type      VARCHAR(64)  DEFAULT '' COMMENT '错误类型',
    error_msg       TEXT         COMMENT '错误详情',
    ip_address      VARCHAR(45)  DEFAULT '' COMMENT 'IP地址',
    create_time     DATETIME     DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_agent_id (agent_id),
    INDEX idx_create_time (create_time),
    INDEX idx_success (success)
) COMMENT '调用日志表';
```

### 1.5 学生技能状态表 `me_student_ability`（待确认）

```sql
CREATE TABLE me_student_ability (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT       NOT NULL COMMENT '学生用户ID',
    ability_id      VARCHAR(64)  NOT NULL COMMENT '能力节点ID',
    status          VARCHAR(16)  NOT NULL DEFAULT 'unknown' COMMENT 'unknown/weak/improving/mastered',
    chat_count      INT          DEFAULT 0 COMMENT '训练对话次数',
    weak_count      INT          DEFAULT 0 COMMENT '薄弱命中次数',
    mastered_count  INT          DEFAULT 0 COMMENT '掌握命中次数',
    last_event_id   VARCHAR(64)  DEFAULT '' COMMENT '最后学习事件ID',
    update_time     DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_ability (user_id, ability_id),
    INDEX idx_user_id (user_id)
) COMMENT '学生技能状态表（MySQL侧缓存，权威源在Python侧）';
```

> **待确认项**：此表为 MySQL 侧缓存副本，权威源是 Python 侧的 SQLite `ability_state_cache`。是否需要在 MySQL 侧维护取决于前端是否需要直接从 Spring Boot 查询学生技能状态，而非每次代理到 Python。

## 2. 复用 RuoYi 表

| 表名 | 用途 | 是否修改 |
|------|------|----------|
| `sys_user` | 用户表 | 不修改 |
| `sys_role` | 角色表 | 不修改 |
| `sys_menu` | 菜单权限 | 新增菜单数据 |
| `sys_oper_log` | 操作日志 | 不修改（聊天调用写入 `me_call_log`） |

## 3. ER 关系

```
sys_user (RuoYi)
  │
  ├── 1:N ── me_conversation
  │             │
  │             └── 1:N ── me_message
  │
  ├── 1:N ── me_call_log
  │
  └── 1:N ── me_student_ability (待确认)

me_agent_config
  │
  └── 1:N ── me_conversation
```

## 4. Python 侧数据（不变）

以下数据保持现有存储方式，不做迁移：

| 数据 | 存储方式 | 位置 |
|------|---------|------|
| 能力节点定义 | JSON | `knowledge/ability_nodes.json` |
| 知识库文章 | JSON | `knowledge/knowledge_50.json` |
| 雷达维度 | JSON | `knowledge/radar_dimensions.json` |
| 岗位画像 | JSON | `knowledge/job_profiles.json` |
| 技能词典 | JSON | `knowledge/job_skill_lexicon.json` |
| 问题模式 | JSON | `knowledge/problem_patterns.json` |
| 排故场景 | JSON | `knowledge/troubleshooting_scenarios.json` |
| 会话事件 | SQLite | `data/sessions.db` |
| 能力状态缓存 | SQLite | `data/sessions.db` (ability_state_cache) |
| 会话记忆 | SQLite | `data/sessions.db` (session_memory) |
| 证据事件 | SQLite | `data/evidence/evidence.db` |
| 图谱快照 | SQLite | `data/evidence/evidence.db` (snapshots) |
| 图谱提案 | SQLite | `data/evidence/evidence.db` (proposals) |
| 审计日志 | SQLite + JSONL | `data/evidence/` |

## 5. 索引策略

### MySQL 新增索引

- `me_conversation`: `idx_user_id`, `idx_agent_id`, `idx_user_agent`
- `me_message`: `idx_conversation_id`, `idx_create_time`
- `me_call_log`: `idx_user_id`, `idx_agent_id`, `idx_create_time`, `idx_success`
- `me_student_ability`: `uk_user_ability` (UNIQUE), `idx_user_id`

### Python 侧（现有索引不变）

- SQLite 已有自动索引（PRIMARY KEY + UNIQUE constraints）
- FAISS 向量索引：`knowledge/vector_index/faiss.index`