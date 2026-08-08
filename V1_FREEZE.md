# 管理端 V1 功能冻结点

**Commit**: d427453
**Date**: 2026-08-07
**Branch**: test

## 包含功能

- 教师工作台（Dashboard 概览）
- 学生管理（列表、搜索、筛选、详情、个人能力图谱、学习证据）
- 班级洞察（平均能力图谱、节点统计、共性问题发现）
- 教学评语（AI 草稿 → 教师编辑 → 审核 → 发布 → 学生查看）
- AI 教学助教（自然语言查询、action 导航、角色分流）
- 岗位图谱治理（当前图谱、岗位数据、更新审核、版本管理、Diff、Rollback）
- Teacher / Student RBAC（JWT + 服务端权限校验）
- 演示数据（5 名学生，测评 + 事件，可重复注入）

## 阶段对应

| 阶段 | 内容 | Archive |
|---|---|---|
| S1 | 管理岗基础拆分 | c92e5a2 |
| S2 | 学生管理 | 07c64b6 |
| S3 | 班级洞察 | db5711e |
| S4 | 教学评语 | 15f3532 |
| S5 | AI 教学助教 | 95f094a |
| S6 | 岗位图谱治理 | fbb63fd |
| S7 | 整体联调 | c7b6574 |
| S8 | 演示数据 | c3fd2a8 |
| S9 | 稳定性收尾 | d427453 |

## 已知限制

- 暂无正式 class_id，按 job_role 聚合学生
- 共性问题为规则聚合第一版（ability_id + event_category）
- 共性问题事件处理 500 条上限
- S5 Teacher AI intent 在部分服务器运行时有已知缓存问题
- 真实教师规模化试用尚未开展

## Demo 快速启动

```bash
python app/server.py --port 8765
python scripts/demo_data.py
# Teacher: 000 / 123456
# Student: 001 / 123456
```

## V2 建议

- 正式 class_id / 班级模型
- LLM 配置后的 Teacher AI 真实测试
- 共性问题算法升级
- 学生端教师评语 UI 完善
- 性能压测与大规模优化
