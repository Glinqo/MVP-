# MVP — 机电一体化智能排故训练系统

面向职业教育的**岗位能力图谱 + 排故认知孪生**系统。学生端支持从"提问/排故 → 画像更新 → 证据解释 → 下一步推荐 → 岗位差距"的完整闭环。

## 快速开始

### 环境要求

- Python 3.11+
- 无外部数据库依赖（JSON 文件 + SQLite 内置存储）

### 安装

```powershell
git clone https://github.com/Glinqo/MVP-.git
cd MVP-
```

无需 `pip install`，项目使用 Python 标准库。

### 启动

```powershell
python app/server.py --port 8765
```

打开浏览器访问 `http://127.0.0.1:8765`

### 运行测试

```powershell
python -m compileall -q app scripts tests
python tests/troubleshooting_model.test.py
python tests/model_tracer.test.py
python tests/conformance_engine.test.py
python tests/counterfactual_action.test.py
python tests/cognitive_twin.test.py
python tests/learning_event_normalizer.test.py
python tests/ability_state_engine.test.py
python tests/next_action_recommender.test.py
python tests/student_mastery_profile.test.py
python tests/api_smoke.test.py
```

---

## 架构概览

```
web/                          前端 (D3.js 力导向图 + 交互界面)
app/
├── server.py                  HTTP 服务器 (52 个 API 路由)
└── services/                  44 个服务模块
    ├── graph.py               岗位/学生能力图谱构建
    ├── graph_update_engine.py 图谱更新引擎 (事件驱动)
    ├── ability_state_engine.py 能力状态机 (四维分 + 不确定性 + 状态判定)
    ├── cognitive_twin.py      认知孪生 (聚合四维画像)
    ├── student_mastery_profile.py 学生掌握度画像
    ├── scenario.py            排故场景 (选择题 + 自由排故双模式)
    ├── model_tracer.py        行为图追踪 (最优路径/偏差检测)
    ├── conformance_engine.py  过程一致性评估 (5 维指标)
    ├── counterfactual_action.py 反事实动作选择 (效用公式)
    ├── hypothesis_engine.py   故障假设管理 (集合消除 + 置信度排序)
    ├── information_gain.py    信息增益计算 (熵 + 期望熵减)
    ├── strategy_profile.py    排故策略画像 (偏差标签 + 持久化追踪)
    ├── scenario_composer.py   动态场景组合 (variants + difficulty + seed)
    ├── coverage_matrix.py     能力覆盖矩阵
    ├── transfer_engine.py     迁移评分引擎
    ├── uncertainty_selector.py 不确定性驱动训练选择
    ├── learning_event_normalizer.py 学习事件标准化 (9 种类型)
    ├── learning_event_store.py 标准事件存储 + 查询
    ├── next_action_recommender.py 下一步行动推荐
    ├── device_state_handler.py 设备状态录入 → 能力映射
    ├── data_store.py          统一数据存储层
    ├── feedback.py            反馈 + session 管理
    ├── chat.py                对话引擎
    ├── explanation.py         讲题引擎
    ├── quiz.py                自测题
    ├── personalized_plan.py   个性化训练计划
    ├── recommendation.py      诊断推荐
    ├── matching.py            学生-岗位匹配
    ├── learner_context.py     学生上下文
    ├── student_dashboard.py   学生仪表盘
    └── ...                    更多模块

knowledge/                    知识库 (JSON, 只读)
├── ability_nodes.json        25 个能力节点 (前置关系 + 维度映射)
├── troubleshooting_models.json 4 个排故场景模型 (含 9 个 variants)
├── troubleshooting_scenarios.json 排故场景描述
├── diagnostic_action_policy.json 诊断动作策略配置
├── job_skill_lexicon.json    技能词典
├── job_profiles.json         岗位配置
└── ...

scripts/pipeline/             数据采集管线
├── crawler_framework.py      爬虫基类
├── sqlite_store.py           SQLite 证据存储
└── ...

tests/                        25 个测试文件 (~4400 行)
```

### 数据流

```
学生行为 (聊天/自测/排故/反馈)
    → 标准化学习事件 (Phase 1)
    → 能力画像计算 (Phase 2: 四维分 + 认知综合分 + 不确定性)
    → 证据链查询 (Phase 3)
    → 排故过程诊断 (Phase 4: 过程一致性 + 策略画像)
    → 下一步推荐 (Phase 5: 优先级排序)
    → 岗位差距 (Phase 6)
    → 设备状态证据 (Phase 7)
```

### 存储层

```
data/sessions/        Session JSON 文件 (学生行为事件)
data/evidence/        证据事件 + 版本快照
scripts/pipeline/     SQLite (evidence_events, proposals, snapshots, audit_log)
knowledge/            只读知识库 JSON
```

所有 JSON 读写收敛到 `app/services/data_store.py`，其他模块通过它访问持久化存储。

---

## API 清单

### 图谱相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/graph` | 当前能力图谱 |
| GET | `/api/graph/job` | 岗位能力图谱 |
| GET | `/api/graph/student` | 学生个人能力图谱 (25 节点含四维分) |
| GET | `/api/graph/gap` | 学生 vs 岗位差距图 |
| GET | `/api/graph/updates` | 图谱更新时间线 |
| GET | `/api/graph/job/versions` | 岗位图谱版本列表 |
| GET | `/api/graph/job/versions/diff` | 版本差异对比 |
| POST | `/api/graph/student/event` | 写入学生图谱事件 |
| POST | `/api/graph/job/proposals` | 生成岗位图谱更新建议 |
| POST | `/api/graph/job/proposals/confirm` | 确认建议 (生成快照) |
| POST | `/api/graph/job/versions/rollback` | 回滚图谱版本 |
| POST | `/api/graph/job/ingest` | 导入 JD 文本 |

### 学生能力

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/student/bootstrap` | 学生初始化 |
| GET | `/api/student/dashboard` | 学生仪表盘 |
| GET | `/api/student/ability-state` | 能力状态 (四维 + 不确定性 + 推荐) |
| GET | `/api/student/ability-evidence` | 能力证据链 (含评分影响) |
| GET | `/api/student/cognitive-twin` | 认知孪生 |
| GET | `/api/student/diagnostic-traces` | 诊断轨迹 |
| GET | `/api/student/strategy-profile` | 排故策略画像 |
| GET | `/api/student/transfer-profile` | 迁移评分 |
| GET | `/api/student/coverage-matrix` | 能力覆盖矩阵 |
| GET | `/api/student/job-match` | 学生-岗位匹配 |
| GET | `/api/student/job-gap` | 岗位差距视图 |
| GET | `/api/student/next-actions` | 下一步行动推荐 |
| GET | `/api/student/next-training-scenario` | 下一训练场景推荐 |
| POST | `/api/student/device-state` | 录入设备状态 |

### 学习事件 (Phase 1)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/student/events` | 查询标准化事件 (支持按 type/ability/scenario 过滤) |
| GET | `/api/student/events/timeline` | 事件时间线 + 统计 |
| POST | `/api/student/events` | 写入标准化事件 |

### 排故场景

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/scenarios` | 场景列表 |
| POST | `/api/scenario/start` | 开始排故场景 (支持 variant_id/difficulty/seed) |
| POST | `/api/scenario/step` | 提交选择题步骤 |
| POST | `/api/scenario/action` | 提交自由排故动作 (含过程诊断) |
| GET | `/api/scenario/next-action` | 反事实动作分析 |

### 对话 & 诊断

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/start` | 开始对话 |
| POST | `/api/chat/message` | 发送消息 |
| POST | `/api/explain` | 讲题 |
| POST | `/api/assist` | 辅助诊断 |
| POST | `/api/quiz/personalized` | 个性化自测 |
| POST | `/api/score` | 评分 |
| POST | `/api/diagnose` | 诊断推荐 |
| POST | `/api/feedback` | 提交反馈 |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/sessions` | 所有会话列表 |
| GET | `/api/knowledge/search` | 知识库搜索 |
| GET | `/api/teacher/summary` | 教师视图汇总 |
| GET | `/api/job-profile` | 岗位信息 |

---

## 核心设计原则

1. **确定性优先** — 全部算法使用规则+权重+配置驱动，不依赖 LLM 自由生成专业事实。同一输入必然产生同一输出。

2. **证据驱动** — 每条图谱更新必须可溯源于具体证据事件（来源 URL + 时间戳 + 提取方法 + 置信度）。

3. **教师确认铁律** — LLM 和爬虫只能生成"待确认建议"，不能直接修改正式能力图谱。正式更新必须经过教师确认 + 版本快照 + 可回滚。

4. **安全约束优先于信息价值** — 危险操作在策略配置中显式标记并阻止，安全评分门槛不达标时限制高级场景。

5. **无重型依赖** — Python 标准库 + D3.js。不需要 Neo4j、Kafka、PostgreSQL、Redis。

---

## 分支说明

| 分支 | 内容 |
|------|------|
| `main` | 稳定版本 |
| `qian` | 学生端开发主线 (Phase 1-7 全部功能 + 排故认知孪生) |
| `feature/job-ability-graph` | 岗位图谱数据管线 |
| `backend/job-graph-upgrade` | 后端升级 (SQLite + LLM) |
| `test` | 岗位扩展 + 诊断题库 v2 |
