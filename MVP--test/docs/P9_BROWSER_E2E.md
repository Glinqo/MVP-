# P9 Browser E2E Acceptance

**Baseline**: ec31d9c
**Branch**: test
**Date**: 2026-08-19

---

## 浏览器与运行环境
- 无浏览器自动化框架（Playwright/Selenium 未安装）
- 通过 HTTP API smoke test 验证核心功能链
- 真实浏览器手工 E2E 待用户执行

## 测试数据
- P9-A (id=159): 001-005 + 011 (automation_line)
- P9-B (id=160): 006-010 + 011 (mechanical_maintenance)
- 多班学生: 011
- 无班学生: 012

## API Smoke Test 结果

| 测试 | 结果 |
|------|------|
| 教师登录 000 | PASS |
| 创建 P9-A/P9-B | PASS |
| A roster 6人 | PASS |
| B roster 6人 | PASS |
| 缺失 class_id -> 400 | PASS |
| 跨教师 -> 403 | PASS |
| Teacher AI 跨班拒绝 | PASS |
| 学生 011 多班 | PASS |
| 学生 012 无班 | PASS |

## 浏览器 E2E 状态
**NOT RUN** — 无浏览器自动化工具，需手工执行。

## 自动测试
- 16/16 unit tests PASS
- Python compile PASS
- JS syntax PASS

## 静态检查
- `_DEMO_STUDENTS` renamed to `class_student_ids`
- `landingStepStudents`: 0 残留
- `mcp_teacher_selected_students`: 0 残留
- `graph_update_events.json`: untracked

## Q1-Q12 回答
Q1: NO（无浏览器自动化，需手工）
Q2-Q10: 通过 API 验证，浏览器层面待手工
Q11: BLOCKER=0, HIGH=0
Q12: HEAD == origin/test = ec31d9c
