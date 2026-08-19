# TF-6B: Browser E2E, Full Regression, Performance Baseline & V2 Release Freeze

**Branch**: fix/teacher-frontend-boot-roleui
**Start SHA**: d2d6984 (TF-6A)
**Final SHA**: daf5b7d
**Date**: 2026-08-09

---

## TF-6B.1 Release Closure (daf5b7d)

| Fix | Result |
|-----|--------|
| /api/graph/student/event JWT + ownership guard | FIXED |
| /api/student/device-state JWT guard | FIXED |
| /api/score JWT guard | FIXED |
| /api/plan/task_feedback JWT guard | FIXED |
| Duplicate DOM ID studentListContainer | FIXED (renamed to studentListContainerBottom) |

---

## Static Gates

| Gate | Result |
|------|--------|
| JS syntax (all 4 .js files) | PASS |
| Python compile (app/) | PASS |
| Duplicate DOM IDs | 0 — PASS |

---

## Runtime & API

| Gate | Result |
|------|--------|
| Server boot (health=200) | PASS |
| V2 Facade + Workflow Store init | PASS |
| API smoke (7 endpoints) | PASS |
| Automated closed-loop E2E | PASS |
| P0 issues | 0 |
| P1 issues | 0 |

---

## Security Gates (TF-6B.1)

| Gate | Result |
|------|--------|
| /api/graph/student/event: no-auth → 401 | VERIFIED (code) |
| /api/graph/student/event: student X → 200 | VERIFIED (code) |
| /api/graph/student/event: student X writes Y → 403 | VERIFIED (code) |
| /api/student/device-state: no-auth | Now 401 |
| /api/score: no-auth | Now 401 |
| /api/plan/task_feedback: no-auth | Now 401 |
| Teacher governance write endpoints | All guarded (TF-6A) |
| Governance read endpoints (Student) | 403 |
| Conversation ownership | Enforced (TF-6A) |

---

## Performance Baseline (Local Dev)

| Operation | Events | Median | per-event |
|-----------|--------|--------|-----------|
| emit_event | 100 | 0.32s total | 3.19ms |
| emit_event | 1,000 | 2.97s total | 2.97ms |
| student_state | - | <1ms | - |
| discover_issues | - | 6.0ms | - |
| get_issue | - | 6.0ms | - |
| generate_candidates | - | 6.8ms | - |

**Key finding**: Linear scaling (2.97ms/event at 1k events). No O(N^2) detected.

---

## Browser E2E

| Phase | Result |
|-------|--------|
| Teacher login & Decision Workspace | NOT RUN — requires manual browser verification |
| Teaching Issue → Candidate → Draft → Review → Assign | NOT RUN |
| Refresh/restart persistence gate | NOT RUN |
| Student login & task execution | NOT RUN |
| Teacher AI Copilot grounding | NOT RUN |
| Role isolation (Student A → Student B) | NOT RUN |
| Qian regression (10 core functions) | NOT RUN |

> Browser E2E was attempted via in-app browser automation but the browser had no open tabs at runtime. All API chains are verified. Manual browser verification is recommended.

---

## Release Decision

| Question | Answer |
|----------|--------|
| API chain verified | YES |
| Security gaps closed | YES (4 new guards) |
| Performance baseline ok | YES (linear scaling) |
| Static gates pass | YES |
| Browser E2E | PENDING manual verification |
| P0 = 0 | YES |
| P1 = 0 | YES |
| Ready for manual browser E2E | YES |
| Ready for v2/integration-baseline | NOT YET — browser E2E pending |
