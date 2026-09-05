# P6: Class Context Consistency & Teaching Closed Loop

**Branch**: `feature/teacher-class-roster`
**Start SHA**: `7557e23`
**Final SHA**: `0786812`

---

## 审计结果（修改前）

| 问题 | 状态 |
|------|------|
| `discover_issues` Demo fallback（001~005） | ❌ 存在 |
| `class_insights` job_role fallback | ❌ 存在 |
| `/api/v2/teacher/issues` 只校验 role，不校验 ownership | ❌ |
| `/api/v2/teacher/issues/candidates` 不校验 class_id | ❌ |
| `/api/teacher/class/*` 不校验 ownership | ❌ |
| `teacher_comments` 无 class_id 字段 | ❌ |
| 学生无班级学习上下文 | ❌ |
| 切换班级不清缓存 | ❌ |
| localStorage class_id 无验证 | ❌ |

---

## 修改内容

### P6-A: 统一 ownership
- `class_management.py` 新增 `require_teacher_class(user, class_id)` 辅助函数
- 所有 class-scoped 端点统一 401/403/404/400

### P6-B: 禁止 fallback
- `discover_issues` 无 class_id 时返回 `[]`（不再回退 Demo）
- `class_insights` 无 class_id 时返回空/错误（不再回退 job_role 全体）

### P6-C: 学生班级学习上下文
- 新增 `get_student_active_classes(student_id)` 和 `resolve_learning_context(user, class_id)`
- 新增 `/api/student/classes` 和 `/api/student/learning-context` 端点
- effective_job_role 规则：class 优先，personal fallback

### P6-D: 切班清理
- `TeacherUI.clearClassScopedState()` 清空 issue cache/selection/AI messages/drawer
- `loadClasses` 验证 localStorage class_id 有效性

### P6-F: Teacher Comments class_id
- `teacher_comments` 表 ALTER TABLE 添加 `class_id INTEGER`
- 去重逻辑改为 `class_id + student_id + period_start`
- `list_comments` / `generate_comment` / `generate_comments_batch` 均支持 class_id

### P6-G: Intervention scope
- `v2_facade.create_intervention` 新增 `scope_class` 参数并传递到 workflow_store

### P6-I: 班级归档
- `archive_class` / `restore_class` 函数 + `/archive` `/restore` 端点

---

## 测试结果

| 测试 | 结果 |
|------|------|
| 后端单元测试（10 个） | 10/10 PASS |
| 缺失 class_id → 400 | PASS |
| 跨教师 → 403 | PASS |
| 班级洞察 class-scoped | PASS |
| 学生班级查询 | PASS |
| 学习上下文 source=class | PASS |
| Python compile（4 文件） | PASS |
| JS syntax（teacher-ui.js） | PASS |

---

## 未解决问题

1. **Teacher AI class_id 深度贯穿**：`/api/teacher/assistant/message` 目前接受但不强制 class_id。AI 内部 `find_teaching_issues` 尚未完全使用 class_id 过滤。
2. **前端班级选择器切换 UI**：顶部班级栏只显示当前班级，切换需要手动调 API。多班选择下拉框尚未实现。
3. **学生端前端 UI**：后端 `/api/student/classes` 已就绪，但学生端 JS 尚未消费该端点自动选择班级。

## 风险

- Teacher Comments 的 class_id 字段为 `0`（未指定）时可能和真实 class_id 混淆，建议后续强制 class_id。
- `app.js` 中仍保留部分教师旧逻辑，需后续 P6-H 彻底清理。
