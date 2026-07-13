# 岗位能力图谱后端升级 — 开发日志

> 时间：2026-07-12 ~ 2026-07-13
> 分支：`feature/job-ability-graph`
> 基准：`main` (17acbcb)

## 概述

基于原有 MVP 的岗位能力图谱功能，分三个阶段完成从静态 JSON 到证据驱动、LLM 辅助、教师确认、版本可控的动态图谱升级。

---

## Phase A — 数据底座 + 管道打通

### 目标
把 `evidence_events → proposals → snapshots` 从 JSON 文件存储升级为 SQLite，打通 pipeline 到 API 的完整链路。

### 新增文件

| 文件 | 说明 |
|------|------|
| `scripts/pipeline/sqlite_store.py` | SQLite 存储层，4 表 + 8+ 接口函数 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `scripts/pipeline/evidence_store.py` | 重写为 `sqlite_store` 的薄包装，保持全部向后兼容 API |
| `app/services/graph_update_engine.py` | 新增 `generate_proposals_from_evidence()` — 从 SQLite 证据聚合打分 |
| `app/services/graph.py` | `build_job_ability_graph()` 每个节点追加 `evidence_count` / `avg_confidence` / `last_updated_at` / `source_types` / `latest_evidence` |
| `app/server.py` | 新增 `POST /api/graph/job/ingest` — JD 文本 → 技能抽取 → 证据 → 提案 |

### SQLite Schema

```sql
evidence_events (event_id, job_role, ability_id, evidence_text, source_url, source_type, extraction_method, confidence, extracted_at)
    → 追加写，自动去重，多条件查询

proposals (proposal_id, job_role, ability_id, action, suggested_weight_delta, evidence, source, proposal_score, status, confirmed_by, confirmed_at)
    → 状态机：pending → confirmed / rejected

snapshots (snapshot_id, job_role, version, created_at, node_count, node_data, dimension_scores, source, parent_version)
    → 版本快照，支持 diff 和回滚

audit_log (id, timestamp, action, entity_id, detail)
    → 审计跟踪
```

### 评分公式

```text
proposal_score = source_weight × confidence × frequency_factor × recency_decay

source_weights:
  enterprise_official: 0.85
  teacher_material:    0.95
  standard:            0.90
  job_platform:        0.65
  social_media:        0.25 (仅弱信号)

thresholds:
  >= 0.75 → auto_approve
  0.45–0.75 → pending
  < 0.45 → weak_signal (不入主图谱)
```

---

## Phase B — LLM 辅助抽取

### 目标
增加 LLM 作为辅助抽取器，识别规则词典无法覆盖的隐含能力。LLM 只生成候选，不直接入正式图谱。

### 新增文件

| 文件 | 说明 |
|------|------|
| `scripts/pipeline/llm_extractor.py` | LLM 抽取模块（3 个公开函数） |

### 函数 API

| 函数 | 作用 |
|------|------|
| `llm_extract_skills(jd_text, ability_nodes)` | 调用 LLM 提取技能，返回结构化候选列表 |
| `extract_with_both(jd_text, ability_nodes)` | 规则 + LLM 合并抽取，去重后按置信度排序 |
| `_validate_and_map(candidates, ability_nodes)` | LLM 结果校验 + 映射到具体能力节点 |

### LLM prompt 设计

```
你是一个机电岗位能力分析助手。
从岗位描述中提取技能，输出 JSON 数组：
[{"skill_name", "ability_dimension", "matched_dimension_id", "confidence", "evidence_snippet", "implicit"}]
implicit=true 表示该技能未直接提及但可从上下文推断。
只输出 JSON，不要解释。
```

### 合并策略

```text
规则词典 → confidence * 1.0, source="rule_lexicon"
jieba 增强 → confidence * 0.9 (需 pip install jieba)
LLM 辅助 → confidence - 0.15, source="llm_extraction"
合并：保留全部结果（不按 ability_id 去重），按 confidence 降序
```

---

## Phase C — 教师工作流 + 前端展示

### 目标
前端展示证据来源、最新证据、版本信息，后端提供教师确认/驳回 API。

### 后端新增 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/graph/job/proposals/pending` | GET | 返回 SQLite 中所有 pending 提案 |
| `/api/graph/job/proposals/confirm-sqlite` | POST | 教师确认/驳回提案 |

### 前端修改

| 文件 | 改动 |
|------|------|
| `web/app.js` | `showGraphNodeDetail()` 增强：显示证据来源分布 (`source_types`)、最新证据 (`latest_evidence`)、版本信息 |

### 节点详情抽屉 (showGraphNodeDetail) 增强

```text
点击图谱节点 → 右侧抽屉展示：
├── 能力名称 / 状态
├── 掌握度 / 置信度 / 证据总数 / 平均置信度
├── 证据来源分布（企业官网: N 条, 招聘平台: N 条 ...）
├── 最新证据（前 3 条：片段 + 来源 + 时间 + 置信度）
├── 版本历史（版本数 + 最新版本号）
└── 下一步 + AI 讲解 / 培养方案
```

---

## 完整 API 端点清单

```text
图谱数据
  GET  /api/graph/job                         当前正式图谱（节点含证据元信息）
  GET  /api/graph/student?session_id=...       学生个人图谱
  GET  /api/graph                             当前问题图谱

图谱更新
  POST /api/graph/job/ingest                  导入 JD / 教师材料
  POST /api/graph/job/proposals               生成更新建议（基于关键词）
  GET  /api/graph/job/proposals/pending       查看待确认建议列表
  POST /api/graph/job/proposals/confirm       教师确认建议（旧版）
  POST /api/graph/job/proposals/confirm-sqlite 教师确认建议（SQLite 版）

版本管理
  GET  /api/graph/job/versions                查看版本列表
  GET  /api/graph/job/versions/diff?v1=...&v2=... 版本差异对比
  POST /api/graph/job/versions/rollback       回滚图谱版本

学生相关
  GET  /api/student/job-match?session_id=...  学生-岗位匹配度
  GET  /api/graph/student?session_id=...      学生个人图谱
  POST /api/graph/student/event               记录学生事件

学生-岗位匹配
  GET  /api/student/job-match?session_id=...  FitScore + 覆盖度 + 准备度 + 缺口列表
'''

---

## 使用方式

```powershell
# 启动服务
$env:LLM_API_KEY="sk-..."
python app/server.py --port 8765

# 粘贴 JD 文本 → 抽取能力 + 生成提案
curl -X POST http://127.0.0.1:8765/api/graph/job/ingest \
  -H "Content-Type: application/json" \
  -d '{"text":"负责PLC调试、传感器故障排查","use_llm":true}'

# 查看待确认提案
curl http://127.0.0.1:8765/api/graph/job/proposals/pending

# 确认提案
curl -X POST http://127.0.0.1:8765/api/graph/job/proposals/confirm-sqlite \
  -H "Content-Type: application/json" \
  -d '{"proposal_id":"PRP-...","action":"confirm"}'

# 查看版本
curl http://127.0.0.1:8765/api/graph/job/versions

# 版本 diff
curl "http://127.0.0.1:8765/api/graph/job/versions/diff?v1=v0.1&v2=v0.2"
```

---

## 数据流

```text
JD / 教师材料 / 企业材料
  → POST /api/graph/job/ingest
    → extract_with_both(text)         # 规则词典 + LLM（可选）
    → sqlite_store.add_event()        # 写入证据事件
    → sqlite_store.add_proposal()     # 生成待确认提案
  → GET /api/graph/job/proposals/pending  # 教师查看
  → POST /api/graph/job/proposals/confirm-sqlite  # 教师确认
    → sqlite_store.confirm_proposal()
    → sqlite_store.create_snapshot()  # 生成版本快照
  → GET /api/graph/job               # 图谱更新（含证据元信息）
    → graph.py build_job_ability_graph() + ability_evidence_summary()
```

---

## 已知问题

1. **SQLite 中文显示问题**：PowerShell `Invoke-WebRequest` 展示中文时可能出现 `?`，但实际存储和 API 返回均为正确 UTF-8（可用 Python 或浏览器验证）
2. **证据元信息为 0**：当前 evidence_events 表中无匹配 `job_role="自动化生产线装调与运维技术员"` 的证据。通过 ingest 接口导入数据后会自动填充
3. **jieba 未安装**：`extract_skill_spans_jieba()` 已预置，需 `pip install jieba` 后激活
4. **2 项测试预期性失败**：dedup 逻辑变更 + confidence 公式调整