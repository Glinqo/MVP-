# Mechatronics Agent MVP

## Job Intelligence Updater

The repo includes a lightweight job intelligence updater for the job ability graph. See [docs/job_intelligence_update.md](docs/job_intelligence_update.md).

Dry run:

```powershell
python .\mechatronics-agent-mvp\scripts\job_intelligence_update.py --dry-run
```

Install a daily Windows scheduled task:

```powershell
powershell -ExecutionPolicy Bypass -File .\mechatronics-agent-mvp\scripts\install_daily_job_intelligence_update.ps1 -Time "07:30"
```

The updater only reads explicitly configured public/local sources, generates pending graph proposals, and requires teacher confirmation before formal job graph changes.

面向职业教育机电一体化职业新人培训的轻量智能体 MVP 仓库。

这个仓库不做大系统，当前以自研轻量 Web/API Demo 为主，同时保留星辰 Agent 的可选导出材料。核心沉淀四类内容：

- 可被本地 Demo 和可选平台复用的提示词与节点配置
- 机电一体化岗位画像、能力节点、知识点、资源和训练任务
- 20 道可确定性评分诊断题、评分规则、示例答案和最小评分代码/API
- 提交、演示和师生反馈文档

## 快速了解产品

如果只是想快速看清楚这个产品做什么、亮点在哪里、如何演示，先读：

- [产品功能与亮点说明](docs/product_overview.md)
- [学生端增强路线与借鉴方案](docs/student_side_enhancement_strategy.md)
- [产品范围](docs/product_scope.md)
- [演示脚本](docs/demo_script.md)

当前产品的核心亮点是：以问答式 AI 作为第一入口，学生先描述真实实训问题，系统再把问题映射到岗位能力图谱、个人能力图谱、知识缺口和补救训练；诊断题只作为可选验证，不再是学习入口。

## MVP 闭环

1. 系统读取目标岗位画像：自动化生产线装调与运维技术员。
2. 职业新人在聊天主屏自由提问和追问，不强制先做题。
3. Agent 先回答问题；涉及设备调试时先给安全提醒。
4. Agent 引导学生补充传感器灯、PLC 输入灯、在线监控等关键现场证据。
5. 岗位能力图谱以 SVG 图形展示企业/行业需求，学生个人能力图谱根据问答、自测、讲题、反馈和任务事件动态更新。
6. 当前问题图谱和知识卡片同步高亮该问题暴露的缺口。
7. 系统推荐今日训练单、7 天补强计划和一节课实训任务；诊断题作为全屏工作台中的可选自测保留，并可按学生薄弱点从知识库生成个性化练习题和培养方案。
8. 教师/师傅视图汇总薄弱点和下一次带教建议。

## 目录

```text
docs/        产品范围、框架调研、流程蓝图、提交清单、演示脚本
app/         标准库 HTTP API 与领域服务
web/         静态学生诊断页面
data/        本地演示会话反馈
prompts/     工作流各节点提示词
knowledge/   岗位画像、能力节点、66 个知识点、资源、训练任务、常见错误
knowledge/imports/  新导入的星辰知识库扩展源
diagnosis/   诊断题、评分规则、示例答案
xingchen/    可选平台导入说明和评分代码模块历史资产
tests/       最小评分测试与样例输入输出
.agents/     给 Codex/智能体使用的本地技能说明
```

## 快速验证

在仓库父目录运行评分测试：

```powershell
node .\mechatronics-agent-mvp\tests\scoring.test.js
```

预期输出：

```text
scoring.test.js passed
```

如果本机 PATH 没有 `node`，使用 Codex 工作区依赖中的 Node 运行。

运行 API 冒烟测试：

```powershell
python .\mechatronics-agent-mvp\tests\api_smoke.test.py
```

预期输出：

```text
api_smoke.test.py passed
```

## 本地运行

启动本地 MVP：

```powershell
python .\mechatronics-agent-mvp\app\server.py --port 8765
```

浏览器打开：

```text
http://127.0.0.1:8765
```

页面支持问答式排故辅导、岗位能力图谱、学生个人能力图谱、当前问题图谱、20 道预设评分题、个性化练习题、今日训练单、7 天补强计划、薄弱点推荐、实训任务推荐、反馈保存和教师摘要。右侧边栏是功能入口，点击后进入全屏工作台查看或操作；图谱节点会打开证据详情，题目讲解按钮会记录学习事件并可快速回到聊天追问。

## 可选大模型配置

聊天接口支持 OpenAI-compatible Chat Completions。没有配置时会自动使用规则兜底回答。

```powershell
$env:LLM_API_KEY="your_api_key"
$env:LLM_BASE_URL="https://api.openai.com/v1"
$env:LLM_MODEL="gpt-4o-mini"
python .\mechatronics-agent-mvp\app\server.py --port 8765
```

评分仍由 `diagnosis/scoring_rules.json` 和确定性代码完成，大模型只用于回答、解释和引导追问。

## 使用方式

- 先阅读 `docs/product_scope.md` 明确 MVP 边界。
- 阅读 `docs/optimized_mvp_spec.md` 查看优化后的岗位新人培训 MVP 规格。
- 阅读 `docs/mechatronics_professional_group_research.md` 了解机电一体化专业群、岗位群和课程群。
- 先阅读 `docs/related_project_frameworks.md` 确认自研框架取舍。
- 参考 `docs/student_training_llm_landscape.md` 了解现有学生培训类大模型的功能、优缺点和差异化机会。
- 再阅读 `docs/product_innovation_architecture.md` 确认核心创新功能和系统架构。
- 将 `prompts/*.md` 作为本地 LLM 调用或后续平台节点的提示词资产。
- 将 `xingchen/code_module_scoring.js` 或 Python 版作为评分服务的确定性规则核心。
- 将 `knowledge/knowledge_50.json` 作为轻量主知识库（当前 66 条，文件名保留历史命名），将 `knowledge/imports/机电一体化智能体_知识库导入版_V1.json` 作为扩展知识库。
- 将 `knowledge/industry_demand_snapshots.json` 作为岗位能力图谱的企业/行业需求样例数据，后续可定期人工更新。
- 将 `data/graph_update_events.json`、`data/job_graph_update_proposals.json`、`data/job_graph_confirmed_snapshots.json` 作为自更新图谱的本地运行时证据和确认记录。
- 使用 `tests/sample_inputs.json` 和 `tests/expected_outputs.json` 做本地自测。
