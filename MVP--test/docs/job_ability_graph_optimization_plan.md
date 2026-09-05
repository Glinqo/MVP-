# 岗位能力图谱更新审查与优化方案

_面向当前 Mechatronics Agent MVP，聚焦岗位能力图谱更新、爬虫资料取舍与前端图谱可读性优化。_

---

## 📌 结论先行

这次“更新了但效果不好”的核心不是单一问题，而是三类问题叠加：

- **图谱运行失败**：前端 D3 边引用了 `role` 根节点，但节点数组里没有 `role`，会触发 `node not found: role`
- **图谱可视化失控**：标签避让函数既有未定义变量，又把节点本体推离画布，导致 SVG 生成了但用户看到空白
- **方案不可执行**：`deep-research-report.md` 更像后端深研资料库，范围过大、引用占位未落地、爬虫资源没有按 MVP 风险分层

已完成的代码级修复：

- `app/services/graph.py`：节点 payload 补充 `level`、`parent_id`、`description`、`radar_dimension_ids`
- `web/graph-renderer.js`：补虚拟根节点、修标签避让、约束节点坐标、按连接度/权重/证据数调整节点大小

后续方案应坚持一个原则：**岗位能力图谱的主链来自教师确认和权威/企业材料，爬虫只做证据补充和候选更新，不直接改正式图谱。**

---

## 🔎 问题审查

### 当前实现问题

| 问题 | 表现 | 根因 | 已处理 |
| --- | --- | --- | --- |
| 缺失根节点 | 首屏出现 `服务连接失败：node not found: role` | `edges` 中有 `from: "role"`，但 D3 `nodes` 中没有同名节点 | 已在前端补虚拟根节点 |
| 标签避让报错 | 控制台连续报 `ReferenceError: i is not defined` | `_resolveLabelOverlaps()` 使用未定义变量 | 已修复 |
| 节点飞出画布 | 画布空白，但 SVG 内有节点 | 标签避让直接修改节点坐标，强斥力继续放大位移 | 已改为只移动标签，并添加边界约束 |
| 维度配色失效 | 节点几乎只有默认色 | 后端没有传 `radar_dimension_ids` | 已补传字段 |
| 图谱含义不清 | 用户只看到节点，不知道大小/颜色/虚线含义 | 缺少图例和编码规则说明 | 待做 P1 |

### 方案文档问题

| 问题 | 影响 | 优化方向 |
| --- | --- | --- |
| 长报告范围过大 | MVP 团队不知道先做哪三件事 | 拆成“P0 可跑、P1 好用、P2 可扩展” |
| 引用是搜索占位 | Markdown 交付不可复核 | 真实外部资源用脚注 URL；内部材料用相对链接 |
| 技术栈过重 | 容易过早引入 Neo4j、Kafka、Airflow | 当前继续本地 JSON + Python API + 教师确认；规模上来再升级 |
| 爬虫资源未分层 | 容易把自媒体爬虫当主数据入口 | 社媒/内容平台只做弱信号；企业 JD/课程标准/官方资料做主证据 |
| 前端参考只停留在“好看” | 没转成编码规则 | 借鉴 Coppelia 的连接度、社区、过滤、缩放逻辑 |

---

## 🧭 优化后的更新闭环

```mermaid
flowchart LR
    accTitle: Job Graph Update Loop
    accDescr: MVP update loop from curated or public materials through extraction, teacher confirmation, versioned snapshots, and graph rendering

    source([📥 材料来源]) --> ingest[⚙️ 低频采集/导入]
    ingest --> extract[🔍 能力命中与证据抽取]
    extract --> proposal[📋 待确认建议]
    proposal --> review{🔍 教师确认?}
    review -->|通过| snapshot[📦 版本快照]
    review -->|退回| refine[✏️ 修订材料/规则]
    refine --> extract
    snapshot --> graph[📊 图谱渲染]
    graph --> audit([✅ 可解释验收])

    classDef start fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#3b0764
    classDef process fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a5f
    classDef decision fill:#fef9c3,stroke:#ca8a04,stroke-width:2px,color:#713f12
    classDef success fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d

    class source,audit start
    class ingest,extract,proposal,refine,snapshot,graph process
    class review decision
```

---

## 🕷️ 爬虫资料取舍

| 资料 | 适合放在 MVP 的位置 | 不建议做什么 |
| --- | --- | --- |
| MediaCrawler[^1] | 学习多平台采集项目结构；后续用于企业官号、公开视频、公开评论中的“新词/趋势弱信号” | 不作为默认岗位图谱主采集器；不在 MVP 做登录态、Cookie、代理、验证码、反检测 |
| CrawlerTutorial[^2] | 团队培训资料；补齐入门、并发、存储、抽象类等工程基础 | 不把教程案例直接复制成生产采集逻辑 |
| B 站爬虫课程[^3] | 与 CrawlerTutorial 配套学习；适合项目成员快速理解爬虫边界和工具链 | 不把视频内容本身作为岗位能力证据 |
| Scrapling[^4] | P1/P2 可选通用网页抽取框架，适合公开企业招聘页、公开 HTML、Markdown 化抽取和小规模 spider | 不用它绕过网站限制；不把“stealth”能力作为 MVP 目标 |
| Coppelia 图谱参考[^5] | 转成前端图谱编码规则：节点大小、社区颜色、过滤低连接节点、缩放查看 | 不照抄哲学史图的视觉密度；职业教育图谱必须更少节点、更强解释 |

MVP 的来源优先级建议：

1. 教师确认材料、课程标准、实训指导书
2. 官方/职业教育/行业标准
3. 企业公开 JD、企业公开任务资料
4. 招聘平台公开岗位摘要
5. 自媒体、社媒、评论、视频标题等弱信号

> ⚠️ 合规边界：当前 MVP 只处理岗位侧公开信息和校内授权材料，不采集简历、手机号、身份证、聊天记录、登录态个人页面或候选人画像。

---

## 🎨 前端图谱优化规则

参考 Coppelia 的关键不是复刻外观，而是复刻“网络图表达逻辑”：节点是实体，边是影响/依赖关系；节点和文字大小随连接度变化；高连接节点更靠中心；社区用颜色区分；低连接节点可过滤；缩放后能细看局部。[^5]

落到本 MVP：

| 视觉编码 | 当前规则 | 后续增强 |
| --- | --- | --- |
| 节点大小 | `degree + demand_weight + evidence_count` | 增加“教师确认次数”和“最近更新时间”权重 |
| 节点填充色 | `radar_dimension_ids`：安全、传感器、PLC、排故 | 增加图例，避免只靠颜色理解 |
| 节点外环 | `status`：行业高频、岗位核心、行业补充、薄弱、掌握等 | 统一虚线/实线语义 |
| 边样式 | 主链实线，行业补充虚线 | 增加边 tooltip：先修、证据补充、岗位扩展 |
| 标签 | 2–3 行短标签，标签避让不移动节点 | 高缩放时显示完整证据摘要 |
| 过滤 | 暂不默认过滤 | 增加“只看核心链 / 只看高频 / 显示全部” |

---

## 🛠️ 实施路线

### P0：让图谱可信可见

- [x] 修复 `role` 缺失导致的 D3 force link 报错
- [x] 修复标签避让未定义变量
- [x] 限制节点坐标，不再飞出画布
- [x] 后端补充维度字段，前端恢复维度配色
- [ ] 清理历史会话里的旧错误消息，避免修复后仍在聊天区残留误导

### P1：让图谱可读好用

- [ ] 在画布右上角增加图例：颜色=能力维度，外环=状态，虚线=行业补充
- [ ] 增加筛选：核心链、行业高频、待确认建议、全部
- [ ] 节点详情补“为什么重要”：主证据、来源、最近更新时间、教师确认状态
- [ ] 给 `role`、`student` 等根节点增加专门样式和不可误点行为

### P2：让更新链路可控扩展

- [ ] `knowledge/job_intelligence_sources.json` 增加来源风险等级：`primary_evidence`、`supporting_evidence`、`weak_signal`
- [ ] `scripts/job_intelligence_update.py` 输出来源风险和推荐动作
- [ ] 增加 Scrapling 适配层，但默认关闭，只用于公开页面和低频采集
- [ ] 增加“爬虫结果不能直接确认”的测试

---

## ✅ 验收标准

| 维度 | 标准 |
| --- | --- |
| 运行稳定 | 打开岗位能力图谱无 `node not found`、无前端 `ReferenceError` |
| 可见性 | SVG 至少渲染岗位图谱 15 个节点，所有节点坐标在画布范围内 |
| 可读性 | 不同能力维度有不同颜色；高权重/高连接节点更醒目 |
| 可解释性 | 点击节点能看到状态、证据、来源和下一步动作 |
| 更新安全 | 外部材料只生成待确认建议，正式图谱变更必须教师确认 |
| 文档可执行 | 方案里每个外部资源都有 URL；每个阶段都有明确“不做什么” |

---

## 🔗 References

[^1]: NanmiCoder. "MediaCrawler." GitHub. https://github.com/NanmiCoder/MediaCrawler

[^2]: NanmiCoder. "CrawlerTutorial." GitHub. https://github.com/NanmiCoder/CrawlerTutorial

[^3]: 程序员阿江-Relakkes. "1.Python爬虫入门前序介绍（万星爬虫仓库作者免费开课啦）." Bilibili. https://www.bilibili.com/video/BV1PsCdYjEyK

[^4]: D4Vinci. "Scrapling." GitHub. https://github.com/D4Vinci/Scrapling

[^5]: Simon Raper. "Graphing the history of philosophy." Coppelia. https://www.coppelia.io/graphing-the-history-of-philosophy
