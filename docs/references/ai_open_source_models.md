# AI Open Source Models Reference

来源：根目录导入文件 `与竞赛相关的AI开源模型.docx`

## 使用边界

这些项目作为竞赛方案调研和自研架构语言参考，不直接作为本 MVP 的整套运行依赖。当前方向是自研轻量应用优先，星辰 Agent 可作为后续可选导出渠道；第一版仍避免引入 Milvus、Neo4j、复杂数据库或大型平台依赖。

## 可借鉴点

| 项目 | 导入材料中的价值 | 本 MVP 的融入方式 |
| --- | --- | --- |
| KnowBook AI | 上传课件/教材后抽取知识点、生成知识图谱、问答溯源、薄弱点诊断、练习题生成 | 借鉴“资料 -> 图谱 -> 诊断 -> 推荐”闭环，落到本地 Retrieve、Graph、Diagnose、Recommend 服务 |
| Educational_RAG_System | 教育场景 RAG，支持多格式文档解析、混合检索、重排序 | 借鉴知识库检索思路，第一版先用本地 JSON 和关键词检索 |
| Inno Agent | 学习画像、知识库、跨会话检索和错因诊断 | 借鉴 `weak_abilities` 和 `recommended_path` 的结构化输出 |
| Campus-AI-RAG | 高校知识库问答和人工审核流程 | 借鉴“知识库回答需人工审核来源”的表达，不引入其技术栈 |
| Microsoft ai-agents-for-beginners | Agentic RAG、规划、多 Agent 基础课程 | 借鉴工作流节点拆分语言，不做多 Agent 大系统 |
| PAL 2.0 | 知识追踪、掌握度预测、个性化路径推荐 | 借鉴“薄弱点 -> 路径”概念，当前用确定性规则替代复杂模型 |
| EduAdapt AI | 知识追踪、强化学习路径推荐、学习风格检测 | 作为后续扩展方向，不进入 MVP |
| Asset Intelligence Graph-RAG | 制造业知识图谱和混合 RAG | 借鉴“岗位 -> 能力 -> 知识 -> 技能”的层级建模 |

## 答辩可用表述

本项目参考了教育 RAG、知识图谱和个性化学习系统的常见闭环，但第一版只做轻量自研 Demo，不搭建大型平台。MVP 交付本地可运行的知识库、诊断规则、评分代码、提示词和演示材料，重点验证“传感器 NPN/PNP 接线与 PLC 输入信号排查”的教学闭环。
