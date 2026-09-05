# TF-6C: Teacher Frontend Runtime Closure

**Branch**: fix/teacher-frontend-boot-roleui
**PR**: #9
**Start SHA**: 090e2f4 (TF-6B)
**Final SHA**: d71ce4f
**Date**: 2026-08-10
**Scope**: Frontend only — no new backend features

---

## P0 Fixes

| Block | Fix | Result |
|-------|-----|--------|
| TeacherUI load order | Moved sendCopilotMessage to teacher-ui.js; teacher-ui.js loads before app.js | No ReferenceError risk |
| Single Bootstrap | Removed old boot() + startAssessment() auto-run; only bootstrapApplication() | One startup entry point |
| Duplicate Auth | Removed doLogin/selectIdentity/selectJob/switchAccount from index.html; kept app.js implementations | Single auth source of truth |

## P1 Fixes

| Block | Fix |
|-------|-----|
| Role layout isolation | Added student-layout class to chat-layout; teacher-layout kept separate |
| Teacher Copilot container | sendCopilotMessage renders to #teacherChatMessages, not student #chatMessages |
| Submit dedup | Removed inline onsubmit; initCopilot() with bound guard fires once |
| 5 Tabs wired | Today (V2 issues), Insights (job graph), Students (master-detail), Feedback (comments stats), Standards (governance) |
| Issue Drawer | Real data loading with full detail: priority, confidence, severity, ability, students, generate candidates |
| Student Detail | Master-detail in new workspace DOM, not hidden old studentDetailContent |
| Job Graph targets | mainJobGraphDiagram and teacherJobGraphDiagram render to correct targets |
| Priority handling | priorityLevel() helper handles numeric values (0.0-1.0) avoiding "high" string comparison |
| HTML escaping | escHtml() applied to all user-facing strings, event delegation replaces inline onclick |
| Navigation guard | _navInitialized prevents double-binding tab handlers |

## Static Checks

| File | Result |
|------|--------|
| teacher-ui.js | PASS |
| app.js | PASS |
| graph-renderer.js | PASS |

## Files Changed

| File | Change |
|------|--------|
| web/teacher-ui.js | Complete rewrite (81 → ~430 lines): 5 tab loaders, issue drawer, student master-detail, copilot, api helper |
| web/app.js | Removed TeacherUI.sendCopilotMessage (top-level reference); updated teacher boot to use initCopilot |
| web/index.html | Script order fix (teacher-ui.js before app.js); removed old bootstrap auto-run; added student-layout class |
