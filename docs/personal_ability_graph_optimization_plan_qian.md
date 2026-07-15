# Qian 分支：个人能力图谱优化方案

调研日期：2026-07-15  
目标分支 / worktree：`qian`，路径 `D:\Desktop\MVP\MVP-`

## 0. 当前分支状态与约束

`qian` worktree 当前落后 `origin/Qian` 5 个提交，同时存在大量本地未提交开发文件。为了避免覆盖 Qian 已有工作，本方案文档只新增此文件，不修改已有代码文件。

需要特别注意的冲突风险：

- `app/services/graph.py`：本地已修改，远端 `origin/Qian` 也有更新。
- `data/graph_update_events.json`：本地运行时数据已修改，远端也有更新。
- 已存在一组新的本地个人图谱相关模块：
  - `app/services/cognitive_twin.py`
  - `app/services/diagnostic_trace.py`
  - `app/services/process_metrics.py`
  - `app/services/strategy_profile.py`
  - `app/services/transfer_engine.py`
  - `app/services/uncertainty_selector.py`
  - `app/services/coverage_matrix.py`

这些模块说明 Qian 分支已经在把“个人能力图谱”升级为“认知数字孪生 / 诊断过程画像”。后续实现应优先整合这些已有模块，而不是另起一套。

## 1. 外部优秀项目调研结论

### 1.1 OATutor：BKT 掌握度 + 自适应选题

项目：<https://github.com/CAHLR/OATutor>

可借鉴点：

- 使用 Bayesian Knowledge Tracing 估计技能掌握度。
- 以技能掌握度驱动自适应题目选择。
- 强调开源、可配置、轻量部署。

对本项目的启发：

- 不要只用 `weak/mastered` 标签，应维护每个能力的可解释掌握概率或掌握分。
- 可以先实现 `BKT-lite` 规则版，再保留接入 pyBKT 的接口。
- 选题、角色扮演下一步动作、训练单都应从“最低掌握 + 高岗位权重 + 高不确定性”综合排序。

### 1.2 pyBKT：可解释、可复现的知识追踪模型

项目：<https://github.com/CAHLR/pyBKT>

可借鉴点：

- 针对 problem solving sequence 估计 student cognitive mastery。
- 支持 fit、predict、cross-validation。
- 支持 student/item/resource 变体，适合后续离线校准参数。

对本项目的启发：

- MVP 阶段不必直接引入训练依赖；先把事件数据整理成 pyBKT 可用格式：
  `student_id/session_id, skill_name/ability_id, correct, timestamp, item_id, resource_id`。
- 后续可用真实班级数据离线拟合 `learn / guess / slip / prior` 参数，再回填到规则引擎。

### 1.3 OLI Torus：学习工程 + 数据仪表盘 + 版本化

项目：<https://github.com/Simon-Initiative/oli-torus>

可借鉴点：

- 数据驱动的课程创作与交付平台。
- 仪表盘服务持续改进学习内容。
- 内容发布和版本迁移机制清晰。

对本项目的启发：

- 个人能力图谱不只是学生视图，也应成为教师优化题库、实训任务和讲解资源的依据。
- 图谱节点应保留“证据版本”和“最近触发事件”，方便教师复核。

### 1.4 Moodle Analytics API：指标 + 目标 + 洞察动作

文档：<https://docs.moodle.org/dev/Analytics_API>

可借鉴点：

- 一个预测模型由 target 和 indicators 组成。
- 预测不应只输出分数，还要触发 insight 和 action。
- 静态模型也可以基于指标直接产生洞察。

对本项目的启发：

- 个人能力图谱节点应拆成：
  - indicators：事件数、错题数、过程偏差、安全违规、任务完成、间隔时间。
  - target：当前最需要干预的能力 / 是否可以进入综合排故。
  - insight：为什么弱、风险是什么。
  - action：下一步训练、讲解、复问、场景。

### 1.5 pyKT：深度知识追踪可作为远期参考，但不适合 MVP 直接上

项目 / 论文：<https://arxiv.org/abs/2206.11460>

可借鉴点：

- 标准化知识追踪评估协议。
- 覆盖 DKT、DKVMN、SAKT、AKT、GKT 等多类模型。
- 特别提醒：错误评估设置可能导致 label leakage。

对本项目的启发：

- 当前数据量小，不建议直接引入深度知识追踪。
- 应先保证事件定义、评估切分、证据来源可追溯，否则模型分数会“看似高级、实际不可解释”。

### 1.6 Open TutorAI：学习者画像 + 内嵌 analytics + 行动反馈

项目 / 论文：<https://arxiv.org/html/2602.07176v1>

可借鉴点：

- 通过 onboarding 捕捉学习目标和偏好。
- learner analytics 生成 actionable feedback。
- 学习支持围绕个体画像展开。

对本项目的启发：

- 个人能力图谱除了技能状态，还应有“学习策略画像”：是否跳安全检查、是否过早查程序、是否反复低价值检查。
- 前端不应只展示分数，要把分数翻译成“你现在最该做的一件事”。

## 2. 当前本地能力图谱实现盘点

### 已有基础

- `app/services/graph_update_engine.py`
  - 已有事件桶：`chat / weak / improving / mastered / recommended`。
  - 已能计算 `mastery_score / confidence / evidence_count / update_reasons / evidence_events`。
  - 安全能力已做上限保护：安全相关节点不能因一次“已掌握”直接满分。

- `app/services/graph.py`
  - `build_student_ability_graph()` 已返回个人能力图谱节点。
  - 节点已包含 `next_best_action`。
  - Qian 本地改动已预留 `procedure_mastery / safety_score / process_metrics / strategy_tags` 字段，但目前多数为 `None`。

- Qian 新增模块
  - `cognitive_twin.py` 已形成“knowledge / procedure / transfer / safety”四维画像雏形。
  - `diagnostic_trace.py` 已将场景行为标准化为 trace。
  - `process_metrics.py` 已计算安全、证据质量、定位、效率、闭环验证。
  - `strategy_profile.py` 可识别反复策略偏差。
  - `uncertainty_selector.py` 可用掌握度和不确定性挑下一步。

### 主要问题

1. 个人图谱主接口还没真正融合 cognitive twin，`procedure_mastery / safety_score / process_metrics / strategy_tags` 仍是空字段。
2. 事件 schema 不够统一，聊天、自测、讲解、场景、任务的证据强度和方向分散在不同逻辑里。
3. `transfer_engine.py` 的 `_collect_ability_evidence()` 期待 trace 中有 `events`，但 `list_student_traces()` 当前只返回摘要，导致迁移分可能难以产生真实证据。
4. 前端节点详情还偏“列表展示”，缺少清晰的证据时间线、四维掌握条、下一步动作解释。
5. 缺少“岗位要求高但个人证据弱”的 gap 排序，个人图谱和岗位图谱没有形成强对比。

## 3. 优化目标

把个人能力图谱升级为：

> 学生可理解、教师可审查、系统可推荐下一步的“证据驱动认知画像”。

节点从单一 `mastery_score` 升级为四维：

1. `knowledge_mastery`：知识理解，来自问答、自测、讲题复问。
2. `procedure_mastery`：过程掌握，来自排故 trace 与专家路径吻合度。
3. `transfer_score`：迁移能力，来自不同场景/故障上下文中的重复正确应用。
4. `safety_score`：安全合规，来自安全检查顺序、危险动作、闭环确认。

同时保留兼容字段：

- `mastery_score`
- `status`
- `confidence`
- `evidence_count`
- `evidence_events`
- `next_best_action`

## 4. 数据模型方案

### 4.1 标准化学习事件

新增内部标准事件视图，不一定立刻改存储格式，可先在服务层 normalize：

```json
{
  "event_id": "",
  "session_id": "",
  "created_at": "",
  "event_type": "chat_message | score | question_explained | diagnostic_action | task_completed | feedback",
  "ability_ids": [],
  "event_category": "knowledge | procedure | safety | transfer | reflection",
  "polarity": "positive | negative | neutral",
  "evidence_weight": 0.0,
  "confidence_delta": 0.0,
  "mastery_delta": 0.0,
  "scenario_id": "",
  "action_id": "",
  "trace_id": "",
  "outcome": "correct | incorrect | unsafe | completed | needs_review",
  "evidence_summary": ""
}
```

事件权重建议：

| 事件 | 默认类别 | 方向 | 权重 |
| --- | --- | --- | --- |
| 聊天命中能力 | knowledge | neutral/positive | 0.3 |
| 自测答错 | knowledge | negative | 1.0 |
| 自测答对 | knowledge | positive | 0.8 |
| 题目讲解 | knowledge | positive but low | 0.4 |
| 讲解后复问通过 | knowledge | positive | 0.9 |
| 场景正确动作 | procedure | positive | 1.0 |
| 场景错误动作 | procedure | negative | 1.0 |
| 不安全动作 | safety | negative | 1.5 |
| 完成任务交付物 | procedure/transfer | positive | 1.2 |
| 反馈“已掌握” | reflection | positive but capped | 0.5 |
| 反馈“仍不会” | reflection | negative | 0.7 |

### 4.2 节点输出字段

`GET /api/graph/student` 的每个节点建议输出：

```json
{
  "id": "plc_input_common_terminal",
  "label": "PLC 输入公共端判断",
  "status": "weak | improving | mastered | touched | recommended_next | unknown",
  "mastery_score": 62,
  "confidence": 0.58,
  "knowledge_mastery": 68,
  "procedure_mastery": 45,
  "transfer_score": 20,
  "safety_score": 80,
  "uncertainty": 0.42,
  "evidence_count": 5,
  "last_updated_at": "",
  "last_practiced_at": "",
  "update_reasons": [],
  "evidence_events": [],
  "process_metrics": {
    "safety_compliance": 0.8,
    "evidence_quality": 0.6,
    "fault_localization": 0.45,
    "diagnostic_efficiency": 0.5,
    "closure_verification": 0.2
  },
  "strategy_tags": [
    {"tag": "premature_program_check", "label": "过早查程序"}
  ],
  "next_best_action": "",
  "why_next": ""
}
```

## 5. 计算逻辑方案

### 5.1 BKT-lite：先做可解释规则版

不直接训练模型，先把 BKT 思想落成可解释规则：

```text
p_known 初始值：由 mastery_score 映射
correct 事件：p_known 上升，涨幅受 guess/slip 和 evidence_weight 影响
incorrect 事件：p_known 下降，但不直接归零
explanation 事件：小幅上升，只代表接触和改进，不代表掌握
task_completed：中幅上升
unsafe：safety_score 大幅下降，并阻断 mastered
```

参数第一版写死在配置表中：

```json
{
  "default": {"prior": 0.35, "learn": 0.18, "guess": 0.2, "slip": 0.1},
  "safety": {"prior": 0.25, "learn": 0.12, "guess": 0.15, "slip": 0.05},
  "procedure": {"prior": 0.3, "learn": 0.15, "guess": 0.1, "slip": 0.15}
}
```

后续真实数据足够后，再用 pyBKT 离线拟合参数。

### 5.2 四维画像融合

综合掌握度不再只看知识题：

```text
mastery_score =
  0.35 * knowledge_mastery
+ 0.30 * procedure_mastery
+ 0.20 * transfer_score
+ 0.15 * safety_score
```

安全能力特殊规则：

- `safety_score < 60` 时，节点不能是 `mastered`。
- 存在未闭环危险动作时，相关节点至少为 `recommended_next` 或 `weak`。
- 只有“安全检查动作 + 闭环验证 + 任务/场景通过”都有证据时，安全节点才允许进入 `mastered`。

### 5.3 状态判定

建议规则：

```text
weak:
  mastery_score < 45
  或 safety_score < 60
  或 最近关键证据为 negative

improving:
  有 negative 历史，但最近出现 explanation / correct action / task_completed

recommended_next:
  岗位权重高、证据少、或是弱点前置能力

touched:
  只有聊天命中或浏览讲解，证据不足

mastered:
  mastery_score >= 80
  且 confidence >= 0.65
  且 safety gate 通过
```

### 5.4 下一步动作排序

`next_best_action` 不再只由 status 决定，应综合：

```text
priority =
  岗位需求权重 * 0.30
+ 弱点严重度 * 0.25
+ 不确定性 * 0.20
+ 安全风险 * 0.15
+ 前置能力阻塞 * 0.10
```

动作类型：

- 知识弱：看讲解 + 1 分钟复问。
- 过程弱：做排故角色扮演指定场景。
- 迁移弱：换一个故障上下文做同类判断。
- 安全弱：先做安全检查脚本，不进入综合排故。
- 证据不足：完成一题/一个小任务来建立证据。

## 6. 后端落地步骤

### P0：不破坏现有接口，融合 cognitive twin

目标：`GET /api/graph/student` 返回真实四维字段，而不是 `None`。

建议改动：

1. 新增 `app/services/student_mastery_profile.py`
   - 负责标准化事件、计算四维画像、生成节点增强字段。
   - 作为 `graph.py` 和 `cognitive_twin.py` 的共同底层，避免循环依赖。

2. 修正 `transfer_engine.py`
   - 当前 `_collect_ability_evidence()` 期待 trace 中有 `events`，但 `list_student_traces()` 只返回摘要。
   - 应改为对每个 trace 调用 `build_diagnostic_trace(session_id, scenario_id, attempt)` 获取 `activities`。

3. 更新 `app/services/graph.py`
   - `build_student_ability_graph()` 在 node_payload 中合并 `student_mastery_profile` 输出。
   - 保留现有 `mastery_score/status/confidence`，避免前端和测试断裂。

4. 更新 `app/services/cognitive_twin.py`
   - 改成复用 `student_mastery_profile`，不再自己重复归一化。
   - `process_evidence` 不再为空，应放入 trace 摘要和关键偏差事件。

5. 补测试
   - `tests/cognitive_twin.test.py`
   - `tests/scenario_diagnostic_events.test.py`
   - 新增 `tests/student_mastery_profile.test.py`

验收：

- 场景中先做安全检查、正确定位、完成验证后，相关节点 `procedure_mastery/safety_score` 上升。
- 跳过安全检查或过早改程序，`safety_score/procedure_mastery` 下降。
- `GET /api/graph/student` 仍兼容旧字段。

### P1：前端节点详情升级

目标：学生点开个人图谱节点，能马上看懂“我为什么弱、下一步怎么补”。

建议改动：

1. `web/app.js`
   - 节点详情增加四维条：
     - 知识理解
     - 过程掌握
     - 迁移应用
     - 安全合规
   - `evidence_events` 改成时间线。
   - 增加证据筛选：问答 / 自测 / 讲解 / 场景 / 任务 / 反馈。
   - 展示 `strategy_tags`。

2. `web/graph-renderer.js`
   - 节点外环继续表示状态。
   - 节点内部小条或 tooltip 表示四维最低项。
   - 节点大小继续按证据数/连接度，但避免视觉过载。

3. `web/styles.css`
   - 新增 `.mastery-bars`、`.evidence-timeline`、`.strategy-tag`。

验收：

- 学生答错公共端题后，公共端节点打开能看到：
  - 为什么 weak。
  - 哪次题/场景造成。
  - 下一步是讲解、任务还是场景。

### P2：岗位差距视图

目标：把岗位图谱与个人图谱真正连起来。

新增 API：

```text
GET /api/graph/gap?session_id=...
```

返回：

```json
{
  "top_gaps": [
    {
      "ability_id": "",
      "ability_name": "",
      "job_demand_weight": 0.92,
      "student_mastery": 48,
      "confidence": 0.42,
      "gap_score": 0.81,
      "reason": "岗位高频 + 个人证据不足 + 最近场景错误",
      "next_best_action": ""
    }
  ]
}
```

前端：

- 在学习驾驶舱展示 Top 5 岗位差距。
- 在个人图谱节点详情里显示“岗位要求强度”。

### P3：pyBKT 离线校准

目标：真实使用数据足够后，把规则参数校准成数据驱动参数。

步骤：

1. 新增导出脚本：
   - `scripts/export_student_events_for_bkt.py`
   - 输出 `session_id, ability_id, item_id, correct, timestamp, source`
2. 用 pyBKT 离线 fit。
3. 输出每个 ability 的 `prior/learn/guess/slip` 到：
   - `knowledge/student_mastery_parameters.json`
4. 线上仍使用本地规则，不引入实时训练依赖。

## 7. 前端展示建议

### 7.1 图谱图例

个人图谱图例应明确：

- 颜色：能力维度。
- 外环：状态。
- 大小：证据数 / 连接度。
- 四维条：知识、过程、迁移、安全。

### 7.2 节点详情结构

建议按这个顺序：

1. 当前结论：状态、掌握度、置信度。
2. 四维画像：知识 / 过程 / 迁移 / 安全。
3. 为什么：最近 3 条 `update_reasons`。
4. 证据时间线：按时间显示事件、来源、影响。
5. 策略标签：例如“跳过安全检查”“过早查程序”。
6. 下一步动作：按钮直达讲解、训练单、场景、自测。

## 8. 测试计划

后端测试：

- `tests/student_mastery_profile.test.py`
  - 标准事件归一化。
  - 四维分计算。
  - safety gate。
  - next_best_action 排序。

- `tests/cognitive_twin.test.py`
  - 兼容字段存在。
  - 四维字段非空。
  - 安全错误会降低 safety_score。

- `tests/scenario_diagnostic_events.test.py`
  - diagnostic_action 进入个人图谱证据。
  - process_metrics 影响 procedure_mastery。

- `tests/api_smoke.test.py`
  - `/api/graph/student` 兼容旧断言。
  - 新字段存在。
  - `/api/graph/gap` 返回 Top gaps。

前端测试：

- `node --check web/app.js`
- 手动验证：
  - 问答后图谱刷新。
  - 场景错误后 evidence timeline 有记录。
  - 节点详情四维条显示正常。

## 9. 推荐实施顺序

1. 先处理 Qian worktree 的未提交状态：
   - 提交或 stash 当前 `app/services/graph.py`、`app/services/scenario.py` 等本地改动。
   - `data/graph_update_events.json` 属于运行时数据，建议备份后还原，避免污染代码提交。

2. 快进到最新 `origin/Qian`。

3. P0 后端融合：
   - 新增 `student_mastery_profile.py`。
   - 修 `transfer_engine.py` trace 数据来源。
   - `graph.py` 合并四维画像。

4. P1 前端节点详情：
   - 先做详情抽屉，不急着改力导图布局。

5. P2 gap 视图：
   - 学习驾驶舱展示 Top 5 岗位差距。

6. P3 离线 BKT：
   - 等有真实事件样本后再做。

## 10. MVP 边界

本轮不建议做：

- 不引入深度知识追踪模型实时推理。
- 不上 Neo4j / Milvus / Redis。
- 不让 LLM 直接给学生能力评分。
- 不自动把“看过讲解”判定为 mastered。
- 不把安全能力一次反馈就置为满分。

最小闭环应该是：

```text
学习事件
-> 标准化证据
-> 四维个人能力画像
-> 可解释节点详情
-> 下一步动作
-> 新学习事件
```

