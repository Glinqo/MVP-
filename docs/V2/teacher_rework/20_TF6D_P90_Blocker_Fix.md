# P9.0: Teacher Class Runtime Blocker Fix

**Branch**: test
**Final SHA**: 7d33c4c

---

## Q1: Teacher students Tab uses /classes/{class_id}/students?
**YES** — loadStudents now calls GET /api/teacher/classes/{id}/students.

## Q2: Class insights no longer calls /api/graph/job?
**YES** — loadInsights calls overview + ability-graph + common-issues.

## Q3: generateCandidates always includes class_id?
**YES** — request body includes class_id, and no request if currentClassId is null.

## Q4: Teacher B can operate Teacher A comments?
**NO** — comment endpoints enforce require_teacher_class ownership.

## Q5: Teacher AI blocks out-of-class patterns?
**YES** — get_process_patterns validates roster.

## Q6: AI intervention scope_class equals current class_id?
**YES** — create_intervention passes scope_class.

## Q7: duplicate doLogin/selectJob?
**NO** — index.html inline versions removed, app.js is single source.

## Q8: landingStepStudents deleted?
**YES** — entire DOM block removed.

## Q9: teacher workspace free of mcp_job_id?
**YES** — all replaced with TeacherUI.currentClass.job_role.

## Q10: graph_update_events.json untracked?
**YES** — git rm --cached + .gitignore.

---

## Test Results
- 16/16 unit tests PASS
- Python compile PASS
- JS syntax PASS
- Smoke test: class roster/overview/graph/issues/candidates all 200

## Commits
7d33c4c fix: P9.0 — wire teacher students/insights to class APIs
