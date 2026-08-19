# Teacher Class & Student Management — Development Summary

**Branch**: `feature/teacher-class-roster`
**Base**: `test` @ `96f79ad`
**Scope**: P0 → P5 complete

---

## 完成内容

### P0: 班级数据模型
- 新增 `app/services/class_management.py`
- `classes` + `class_members` 两张表，复用 `data/users.db`
- 约束：一教师多班、一班一师、一班一岗位、一学生可多班

### P1: 班级 API
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/teacher/classes` | GET | 当前教师班级列表 |
| `/api/teacher/classes` | POST | 创建班级（teacher_id 从 JWT 取） |
| `/api/teacher/classes/{id}` | GET | 班级详情 |
| `/api/teacher/classes/{id}/update` | POST | 更新班级 |
| `/api/teacher/classes/{id}/students` | GET | 班级成员 |
| `/api/teacher/classes/{id}/students` | POST | 批量添加（返回 added/already/not_found） |
| `/api/teacher/classes/{id}/students/remove` | POST | 批量移除 |
| `/api/teacher/students/available` | GET | 可添加学生搜索 |

全部端点带 `teacher_required` JWT 守卫 + `class_id` ownership 校验。

### P2: 班级选择器 UI
- 顶部班级栏显示当前班级名称、人数、目标岗位
- 创建班级 modal（名称 + 岗位 + 可选学期）
- `mcp_teacher_class_id` 持久化当前班级

### P3: 学生管理 UI
- 管理学生 modal：搜索、多选、批量学号输入、移除
- 批量解析支持换行/逗号/空格分隔，返回 found/not_found
- 已在班学生显示 `in_current_class` 标记

### P4: 班级作用域接入
- `discover_issues(class_id, teacher_id)` 从班级成员解析学生 scope
- `get_class_ability_graph` / `get_common_issues` / `get_class_overview` 支持 `class_id`
- 前端 `loadToday` / `loadInsights` 传 `class_id`

### P5: 兼容清理
- `save_teacher_student_selection` 标记 `[DEPRECATED]`
- 新增 `tests/test_class_management.py`（4 个集成测试）

---

## 验证结果

| 测试 | 结果 |
|------|------|
| 后端单元测试（class CRUD/ownership） | 4/4 PASS |
| API 端到端（创建 → 加30人 → 查询 → 搜索 → class-scoped issues） | PASS |
| Python compile（class_management, server, v2_facade, class_insights） | PASS |
| JS syntax（teacher-ui.js, app.js） | PASS |

---

## 提交记录

| SHA | 提交 |
|-----|------|
| `9d27fe4` | Class data model + API |
| `e389df1` | Class selector UI + student management |
| `fc79514` | Class-scoped insights |
| `ae65a52` | Integration tests + deprecated selection |
