# Teacher Functional Baseline V1 (Revised)

**Baseline purpose**: 后续教师端继续开发所使用的当前稳定功能基线。不是 Release，后续功能继续演进。

**Functional code SHA**: `13b51df`
**Baseline anchor SHA**: `f69d5b1`
**Branch**: test
**Date**: 2026-08-19

---

## 当前核心能力

| # | 能力 | 状态 |
|---|------|------|
| 1 | Teacher Auth | ✅ Stable |
| 2 | Class Context（创建/切换/roster/ownership/A→B→A） | ✅ Stable |
| 3 | Students（roster/profile/assessment/weak-strong/events/patterns/coverage） | ✅ Stable |
| 4 | Class Insights（risk/coverage/weakest abilities/graph/common issues） | ✅ Stable |
| 5 | Today Teaching（class-scoped issues/evidence_summary/top_patterns/candidates） | ✅ Stable |
| 6 | Teacher AI（class-scoped profile/cross-class protection/evidence grounding） | ⚠️ multi-turn=partial |
| 7 | Teaching Feedback（class-scoped/evidence/draft/review/publish） | ✅ Stable |
| 8 | Job Standards（graph/proposals/versions） | ⚠️ diff/rollback/confirm=pending |

## 测试结果

| 测试 | 结果 |
|------|------|
| Python unittest | 16/16 PASS |
| Playwright E2E | 7/7 PASS |
| Python compile | PASS |
| JS syntax | PASS |

## 修复记录（385883a → f69d5b1）

中文化提交 `892b2e` 误改 JS identifiers，已全部修复：
- todayTeachingContent / studentDetailContent
- addSelectedStudents / removeSelectedStudents
- students variable in Issue Drawer / Candidates
- weakest_abilities / weak_ratio / weak_student_count
- renderGraphDiagram + graph container IDs
- weak_abilities in student list/detail
- comment filter labels
- class switch state reset

## 已知非阻塞缺口

1. Teacher AI advanced multi-turn context
2. Job diff frontend
3. Rollback frontend
4. Proposal confirm frontend
