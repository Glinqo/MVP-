# 岗位能力图谱后端升级开发留痕

> 当前目标：基于 Qian 分支的产品形态，分阶段升级岗位能力图谱后端。
> 开发规则：`D:\E盘\实验\rule`，采用“简单优先、手术式改动、目标可验证”的方式推进。
> 最近更新：2026-07-14

## 总体方向

岗位能力图谱后端升级不以“更强爬虫”为唯一目标，而是建立一条可解释、可审计、可回滚的数据链路：

```text
真实岗位数据 / 教师材料 / 企业 JD
  → 结构化导入或低频采集
  → 规则词典 + LLM 候选抽取
  → 能力证据事件库
  → 图谱更新提案
  → 教师/管理员确认
  → 版本化岗位能力图谱
  → 前端图谱 API 消费
```

## Phase A：数据底座与 API 闭环

目标：让岗位材料进入后端，转成可查询、可聚合、可追溯的证据数据。

已实现：

- 新增 `scripts/pipeline/sqlite_store.py`，提供 SQLite 存储层。
- `scripts/pipeline/evidence_store.py` 改为兼容包装层，保留旧函数名。
- 新增 `raw_documents` 和 `job_posts` 两层存储：
  - `raw_documents` 保存原始岗位材料、来源、URL、内容哈希和导入时间。
  - `job_posts` 保存标准化后的岗位标题、公司、职责、技能、要求。
- 新增/修复 `POST /api/graph/job/ingest`：
  - 输入 JD / 教师材料文本。
  - 保存原始材料和标准化岗位记录。
  - 使用规则词典或 LLM 候选抽取能力。
  - 生成 `evidence_events`。
  - 按来源权重和置信度生成待确认提案。
- 新增 `scripts/pipeline/job_data_importer.py`：
  - 支持本地 `txt/md/html/json/csv` 批量导入。
  - 支持 `utf-8-sig / utf-8 / gb18030` 读取回退，降低 Excel/中文材料导入失败概率。
  - CLI 与 `/api/graph/job/ingest` 共用同一条 `ingest_job_text()` 链路，避免两套导入逻辑分叉。
- 升级 `scripts/job_intelligence_update.py`：
  - 兼容旧版 `policy/path/url` 和新版 `update_policy/local_path/search_url` 来源配置。
  - 默认非 dry-run 写入 SQLite 证据链路，而不是只生成旧 JSON 提案。
  - 保留 `--store legacy/both` 兼容旧演示路径。
  - 本地授权来源和公开 URL 来源仍遵守低频、robots.txt、最大字节数限制。
  - 企业官网 `enterprise_official` 来源优先走站点级 HTML 解析适配器：
    - 新增 `scripts/enterprises/site_adapters.py`。
    - 支持 JSON-LD `JobPosting`、招聘卡片、职位列表、表格行抽取。
    - 内置 Siemens / 汇川 Inovance / BYD / generic enterprise 适配策略。
    - 结构化岗位以 `structured_posts` 单条写入 SQLite，避免整页文本混杂。
- 新增 `POST /api/job-data/collect`：
  - 后端可直接触发授权来源采集。
  - 支持 `dry_run`、`sources`、`source_id`、`max_sources`、`store`、`use_llm`、`max_abilities`。
  - 采集结果进入 `raw_documents → job_posts → evidence_events → proposals` 链路。
- 新增 `GET /api/job-data/documents`。
- 新增 `GET /api/job-data/posts`。
- 新增 `GET /api/graph/job/proposals/pending`。
- 新增 `POST /api/graph/job/proposals/confirm-sqlite`。
- `build_job_ability_graph()` 返回节点证据元数据：
  - `evidence_count`
  - `avg_confidence`
  - `last_updated_at`
  - `source_types`
  - `latest_evidence`

## Phase B：LLM 辅助分析

目标：让 LLM 只做“候选抽取”，不直接修改正式图谱。

已实现：

- 新增 `scripts/pipeline/llm_extractor.py`。
- 支持 LLM JSON 候选解析。
- 支持规则抽取 + LLM 抽取合并。
- LLM 未配置或调用失败时自动回落到规则抽取。
- LLM 候选必须映射到已知能力节点，才会进入后续证据链。
- LLM 候选写入证据时保留 `prompt_version` 和 `llm_model` 元数据，便于后续审计、复现和成本分析。
- LLM 候选映射增加确定性语义 fallback：
  - 优先匹配能力名称。
  - 名称不完全一致时，按技能词项、中文 2/3-gram、英文/数字 token、维度一致性计算相似度。
  - 只映射到已知能力节点，并记录 `match_method` 与 `similarity_score`。
  - 对 root 节点降权，减少把具体技能错误映射到根任务节点。
- 已接入可配置 embedding 向量召回增强：
  - 新增 `app/services/embedding_client.py`，调用 OpenAI-compatible `/embeddings` 接口。
  - 通过 `EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL`、`EMBEDDING_MODEL` 启用。
  - 可复用 `LLM_API_KEY` / `LLM_BASE_URL` 作为兼容网关配置。
  - `EMBEDDING_MATCH_THRESHOLD` 控制命中阈值，默认 `0.68`。
  - `EMBEDDING_MATCH_ENABLED=0` 可关闭向量匹配。
  - 未配置或调用失败时自动回落本地词项相似度，不影响导入链路。
- 新增 LLM 抽取缓存与调用上限：
  - 默认按 `prompt_version + model + 文本哈希` 缓存候选结果。
  - `LLM_EXTRACT_CACHE_DIR` 可指定缓存目录。
  - `LLM_EXTRACT_MAX_CALLS` 可限制单进程最大 LLM 抽取调用次数。
  - 缓存/预算只影响 LLM，规则抽取链路保持可用。

## Phase C：版本、确认与可解释

目标：让图谱更新可审计、可确认、可回滚。

已实现：

- SQLite `proposals` 表支持 pending / confirmed / rejected。
- SQLite `snapshots` 表支持版本快照。
- SQLite `audit_log` 表记录事件、提案、快照操作。
- 确认 SQLite 提案后自动生成岗位图谱快照：
  - `POST /api/graph/job/proposals/confirm-sqlite`
  - 返回 `proposal`、`snapshot`、`snapshot_graph`
  - 快照节点包含确认人、确认时间、提案 ID、证据元数据和维度分数。
- `GET /api/graph/job?job_role=...` 会叠加该岗位最新 SQLite snapshot：
  - 返回 `active_snapshot`
  - `summary.active_snapshot_version` 标明当前生效版本
  - 节点保留 `confirmed_proposal_id` / `confirmed_by` / `confirmed_at`
- 新增批量确认入口：
  - `POST /api/graph/job/proposals/confirm-sqlite-batch`
  - 支持 `proposal_ids` 或 `confirm_all + job_role`。
  - 按岗位分组生成快照，避免跨岗位提案混入同一个图谱版本。
- 节点详情可展示证据来源分布和最新证据。

未完成：

- 前端在 Qian 分支中移除了岗位更新提案入口，后续需要为管理入口恢复轻量审核页，或保持纯 API 管理。

## 本轮修复的 P0 风险

| 风险 | 处理 |
|---|---|
| `GET /api/graph/job/proposals/confirm-sqlite` 中误用未定义 `payload` | 移到 POST 分支 |
| `POST /api/graph/job/ingest` 写入乱码岗位名 | 改为读取 `payload.job_role` 或 `primary_job_profile().role_name` |
| SQLite 去重逻辑查询 `event_id` 前缀，实际无法命中 | 改为按 `job_role + ability_id + source_url + evidence_text` 精确去重 |
| `evidence_store` import 时自动迁移并重命名旧 JSON | 改为显式 `migrate_existing_json_events()`，import 不再变更用户数据 |
| `compute_confidence()` 旧 API 语义被 proposal score 替代 | 恢复旧兼容公式 |
| `cleaner.extract_fields_from_text()` 中文关键词乱码 | 重写为干净 UTF-8 关键词，支持职责/要求/技能字段抽取 |
| LLM prompt 乱码 | 重写为干净 UTF-8 中文 prompt |
| LLM 失败返回错误对象可能污染候选 | 改为失败返回空列表，安全回落规则抽取 |
| 测试污染真实 SQLite 数据 | 新增 `MVP_EVIDENCE_DB_PATH` 支持，测试使用临时 DB |
| 确认 SQLite 提案后没有正式快照 | 新增 `confirm_sqlite_job_graph_proposal()` 自动创建版本化图谱快照 |
| API 导入与 CLI 导入逻辑可能分叉 | 抽出 `ingest_job_text()`，API 和批量导入共用 |
| 版本回滚 POST 入口缩进在异常处理之后导致不可达 | 移回正常 POST 路由分支 |
| 多条提案逐条确认会产生过多快照 | 新增批量确认 API，按岗位生成单个批量快照 |
| 确认后的 SQLite 快照没有成为当前图谱状态 | `GET /api/graph/job?job_role=...` 叠加最新 SQLite snapshot 并返回 `active_snapshot` |
| LLM 抽取结果缺少复现线索 | 证据 metadata 记录 `prompt_version` 和 `llm_model` |
| LLM 候选表达与能力节点名称不完全一致时容易丢失 | 新增确定性语义/词项相似度 fallback，结果记录 `match_method` 和 `similarity_score` |
| 默认岗位来源配置与采集脚本格式不一致 | `job_intelligence_update.py` 同时兼容 `policy` 和 `update_policy`、`path` 和 `local_path`、`url` 和 `search_url` |
| 采集脚本只生成旧 JSON 提案，未进入新证据库 | 非 dry-run 默认 `--store sqlite`，写入新的 SQLite 证据链路 |
| 批量岗位样本重复触发 LLM，成本不可控 | 新增 LLM 抽取缓存和 `LLM_EXTRACT_MAX_CALLS` 调用上限 |

## 风险检查

- 合规风险：当前实现只支持输入材料/低频来源产生候选证据，不绕过登录、验证码或反爬机制。
- 采集合规风险：`job_intelligence_update.py` 只处理显式启用的授权来源；URL 来源默认检查 robots.txt，限制请求间隔和最大读取字节数。
- 数据污染风险：外部材料不会直接修改正式图谱，只生成 evidence 和 proposal；正式快照必须经确认接口产生。
- 可追溯风险：每条证据保留来源类型、来源 URL、抽取方法、置信度和时间；确认后的快照保留提案 ID、确认人和确认时间。
- 回滚风险：已有 snapshot/diff/rollback 存储函数，但批量确认和前端管理入口还未完成。
- LLM 风险：LLM 只作为候选抽取器；未配置或失败时不影响规则链路。

## 验证记录

2026-07-14 已通过：

```powershell
python -m compileall -q app scripts tests
python tests\job_graph_backend_upgrade.test.py
python tests\api_smoke.test.py
python tests\job_intelligence_update.test.py
python tests\test_p0_pipeline.py
```

新增测试覆盖：

- `tests/job_graph_backend_upgrade.test.py`
  - SQLite 原始材料和标准化岗位存储
  - SQLite 证据去重
  - 提案 pending / confirmed / rejected
  - 确认提案自动生成 snapshot
  - snapshot diff
  - LLM JSON 解析和 fallback
  - `/api/graph/job/ingest`
  - `/api/job-data/documents`
  - `/api/job-data/posts`
  - `/api/job-data/collect`
  - `/api/graph/job/proposals/pending`
  - `/api/graph/job/proposals/confirm-sqlite`
  - `/api/graph/job/proposals/confirm-sqlite-batch`
  - `/api/graph/job?job_role=...` 返回 active SQLite snapshot
  - 本地 CSV 批量导入 CLI 与原始材料/岗位记录落库
  - 授权来源采集脚本非 dry-run 写入 SQLite
  - 默认岗位来源配置 dry-run 可识别新版配置格式
  - LLM 抽取缓存命中，不重复调用 fake LLM
  - LLM 候选“源型漏型输入接法”可通过语义 fallback 映射到 `plc_input_common_terminal`
  - embedding 客户端余弦相似度、最佳候选召回和 LLM 映射接入点
- `tests/job_intelligence_update.test.py`
  - 企业官网站点适配器可解析结构化岗位
  - `enterprise_official` 来源非 dry-run 以多条岗位记录写入 SQLite

## 本轮完成的三个功能

1. 已在前端管理入口恢复“岗位数据导入与提案审核”轻量页面：
   - 功能工作台新增“岗位数据导入”。
   - 工作台标签新增“岗位数据”。
   - 页面支持粘贴岗位材料、选择来源类型、触发授权来源采集、查看最近岗位数据、审核待确认提案、批量确认并生成图谱快照。
2. 已为企业官网来源增加站点级 HTML 解析适配器：
   - `enterprise_official` 来源优先解析官方招聘页中的职位卡片/JSON-LD。
   - 结构化岗位逐条进入 `raw_documents → job_posts → evidence_events → proposals`。
3. 已接入 embedding 向量模型增强召回：
   - 配置 embedding 后，LLM 抽取候选优先通过向量相似度映射到能力节点。
   - 未配置时保留本地词项相似度 fallback。

## 下一步建议

1. 给前端管理页补更细的采集运行日志与跳过原因筛选。
2. 给不同企业官网沉淀更多站点专用 selector 与样例 fixtures。
3. 如果后续数据量扩大，再考虑 SQLite FTS / 向量索引做离线检索加速。
