# 岗位情报更新器

这个模块用于让岗位能力图谱具备“定期吸收外部材料、生成待确认更新建议”的能力。它不是通用爬虫平台，也不替代教师确认。

## 设计来源

参考项目：

- `https://github.com/NanmiCoder/MediaCrawler`
- `https://github.com/NanmiCoder/CrawlerTutorial`
- `https://www.bilibili.com/video/BV1PsCdYjEyK`
- `https://github.com/D4Vinci/Scrapling`

图谱前端和更新策略的完整审查见：[岗位能力图谱更新审查与优化方案](job_ability_graph_optimization_plan.md)。

本仓库没有复制上述项目代码，只借鉴结构思路：

- 配置驱动：来源写在 `knowledge/job_intelligence_sources.json`。
- 采集与存储分离：脚本负责采集和抽取，正式图谱更新仍走现有图谱建议机制。
- 低频运行：默认每天一次，默认最多 3 个来源。
- 可审计：每次输出来源、摘要、命中的能力点和建议批次。
- 合规边界：不做登录、Cookie、代理、验证码、反检测和大规模采集。

资源取舍：

- MediaCrawler：学习多平台内容采集架构，只能作为后续弱信号来源，不作为岗位能力图谱主数据入口。
- CrawlerTutorial 与配套 B 站课程：作为团队爬虫工程训练材料。
- Scrapling：后续可选为公开企业招聘页和公开 HTML 的通用抽取层，但默认关闭，且必须遵守来源条款。

## 文件位置

- `.agents/skills/job-intelligence-updater/SKILL.md`：给 Codex 使用的本地 skill。
- `.agents/skills/job-intelligence-updater/references/crawler_source_map.md`：借鉴来源和限制说明。
- `knowledge/job_intelligence_sources.json`：岗位情报来源配置。
- `docs/references/job_intelligence_seed.md`：默认启用的本地演示材料。
- `scripts/job_intelligence_update.py`：标准库岗位情报更新器。
- `scripts/install_daily_job_intelligence_update.ps1`：Windows 每日定时任务安装脚本。
- `tests/job_intelligence_update.test.py`：更新器冒烟测试。

## 使用方式

先干跑，不写运行日志和图谱建议：

```powershell
python scripts/job_intelligence_update.py --dry-run
```

确认来源合法、摘要合理后生成待教师确认的岗位图谱建议：

```powershell
python scripts/job_intelligence_update.py
```

只运行某一个来源：

```powershell
python scripts/job_intelligence_update.py --source-id demo_local_automation_job_seed
```

安装每日更新任务：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_daily_job_intelligence_update.ps1 -Time "07:30"
```

## 更新闭环

```text
公开/本地岗位材料
-> 低频采集和文本清洗
-> 能力关键词命中
-> data/job_graph_update_proposals.json 待确认建议
-> 教师确认
-> data/job_graph_confirmed_snapshots.json
-> 岗位能力图谱可视化
```

## 添加真实来源

在 `knowledge/job_intelligence_sources.json` 中新增来源，并先保持 `enabled: false`。确认以下事项后再启用：

- 页面公开可访问，不需要登录、Cookie 或验证码。
- 允许低频访问，且不违反网站条款。
- `source` 字段能追溯到原始材料。
- `source_type` 能说明材料类型，例如 `public_job_page`、`enterprise_task_doc`、`teacher_imported_material`。

如果来源不适合网页采集，优先请教师导出为本地 Markdown/TXT/HTML，再配置为 `local_file`。

## 验证命令

```powershell
python tests/job_intelligence_update.test.py
python -m compileall -q scripts app tests
python tests/api_smoke.test.py
```
