# GitHub 发布说明

本项目已在 `mechatronics-agent-mvp/` 内初始化为独立 Git 仓库。用户提供的目标远端为：

```text
https://github.com/Glinqo/MVP-.git
```

当前发布策略是直接使用原生 `git` 推送到该远端。当前机器未安装 GitHub CLI（`gh`），因此不使用 `gh repo create` 或 `gh pr create` 流程。

## 本次发布范围

- 自研轻量 Web/API Demo。
- 学生端问答式岗位培训界面。
- 岗位能力图谱、学生个人能力图谱、当前问题图谱。
- 诊断题、确定性评分、讲题、学习路径、实训任务、反馈闭环。
- 机电一体化 NPN/PNP 传感器与 PLC 输入排故知识库、题库和资源。
- 借鉴项目源码位置与功能清单：`docs/borrowed_feature_source_map.md`、`docs/borrowed_feature_inventory.json`。

## 远端处理

远端 `main` 初始状态只有一个 README 标题：

```text
# MVP-
```

本地合并该初始提交时保留了本项目完整 README，并把远端初始提交纳入历史，避免强推覆盖。

## 验证命令

发布前运行：

```powershell
python -c "import json, pathlib; [json.load(open(p, encoding='utf-8')) for p in pathlib.Path('.').rglob('*.json')]; print('json parse ok')"
python -m compileall -q app tests
node --check web/app.js
node tests/scoring.test.js
python tests/api_smoke.test.py
```

如本机 PATH 没有 `python` 或 `node`，使用 Codex 工作区依赖中的运行时。

## 后续更新

后续本地修改完成并通过测试后，在 `mechatronics-agent-mvp/` 内执行：

```powershell
git status -sb
git add <changed-files>
git commit -m "<message>"
git push
```
