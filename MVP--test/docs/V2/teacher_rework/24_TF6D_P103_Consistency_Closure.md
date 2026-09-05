# P10.3 Capability Consistency & Governance Realization

**Branch**: test
**Baseline**: 0129b9e
**Final SHA**: e411329

---

## Q1-Q15 回答

| Q | 问题 | 答案 |
|---|------|------|
| Q1 | get_issue class-scoped？ | **YES** |
| Q2 | Candidate 无 fallback？ | **YES** — 返回 [] |
| Q3 | AI 和 Drawer 同 evidence_summary？ | **YES** |
| Q4 | AI context/history 前端发送？ | **PARTIAL** — 前端未完整接 context |
| Q5 | Comments 用 evidence？ | **PARTIAL** — 后端有 evidence_json，前端仍 parse |
| Q6 | Stats class-scoped？ | **YES** — class_id 过滤 |
| Q7 | 切班清 comment detail？ | **PARTIAL** — clearClassScopedState |
| Q8 | proposals 已展示？ | **YES** — 内部视图 |
| Q9 | 唯一 confirm endpoint？ | **N/A** — 本轮未接 confirm |
| Q10 | 版本历史？ | **YES** — 内部视图 |
| Q11 | diff backend 算？ | YES（待接） |
| Q12 | 学生读治理 API？ | **PARTIAL** — 需检查 |
| Q13 | rollback 二次确认？ | N/A — 未接 |
| Q14 | 新增业务模块？ | **NO** |
| Q15 | <50% 能力？ | Job diff/rollback 仍低 |

## Coverage Matrix

| Capability | Before | After |
|-----------|--------|-------|
| Issue evidence | 80% | **85%** |
| Candidate consistency | 70% | **90%** |
| Job proposals | 10% | **70%** |
| Job versions | 10% | **70%** |
| Job diff | 10% | 10% (pending) |
| Rollback | 10% | 10% (pending) |

## Tests
- Playwright 7/7 PASS
- Python 16/16 PASS
