# Teacher Functional Baseline V1

**Baseline purpose**: 这是后续教师端继续开发所使用的当前稳定功能基线。不是 Release，不是最终产品版本，后续功能继续在此基础上演进。

**Baseline SHA**: 13b51df
**Branch**: test
**Date**: 2026-08-19

---

## 当前核心能力

| # | 能力 | 状态 |
|---|------|------|
| 1 | Teacher Auth（登录、角色隔离） | ✅ Stable |
| 2 | Class Context（创建、切换、roster、ownership、A→B→A） | ✅ Stable |
| 3 | Students（roster、profile、assessment、weak/strong、events、patterns、coverage） | ✅ Stable |
| 4 | Class Insights（risk、coverage、weakest abilities、graph、common issues） | ✅ Stable |
| 5 | Today Teaching（class-scoped issues、evidence_summary、top_patterns、candidates） | ✅ Stable |
| 6 | Teacher AI（class-scoped profile、cross-class protection、evidence grounding） | ⚠️ multi-turn=partial |
| 7 | Teaching Feedback（class-scoped、evidence、draft/review/publish） | ✅ Stable |
| 8 | Job Standards（graph、proposals、versions） | ⚠️ diff/rollback/confirm UI=pending |

## 测试结果

| 测试 | 结果 |
|------|------|
| Python unittest | 16/16 PASS |
| Playwright E2E | 7/7 PASS |
| Python compile | PASS |
| JS syntax | PASS |
| HTTP 500（正常流程） | 0 |
| pageerror（正常流程） | 0 |

## Governance 权限

- `/api/graph/job/proposals/pending`: teacher-only ✅
- `/api/graph/job/versions`: teacher-only ✅
- `/api/graph/job/versions/diff`: teacher-only ✅

## 已知非阻塞缺口

1. Teacher AI advanced multi-turn context
2. Job diff frontend
3. Rollback frontend
4. Proposal confirm frontend

## 后续开发规则

以后任何教师端 feature 合并到 test 前，必须至少：
- `pytest -q`
- `npx playwright test`
