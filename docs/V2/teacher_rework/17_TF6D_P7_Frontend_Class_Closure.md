# P7: Frontend Class Closure & Teacher AI Deep Class Scoping

**Branch**: `feature/teacher-class-roster`
**Start SHA**: `d03ad9e`
**Final SHA**: `4a988d2`

---

## 审计发现

1. `TeacherAIV2.find_teaching_issues()` 只传 `job_role`，未使用 class_id
2. `get_student_state()` 可查询任意学生，不验证班级
3. `generate_intervention_candidates()` 不验证目标学生属于班级
4. Teacher AI context 无 class_id 绑定
5. 教师顶部班级栏纯展示，不可切换
6. 学生端未调用 `/api/student/classes`
7. `app.js` 中 `loadStudentList`/`loadClassInsights`/`loadComments` 与 `teacher-ui.js` 重复

---

## Teacher AI class_id 调用链（修复后）

```text
/api/teacher/assistant/message
  ↓ class_id
handle_teacher_message_v2(class_id)
  ↓ context.class_id 绑定（不匹配则 reset）
TeacherAIV2.find_teaching_issues(class_id, teacher_id)
  ↓ discover_issues(class_id, teacher_id)
  ↓ get_class_students → roster
  ↓ 仅本班学生 LearnerState + patterns
```

学生状态查询：
```text
TeacherAIV2.get_student_state(student_id, class_id, teacher_id)
  ↓ get_class_students → roster
  ↓ 验证 student_id ∈ roster
  ↓ 不在 → {"status": "not_in_class"}
```

---

## 教师切班前端实现

- `switchTeacherClass(classId)`：清缓存 → 更新 state → 刷新当前 Tab → 关闭下拉
- 顶部班级栏可点击，打开班级下拉（含切换、创建、管理）
- `setCurrentClass` 更新 AI scope 显示
- `sendCopilotMessage` 自动附带 class_id

## 学生 learning context

- `studentBoot` 调用 `/api/student/classes`
- 单班自动选择，多班取 localStorage 或第一个
- 班级 `job_role` 覆盖个人 `job_role` 形成 effective learning context
- `mcp_student_class_id` 持久化

## app.js 旧教师代码清理

- 从 `teacherBoot` 移除 `loadStudentList()` 调用
- `loadStudentList`/`loadClassInsights`/`loadComments` 仍保留供旧 workspace 兼容，但不再由 teacherBoot 主动调用
- 教师工作区由 `teacher-ui.js` 完全接管

---

## 测试结果

| 测试 | 结果 |
|------|------|
| 单元测试（12 个） | 12/12 PASS |
| Teacher AI 跨班学生查询 → not_in_class | PASS |
| Teacher AI candidates 班外学生过滤 | PASS |
| Python compile（teacher_ai_v2, server） | PASS |
| JS syntax（teacher-ui.js, app.js） | PASS |

---

## Q1: Teacher AI 查询学生前验证班级？

**是**。`TeacherAIV2.get_student_state(student_id, class_id, teacher_id)` 先调用 `get_class_students` 构建 roster，验证 `student_id` 是否在 roster 中，不在则返回 `{"status": "not_in_class"}`。

## Q2: 学生班级 effective_job_role 来自 class.job_role？

**是**。`studentBoot` 调用 `/api/student/classes` 后，若有班级则 `jobId = selectedClass.job_role` 覆盖个人 `mcp_job_id`。后端 `resolve_learning_context()` 同样遵循 class 优先规则。

## Q3: teacher-ui.js 和 app.js 是否仍有重复教师控制？

**部分清理**。`teacherBoot` 已移除 `loadStudentList()`，教师导航和 Tab 完全由 `teacher-ui.js` 控制。但 `app.js` 中 `loadStudentList`/`loadClassInsights`/`loadComments` 函数定义仍保留（供旧 workspace DOM 兼容），只是不再被教师主流程调用。

---

## 剩余风险

1. `app.js` 旧 workspace panel 切换逻辑（2032-2034 行）仍存在，但不在主流程触发
2. 多班学生选择 UI 尚未实现（前端自动选第一个，未显示选择 modal）
3. 学生端 `mcp_student_class_id` 未验证失效情况
