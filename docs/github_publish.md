# GitHub Publish Notes

当前项目已经在 `mechatronics-agent-mvp/` 内初始化为独立 Git 仓库，并提交当前稳定版本。

```text
commit: 4d28e2e Build mechatronics training MVP
```

## 当前环境状态

- 根目录远程仓库是 Gitee：`https://gitee.com/kadywen/challenge2026.git`
- 本机当前未安装 GitHub CLI：`gh` 不在 PATH
- 因此 Codex 不能直接替你创建 GitHub 仓库并推送

## 方式 A：先在 GitHub 网页创建仓库

1. 在 GitHub 新建空仓库，例如：`mechatronics-agent-mvp`
2. 在本地运行：

```powershell
cd D:\Desktop\challenge2026\mechatronics-agent-mvp
git remote add origin https://github.com/<your-user-or-org>/mechatronics-agent-mvp.git
git branch -M main
git push -u origin main
```

## 方式 B：安装 GitHub CLI 后一键创建并推送

```powershell
winget install GitHub.cli
gh auth login
cd D:\Desktop\challenge2026\mechatronics-agent-mvp
gh repo create mechatronics-agent-mvp --private --source=. --remote=origin --push
```

如需公开仓库，把 `--private` 改成 `--public`。

## 发布前验证命令

```powershell
python .\tests\api_smoke.test.py
node .\tests\scoring.test.js
```

若本机 PATH 没有 `python` 或 `node`，使用 Codex 工作区依赖中的运行时。
