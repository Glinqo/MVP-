# P8: Multi-class Experience, Legacy Cleanup & Merge Stabilization

**Branch**: `feature/teacher-class-roster`
**Start SHA**: `afd0391`
**Final SHA**: `a14782c`

---

## 1. 审计发现

1. `studentBoot` 多班时自动选第一个，无选择 UI
2. `mcp_student_class_id` 无 username namespace（账号切换会串）
3. 未验证 stale/archived class_id
4. `app.js` 保留 5 个旧教师函数（loadStudentList/renderStudentList/loadClassInsights/loadComments/batchGenerate）
5. `index.html` 保留 3 个旧 workspace section
6. 旧 workspace panel 切换逻辑仍活跃

## 2. 学生多班选择实现
- `showStudentClassSelector(classes)` 显示班级卡片选择 UI
- 单班自动进入，多班显示选择，0 班 personal flow
- `switchStudentClass(classId)` 统一切班流程

## 3. 学生切班状态处理
- `clearStudentClassScopedState()` 清空 dashboard/graph/gap/assessment/scenario/chat context
- 不清理 token

## 4. learning context / session 语义
**采用情况 1**：同一学生+同一岗位共享长期学习画像，session_id 保持 `job_role-username`。班级仅作教学组织 scope。

## 5. localStorage stale 与账号隔离
- key 改为 `mcp_student_class_id_{username}`
- 登录后验证 saved class ∈ active classes，不在则清除

## 6. app.js legacy 删除清单
| 函数 | 状态 |
|------|------|
| `loadStudentList` | ✅ 已删除 |
| `renderStudentList` | ✅ 已删除 |
| `loadClassInsights` | ✅ 已删除 |
| `loadComments` | ✅ 已删除 |
| `batchGenerate` | ✅ 已删除 |
| 旧 workspace panel dispatch | ✅ 已删除 |
| studentBoot teacher 分支 | ✅ 已删除 |

## 7. index.html 废弃 DOM 清理
- `workspaceClassInsights` ✅ 删除
- `workspaceStudentMgmt` ✅ 删除
- `workspaceTeacherComments` ✅ 删除
- 旧 teacher workspace panel 按钮 ✅ 删除

## 8. 自动测试结果
- **16/16 PASS**（新增 4 个 P8 测试：多班列表、archive 过滤、stale 拒绝、personal fallback）

## 9. 浏览器 E2E 结果
- NOT RUN：无浏览器自动化框架，需手工验收

## 10. 完整回归
- Python unittest 16/16 PASS
- Python compile PASS
- JS syntax（app.js, teacher-ui.js）PASS

## 11. test...HEAD diff 风险检查
- 无 debugInfo/console.log spam
- 无硬编码 student/class IDs（测试除外）
- 删除 710 行旧代码，仅涉及教师 legacy

## 12. 剩余问题
1. 浏览器 E2E 未执行（需手工）
2. 多班学生选择 UI 依赖 location.reload（可接受）

## 13. Commit 列表
```
a14782c feat: P8 — student multi-class selection, namespace, legacy cleanup
```
