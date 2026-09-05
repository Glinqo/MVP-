# V2-5 API 接入清单

## Evidence Engine
- [ ] GET /api/v2/events/emit
- [ ] GET /api/v2/events/query

## Learner State
- [ ] GET /api/v2/student/state
- [ ] GET /api/v2/teacher/students/{id}/state

## Process Diagnosis
- [ ] GET /api/v2/student/diagnostic-patterns

## Teaching Issue
- [ ] GET /api/v2/teacher/issues
- [ ] POST /api/v2/teacher/issues/discover

## Intervention
- [ ] POST /api/v2/teacher/issues/{id}/candidates
- [ ] GET /api/v2/teacher/interventions
- [ ] POST /api/v2/teacher/interventions/{id}/review
- [ ] POST /api/v2/teacher/interventions/{id}/assign

## Outcome
- [ ] POST /api/v2/teacher/interventions/{id}/evaluate
- [ ] GET /api/v2/teacher/interventions/{id}/outcome
