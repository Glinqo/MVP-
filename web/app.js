const state = {
  questions: [],
  jobProfile: null,
  messages: [],
  lastChat: null,
  lastDiagnosis: null,
  personalizedQuestions: [],
  personalizedPlan: null,
  studentDashboard: null,
  learnerContext: null,
  lastExplanation: null,
  explainPrompt: "",
  scenarios: [],
  activeScenario: null,
  graphUpdates: [],
  graphRenderers: {}, graphs: {
    job: null,
    student: null,
    current: null
  },
  activeWorkspace: "dashboard",
  activeGraphView: "job",
  sessionId: localStorage.getItem("mcp_session_id") || `demo-${Date.now()}`
};

// ── Persistence helpers ──────────────────────────────────────────
function persistSession() {
  localStorage.setItem("mcp_session_id", state.sessionId);
  try {
    localStorage.setItem("mcp_messages", JSON.stringify(state.messages.slice(-40)));
  } catch (e) { /* quota exceeded, ignore */ }
}

function restoreMessages() {
  try {
    const raw = localStorage.getItem("mcp_messages");
    return raw ? JSON.parse(raw) : [];
  } catch (e) { return []; }
}

function newSession() {
  localStorage.removeItem("mcp_session_id");
  localStorage.removeItem("mcp_messages");
  location.reload();
}

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderCompactItems(items, emptyText = "暂无") {
  if (!items || !items.length) return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  return `
    <ul class="compact-list">
      ${items.map((item) => {
        if (typeof item === "string") return `<li>${escapeHtml(item)}</li>`;
        const label = item.label || item.title || item.topic || item.name || item.id || "证据";
        const value = item.value || item.content || item.reason || item.deliverable || item.source || "";
        const source = item.source ? `<div class="muted">source: ${escapeHtml(item.source)}</div>` : "";
        return `<li><strong>${escapeHtml(label)}</strong>${value ? `<div>${escapeHtml(value)}</div>` : ""}${source}</li>`;
      }).join("")}
    </ul>
  `;
}

function renderLearnerContext(context) {
  if (!context) return "";
  const actions = context.next_best_actions || [];
  return `
    <div class="section-block">
      <h3>个人图谱摘要</h3>
      <p>${escapeHtml(context.summary || "暂无个人图谱证据。")}</p>
      ${actions.length ? `
        <ul class="compact-list">
          ${actions.slice(0, 4).map((item) => `<li><strong>${escapeHtml(item.ability_name)}</strong>：${escapeHtml(item.action || "")}</li>`).join("")}
        </ul>
      ` : '<p class="muted">完成一次问答、自测或讲题后，这里会出现下一步动作。</p>'}
    </div>
  `;
}

function renderCountChips(counts = {}) {
  const labels = {
    weak: "薄弱",
    improving: "提升中",
    recommended_next: "建议下一步",
    touched: "问答命中",
    mastered: "已掌握",
    unknown: "待确认"
  };
  return Object.entries(labels).map(([key, label]) => `
    <span class="dashboard-chip">${escapeHtml(label)} ${escapeHtml(counts[key] || 0)}</span>
  `).join("");
}

function dashboardToolButton(toolId, label, graphView = "") {
  return `<button type="button" data-dashboard-tool="${escapeHtml(toolId)}" ${graphView ? `data-dashboard-graph="${escapeHtml(graphView)}"` : ""}>${escapeHtml(label)}</button>`;
}

function attachDashboardActions(root) {
  root.querySelectorAll("[data-dashboard-tool]").forEach((button) => {
    button.addEventListener("click", () => {
      const tool = button.dataset.dashboardTool;
      if (tool === "chat") {
        closeWorkspace();
        $("chatInput").focus();
        return;
      }
      if (tool === "student_graph") {
        openWorkspace("graph", "student");
        return;
      }
      openWorkspace(tool, button.dataset.dashboardGraph);
    });
  });
  root.querySelectorAll("[data-dashboard-ask]").forEach((button) => {
    button.addEventListener("click", () => askFromTool(button.dataset.dashboardAsk));
  });
}

function renderStudentDashboard(data) {
  state.studentDashboard = data;
  const focus = data?.immediate_focus || [];
  const actions = data?.today_actions || [];
  const risks = data?.risk_flags || [];
  const recent = data?.evidence_summary?.recent_events || [];
  $("studentDashboard").classList.remove("muted");
  $("studentDashboard").innerHTML = data ? `
    <section class="dashboard-hero">
      <div>
        <p class="eyebrow">Readiness</p>
        <h3>${escapeHtml(data.readiness_level || "")}</h3>
        <p>${escapeHtml(data.headline || "")}</p>
        <div class="dashboard-chips">${renderCountChips(data.status_counts)}</div>
      </div>
      <div class="readiness-meter">
        <strong>${escapeHtml(data.readiness_score ?? 0)}</strong>
        <span>岗位准备度</span>
      </div>
    </section>

    <div class="dashboard-grid">
      <section class="dashboard-card">
        <h3>马上处理</h3>
        ${focus.length ? focus.map((item) => `
          <article class="focus-item">
            <div class="node-head">
              <strong>${escapeHtml(item.ability_name)}</strong>
              <span class="node-badge">${escapeHtml(item.status_label || statusLabel(item.status))}</span>
            </div>
            <p>${escapeHtml(item.reason || "")}</p>
            <p class="muted">掌握度 ${escapeHtml(item.mastery_score ?? "-")} · 置信度 ${escapeHtml(item.confidence ?? "-")}</p>
            <div class="question-actions">
              ${dashboardToolButton("student_graph", "看证据")}
              ${dashboardToolButton("plan", "生成训练单")}
              <button type="button" data-dashboard-ask="${escapeHtml(`请用现场排故方式讲解：${item.ability_name}`)}">问 AI 讲解</button>
            </div>
          </article>
        `).join("") : '<p class="muted">暂无能力证据，先问一个真实问题或做一次自测。</p>'}
      </section>

      <section class="dashboard-card">
        <h3>今日动作</h3>
        ${actions.length ? `
          <ol class="compact-list">
            ${actions.map((item) => `
              <li>
                <strong>${escapeHtml(item.title)}</strong>
                <div>${escapeHtml(item.action)}</div>
                <div class="question-actions">${dashboardToolButton(item.tool_id || "plan", item.tool_id === "chat" ? "回到对话" : "打开工具")}</div>
              </li>
            `).join("")}
          </ol>
        ` : '<p class="muted">暂无今日动作。</p>'}
      </section>

      <section class="dashboard-card">
        <h3>风险提醒</h3>
        ${risks.length ? risks.map((item) => `
          <div class="dashboard-risk ${escapeHtml(item.level || "")}">
            <strong>${escapeHtml(item.title)}</strong>
            <p>${escapeHtml(item.detail)}</p>
          </div>
        `).join("") : '<p class="muted">暂无高风险提醒。</p>'}
      </section>

      <section class="dashboard-card">
        <h3>推荐工具</h3>
        <div class="dashboard-tool-grid">
          ${(data.tool_suggestions || []).map((item) => `
            <button type="button" data-dashboard-tool="${escapeHtml(item.id === "student_graph" ? "student_graph" : item.id)}">
              <strong>${escapeHtml(item.label)}</strong>
              <span>${escapeHtml(item.reason || "")}</span>
            </button>
          `).join("")}
        </div>
      </section>
    </div>

    <section class="dashboard-card">
      <h3>最近证据</h3>
      ${recent.length ? `
        <ul class="item-list">
          ${recent.map((item) => `
            <li>
              <strong>${escapeHtml(item.event_type)} · ${(item.ability_names || []).map(escapeHtml).join("、")}</strong>
              <div>${escapeHtml(item.note || "")}</div>
              <div class="muted">${escapeHtml(item.created_at || "")} · source: ${escapeHtml(item.source || "")}</div>
            </li>
          `).join("")}
        </ul>
      ` : '<p class="muted">暂无学习证据。</p>'}
    </section>

    <section class="dashboard-card">
      <h3>自我批判与借鉴来源</h3>
      ${renderCompactItems(data.self_critique || [])}
      <p class="muted">借鉴：${(data.borrowed_from || []).map(escapeHtml).join("；")}</p>
    </section>
  ` : '<p class="muted">驾驶舱暂不可用。</p>';
  attachDashboardActions($("studentDashboard"));
}

// ── Inline Chat Cards ─────────────────────────────────────────────

function dotColor(label) {
  if (/匹配|现象|symptom/i.test(label)) return "match";
  if (/能力|ability/i.test(label)) return "ability";
  if (/知识|knowledge/i.test(label)) return "knowledge";
  return "context";
}

function renderEvidenceStrip(evidence) {
  if (!evidence || !evidence.length) return "";
  return `
    <div class="evidence-strip">
      ${evidence.map(item => `
        <span class="evi-tag">
          <span class="evi-dot ${dotColor(item.label)}"></span>
          ${escapeHtml(item.label)}: ${escapeHtml(String(item.value || ""))}
        </span>
      `).join("")}
    </div>
  `;
}

function renderReasoningBar(steps) {
  if (!steps || !steps.length) return "";
  return `
    <div class="reasoning-bar">
      ${steps.map((s, i) => {
        const arrow = i > 0 ? '<span class="rarrow">→</span>' : '';
        return `${arrow}<span class="rstep">${i + 1}. ${escapeHtml(typeof s === "string" ? s : (s.label || s.value || ""))}</span>`;
      }).join("")}
    </div>
  `;
}

function renderKnowledgeCards(refs) {
  if (!refs || !refs.length) return "";
  return refs.slice(0, 4).map(item => `
    <div class="kb-card-inline" data-kb-id="${escapeHtml(item.id || "")}" onclick="this.classList.toggle('expanded')">
      <div class="kbci-head">
        <span class="kbci-id">${escapeHtml(item.id || "")}</span>
        <span class="kbci-topic">${escapeHtml(item.topic || item.id || "")}</span>
        <span class="kbci-source">${escapeHtml(item.source || "")}</span>
      </div>
      <div class="kbci-content">${escapeHtml(item.content || "").replaceAll("\n", "<br>")}</div>
      <div class="kbci-tags">${(item.tags || []).slice(0, 3).map(t => `<span class="kbci-tag">${escapeHtml(t)}</span>`).join("")}</div>
      <div class="kbci-actions">
        <button type="button" data-ask="${escapeHtml(`请详细讲解「${item.topic || item.id}」这个知识点`)}" data-knowledge-id="${escapeHtml(item.id || "")}">追问</button>
      </div>
    </div>
  `).join("");
}

function renderAbilityCards(abilities) {
  if (!abilities || !abilities.length) return "";
  return abilities.slice(0, 3).map(item => `
    <div class="ability-card-inline">
      <div class="aci-head">
        <span class="aci-name">⚡ ${escapeHtml(item.name || item.id || "")}</span>
        <span class="aci-badge hit">已命中</span>
      </div>
      <div class="aci-reason">${escapeHtml(item.reason || item.description || "")}</div>
      <div class="aci-actions">
        <button type="button" data-ask="${escapeHtml(`请讲解「${item.name || item.id}」这个能力，结合我的问题说明怎么练。`)}" data-ability-id="${escapeHtml(item.id || "")}" data-explain-type="ability">问 AI 讲解</button>
      </div>
    </div>
  `).join("");
}

function renderTaskCards(tasks) {
  if (!tasks || !tasks.length) return "";
  return tasks.slice(0, 3).map(item => `
    <div class="task-card-inline">
      <div class="tci-head">
        <span class="tci-type ${escapeHtml(item.type || "training_task")}">${item.type === "learning_resource" ? "📖 学习资料" : "📋 实训任务"}</span>
        <span class="tci-title">${escapeHtml(item.title || "")}</span>
        ${item.estimated_minutes ? `<span class="tci-meta">约${item.estimated_minutes}分钟</span>` : ""}
      </div>
      <div class="tci-action">${escapeHtml(item.action || item.deliverable || "")}</div>
      <div class="tci-actions">
        <button type="button" data-ask="${escapeHtml(`我想做这个实训任务：「${item.title || ""}」，请告诉我具体步骤和安全注意事项。`)}">开始这个任务</button>
      </div>
    </div>
  `).join("");
}

function renderMessageCards(meta = {}) {
  const evidence = meta.evidence_used || [];
  const steps = meta.reasoning_steps || [];
  const refs = meta.knowledge_refs || [];
  const abilities = meta.highlighted_abilities || [];
  const tasks = meta.remediation_cards || [];

  const parts = [
    renderReasoningBar(steps),
    renderEvidenceStrip(evidence),
    renderKnowledgeCards(refs),
    renderAbilityCards(abilities),
    renderTaskCards(tasks),
  ].filter(Boolean);

  if (!parts.length) return "";

  return `<div class="chat-cards">${parts.join("")}</div>`;
}

function collectContext() {
  return {
    sensor_led: $("sensorLed").value,
    plc_input_led: $("plcInputLed").value,
    online_monitor: $("onlineMonitor").value,
    sensor_type: $("sensorType").value,
    common_terminal: $("commonTerminal").value
  };
}

function addMessage(role, content, meta = {}) {
  state.messages.push({ role, content, meta });
  renderMessages();
  persistSession();
}

function renderMessages() {
  $("chatMessages").innerHTML = state.messages.map((message) => {
    const roleLabel = message.role === "user" ? "我" : "AI";
    const safety = message.meta?.safety_notice
      ? `<div class="notice compact">${escapeHtml(message.meta.safety_notice)}</div>`
      : "";
    const fallback = message.meta?.fallback_used
      ? `<div class="message-meta">规则兜底回答</div>`
      : "";
    const extras = message.role === "assistant" ? renderMessageCards(message.meta) : "";
    return `
      <article class="message ${message.role}">
        <div class="message-role">${roleLabel}</div>
        <div class="message-body">
          ${safety}
          <div>${escapeHtml(message.content).replaceAll("\n", "<br />")}</div>
          ${extras}
          ${fallback}
        </div>
      </article>
    `;
  }).join("");
  attachAskButtons($("chatMessages"));
  $("chatMessages").scrollTop = $("chatMessages").scrollHeight;
}

function renderJobProfile(profile) {
  state.jobProfile = profile;
  const tasks = (profile.core_job_tasks || []).slice(0, 4);
  $("jobStrip").innerHTML = `
    <span>${escapeHtml(profile.role_name || "自动化生产线装调与运维技术员")}</span>
    <strong>${escapeHtml(profile.learner_stage || "职业新人")}</strong>
  `;
  $("jobProfile").innerHTML = `
    <div class="job-card-head">
      <div>
        <div class="muted">培训岗位</div>
        <strong>${escapeHtml(profile.role_name || "自动化生产线装调与运维技术员")}</strong>
      </div>
      <span>${escapeHtml(profile.learner_stage || "职业新人")}</span>
    </div>
    <p>${escapeHtml(profile.job_context || "")}</p>
    <div class="muted">本次任务：${escapeHtml(profile.mvp_focus_task || "传感器 NPN/PNP 接线与 PLC 输入信号排查")}</div>
    ${tasks.length ? `<ul class="compact-list">${tasks.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
  `;
}

function renderSuggestedQuestions(items) {
  $("suggestedQuestions").innerHTML = (items || []).map((item) => `
    <button type="button" data-question="${escapeHtml(item)}">${escapeHtml(item)}</button>
  `).join("");
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      $("chatInput").value = button.dataset.question;
      $("chatInput").focus();
    });
  });
}

function askFromTool(prompt) {
  const text = String(prompt || "").trim();
  if (!text) return;
  closeWorkspace();
  $("chatInput").value = text;
  sendChat(text);
}

function selectedAnswerForQuestion(questionId) {
  const fieldset = document.querySelector(`[data-question-id="${CSS.escape(questionId)}"]`);
  if (!fieldset) return "";
  const checked = Array.from(fieldset.querySelectorAll("input[type='checkbox']:checked, input[type='radio']:checked"))
    .map((item) => item.value);
  if (checked.length) return checked;
  const textInput = fieldset.querySelector("input[type='text']");
  return textInput ? textInput.value : "";
}

function closeExplainDrawer() {
  $("explainDrawer").classList.remove("open");
  $("explainDrawer").setAttribute("aria-hidden", "true");
}

function renderExplanation(data) {
  state.lastExplanation = data;
  $("explainTitle").textContent = data.title || "即时讲解";
  const safety = data.safety_notice ? `<div class="notice compact">${escapeHtml(data.safety_notice)}</div>` : "";
  $("explainContent").classList.remove("muted");
  $("explainContent").innerHTML = `
    ${safety}
    <div class="section-block">
      <p>${escapeHtml(data.explanation || "").replaceAll("\n", "<br />")}</p>
      ${data.answer_state ? `<p class="muted">状态：${escapeHtml(data.answer_state)}</p>` : ""}
      <h3>判断步骤</h3>
      ${renderCompactItems(data.reasoning_steps || [])}
      <h3>依据</h3>
      ${renderCompactItems(data.evidence_used || [])}
      <h3>相关能力</h3>
      ${renderCompactItems((data.ability_hits || []).map((item) => ({
        label: item.name || item.id,
        value: item.reason || item.description,
        source: item.source
      })))}
      <h3>知识引用</h3>
      ${renderCompactItems((data.knowledge_refs || []).map((item) => ({
        label: `${item.id || ""} ${item.topic || ""}`.trim(),
        value: item.content,
        source: item.source
      })))}
      <h3>建议任务/资源</h3>
      ${renderCompactItems([...(data.task_refs || []), ...(data.resource_refs || [])].map((item) => ({
        label: item.title || item.id,
        value: item.deliverable || item.use_when || item.url,
        source: item.source
      })))}
    </div>
  `;
  $("explainFollowups").innerHTML = (data.suggested_questions || []).map((item) => `
    <button type="button" data-explain-followup="${escapeHtml(item)}">${escapeHtml(item)}</button>
  `).join("");
  document.querySelectorAll("[data-explain-followup]").forEach((button) => {
    button.addEventListener("click", () => {
      state.explainPrompt = button.dataset.explainFollowup;
      $("continueExplainInChat").click();
    });
  });
}

async function openExplainDrawer(payload) {
  state.explainPrompt = payload.prompt || payload.message || "";
  $("explainDrawer").classList.add("open");
  $("explainDrawer").setAttribute("aria-hidden", "false");
  $("explainTitle").textContent = "讲解生成中";
  $("explainContent").classList.add("muted");
  $("explainContent").innerHTML = "正在根据题目、知识库和个人图谱生成讲解...";
  $("explainFollowups").innerHTML = "";
  try {
    const data = await api("/api/explain", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        context: collectContext(),
        ...payload
      })
    });
    renderExplanation(data);
    await refreshStudentGraph();
    await loadGraphUpdates();
    await loadStudentDashboard();
  } catch (error) {
    $("explainTitle").textContent = "讲解失败";
    $("explainContent").innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
}

function renderToolSuggestions(items) {
  document.querySelectorAll("[data-open-tool]").forEach((button) => {
    button.classList.remove("suggested");
  });
  for (const item of items || []) {
    const selector = {
      dashboard: '[data-open-tool="dashboard"]',
      job_graph: '[data-open-tool="graph"][data-graph-view="job"]',
      student_graph: '[data-open-tool="graph"][data-graph-view="student"]',
      graph: '[data-open-tool="graph"][data-graph-view="current"]',
      knowledge: '[data-open-tool="knowledge"]',
      tasks: '[data-open-tool="tasks"]',
      quiz: '[data-open-tool="quiz"]',
      scenario: '[data-open-tool="scenario"]',
      plan: '[data-open-tool="plan"]',
      teacher: '[data-open-tool="teacher"]'
    }[item.id];
    if (selector) document.querySelector(selector)?.classList.add("suggested");
  }
}

function statusLabel(status) {
  return {
    normal: "常规",
    core: "岗位核心",
    industry_hot: "行业高频",
    industry: "行业补充",
    weak: "薄弱",
    touched: "问答命中",
    improving: "正在提升",
    mastered: "已掌握",
    recommended_next: "建议下一步",
    unknown: "待确认"
  }[status] || status || "常规";
}

function renderGraphNodes(graph, targetId) {
  $(targetId).innerHTML = (graph?.nodes || []).map((node) => {
    const evidence = node.evidence?.length
      ? `<ul class="node-evidence">${node.evidence.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
      : "";
    const weight = node.demand_weight
      ? `<span class="node-badge weight">权重 ${escapeHtml(node.demand_weight)}</span>`
      : "";
    const score = node.mastery_score !== undefined
      ? `<div class="node-score"><span>掌握度 ${escapeHtml(node.mastery_score)}</span><span>置信度 ${escapeHtml(node.confidence)}</span></div>`
      : "";
    return `
      <div class="graph-node status-${escapeHtml(node.status || "normal")}">
        <div class="node-head">
          <strong>${escapeHtml(node.label)}</strong>
          <span class="node-badge">${escapeHtml(node.status_label || statusLabel(node.status))}</span>
        </div>
        <div class="muted">${escapeHtml(node.id)}</div>
        ${weight}
        ${score}
        ${evidence}
        <div class="muted">source: ${escapeHtml(node.source || "")}</div>
      </div>
    `;
  }).join("") || '<p class="muted">暂无图谱节点</p>';
  $(targetId).querySelectorAll(".graph-node").forEach((card, index) => {
    const node = graph?.nodes?.[index];
    if (!node) return;
    card.addEventListener("click", () => {
      showGraphNodeDetail(node, graph);
    });
  });
}

function graphColor(status) {
  return {
    weak: { fill: "#fff1f2", stroke: "#e11d48", text: "#881337" },
    industry_hot: { fill: "#fffbeb", stroke: "#d97706", text: "#78350f" },
    industry: { fill: "#eff6ff", stroke: "#2563eb", text: "#1e3a8a" },
    core: { fill: "#ecfdf5", stroke: "#059669", text: "#064e3b" },
    touched: { fill: "#eef2ff", stroke: "#4f46e5", text: "#312e81" },
    improving: { fill: "#ecfeff", stroke: "#0891b2", text: "#164e63" },
    mastered: { fill: "#f0fdf4", stroke: "#16a34a", text: "#14532d" },
    recommended_next: { fill: "#fff7ed", stroke: "#ea580c", text: "#7c2d12" },
    unknown: { fill: "#f8fafc", stroke: "#94a3b8", text: "#475569" }
  }[status] || { fill: "#ffffff", stroke: "#cbd5e1", text: "#172033" };
}

function splitLabel(label, maxLength = 12) {
  const text = String(label || "");
  if (text.length <= maxLength) return [text];
  const lines = [];
  for (let index = 0; index < text.length; index += maxLength) {
    lines.push(text.slice(index, index + maxLength));
  }
  return lines.slice(0, 3);
}

function graphDimensionLegend() {
  return [
    { label: "电气安全", fill: "#fef2f2", stroke: "#dc2626" },
    { label: "传感器/信号", fill: "#eff6ff", stroke: "#2563eb" },
    { label: "PLC 控制", fill: "#ecfdf5", stroke: "#059669" },
    { label: "排故诊断", fill: "#f5f3ff", stroke: "#7c3aed" }
  ];
}

function graphStatusLegend(graph) {
  const present = new Set((graph?.nodes || []).map((node) => node.status));
  const items = [
    { status: "industry_hot", label: "行业高频" },
    { status: "core", label: "岗位核心" },
    { status: "industry", label: "行业补充" },
    { status: "weak", label: "薄弱" },
    { status: "improving", label: "正在提升" },
    { status: "mastered", label: "已掌握" },
    { status: "recommended_next", label: "建议下一步" },
    { status: "touched", label: "问答命中" }
  ];
  const visible = items.filter((item) => present.has(item.status));
  return visible.length ? visible : items.slice(0, 3);
}

function renderGraphLegend(graph, targetId) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const legendId = `${targetId}Legend`;
  let legend = document.getElementById(legendId);
  if (!legend) {
    legend = document.createElement("div");
    legend.id = legendId;
    legend.className = "graph-legend-panel";
    target.parentNode.insertBefore(legend, target);
  }
  const statusItems = graphStatusLegend(graph);
  legend.innerHTML = `
    <div class="legend-block legend-note">
      <strong>读图规则</strong>
      <span>参考网络图：节点越大代表连接/证据越强；颜色代表能力社区；点击节点看证据。</span>
    </div>
    <div class="legend-block">
      <strong>颜色 = 能力维度</strong>
      <div class="legend-items">
        ${graphDimensionLegend().map((item) => `
          <span class="legend-chip">
            <i class="legend-dot" style="background:${item.fill};border-color:${item.stroke}"></i>${escapeHtml(item.label)}
          </span>
        `).join("")}
      </div>
    </div>
    <div class="legend-block">
      <strong>外环 = 节点状态</strong>
      <div class="legend-items">
        ${statusItems.map((item) => {
          const color = graphColor(item.status);
          const dashed = ["industry_hot", "industry", "recommended_next"].includes(item.status) ? " dashed" : "";
          return `
            <span class="legend-chip">
              <i class="legend-ring${dashed}" style="border-color:${color.stroke}"></i>${escapeHtml(item.label)}
            </span>
          `;
        }).join("")}
      </div>
    </div>
    <div class="legend-block">
      <strong>线条/大小</strong>
      <div class="legend-items">
        <span class="legend-chip"><i class="legend-line solid"></i>主链</span>
        <span class="legend-chip"><i class="legend-line dashed-line"></i>补充关系</span>
        <span class="legend-chip"><i class="legend-size sm"></i><i class="legend-size md"></i><i class="legend-size lg"></i>强度</span>
      </div>
    </div>
  `;
}

function renderGraphDiagram(graph, targetId) {
  const target = document.getElementById(targetId);
  const nodes = graph?.nodes || [];
  if (!nodes.length) {
    document.getElementById(`${targetId}Legend`)?.remove();
    target.innerHTML = '<p class="muted">暂无图谱数据</p>';
    return;
  }
  renderGraphLegend(graph, targetId);
  target.style.minHeight = '450px';
  if (!state.graphRenderers) state.graphRenderers = {};
  if (!state.graphRenderers[targetId]) {
    target.innerHTML = '';
    state.graphRenderers[targetId] = new ForceGraph(targetId, {
      onNodeClick: (node, g) => {
        const d = g.nodes.find(n => n.id === node.id);
        if (d) showGraphNodeDetail(d, g);
      }
    });
  }
  state.graphRenderers[targetId].update(graph);
  return;



}

function renderDemandSources(graph) {
  const sources = graph?.demand_sources || [];
  $("jobDemandSources").innerHTML = sources.length ? `
    <ul class="item-list">
      ${sources.map((item) => `
        <li>
          <strong>${escapeHtml(item.snapshot_id)} · ${escapeHtml(item.source_type)}</strong>
          <div>${escapeHtml(item.evidence)}</div>
          <div class="muted">${escapeHtml(item.collected_at)} · weight ${escapeHtml(item.weight)} · source: ${escapeHtml(item.source)}</div>
        </li>
      `).join("")}
    </ul>
  ` : '<p class="muted">暂无行业需求来源</p>';
}

function renderStudentEvidence(graph) {
  const weak = (graph?.nodes || []).filter((node) => node.status === "weak").length;
  const touched = (graph?.nodes || []).filter((node) => node.status === "touched").length;
  const next = (graph?.nodes || []).filter((node) => node.status === "recommended_next").length;
  const improving = (graph?.nodes || []).filter((node) => node.status === "improving").length;
  $("studentGraphEvidence").innerHTML = `
    <p>会话：${escapeHtml(graph?.session_id || state.sessionId)}</p>
    <p>已记录事件：${escapeHtml(graph?.event_count || 0)}</p>
    <p>薄弱节点：${weak}；正在提升：${improving}；问答命中：${touched}；建议下一步：${next}</p>
    <p class="muted">依据来自本地问答命中、确定性自测评分和学生反馈，不使用 LLM 自由评分。</p>
  `;
}

function renderGraphUpdateLog(updates) {
  state.graphUpdates = updates || [];
  $("graphUpdateLog").innerHTML = state.graphUpdates.length ? `
    <ul class="item-list">
      ${state.graphUpdates.slice(-8).reverse().map((item) => `
        <li>
          <strong>${escapeHtml(item.ability_name || item.ability_id)}</strong>
          <div>${escapeHtml(item.reason || "图谱证据更新")}</div>
          <div class="muted">${escapeHtml(item.event_type)} · ${escapeHtml(item.created_at || "")} · source: ${escapeHtml(item.source || "")}</div>
        </li>
      `).join("")}
    </ul>
  ` : '<p class="muted">暂无更新日志</p>';
}

function showGraphNodeDetail(node, graph) {
  const events = node.evidence_events || [];
  $("graphEvidencePanel").innerHTML = `
    <strong>${escapeHtml(node.label)}</strong>
    <p>状态：${escapeHtml(node.status_label || statusLabel(node.status))}；掌握度：${escapeHtml(node.mastery_score ?? "-")}；置信度：${escapeHtml(node.confidence ?? "-")}</p>
    <p>${(node.update_reasons || node.evidence || []).map(escapeHtml).join("；") || "暂无明确证据"}</p>
  `;
  $("nodeDetailContent").innerHTML = `
    <h3>${escapeHtml(node.label)}</h3>
    <p>状态：${escapeHtml(node.status_label || statusLabel(node.status))}</p>
    <div class="score-grid">
      <div class="metric"><strong>${escapeHtml(node.mastery_score ?? "-")}</strong><span>掌握度</span></div>
      <div class="metric"><strong>${escapeHtml(node.confidence ?? "-")}</strong><span>置信度</span></div>
      <div class="metric"><strong>${escapeHtml(node.evidence_count ?? 0)}</strong><span>证据总数</span></div>
      <div class="metric"><strong>${escapeHtml(node.avg_confidence ?? "-")}</strong><span>平均置信度</span></div>
    </div>
    <h3>证据来源分布</h3>
    ${node.source_types ? Object.entries(node.source_types).map(([src, cnt]) => `
      <div style="display:flex;justify-content:space-between;padding:2px 0;font-size:13px">
        <span>${escapeHtml(src)}</span><span>${escapeHtml(cnt)} 条</span>
      </div>
    `).join("") : '<p class="muted">暂无证据</p>'}
    <h3>最新证据</h3>
    ${node.latest_evidence && node.latest_evidence.length ? `
      <ul class="item-list">
        ${node.latest_evidence.slice(0, 3).map(function(ev) {
          return '<li><div style="font-size:12px">' + escapeHtml(ev.evidence_snippet || '') + '</div><div class="muted">' + escapeHtml(ev.source_type || '') + ' · ' + escapeHtml(ev.extracted_at || '') + ' · conf=' + escapeHtml(ev.confidence || '') + '</div></li>';
        }).join("")}
      </ul>
    ` : '<p class="muted">暂无最新证据</p>'}
    <h3>下一步</h3>
    <p>${escapeHtml(node.next_best_action || "先查看讲解，再完成一个关联训练任务。")}</p>
    <h3>版本历史</h3>
    <div id="versionInfo_${escapeHtml(node.id)}" style="font-size:12px;color:#64748b">加载中...</div>
    <h3>相关事件</h3>
    ${events.length ? `
      <ul class="item-list">
        ${events.map((event) => `
          <li>
            <strong>${escapeHtml(event.event_type || "event")}</strong>
            <div>${escapeHtml(event.reason || event.note || "")}</div>
            <div class="muted">${escapeHtml(event.created_at || "")} · source: ${escapeHtml(event.source || "")}</div>
          </li>
        `).join("")}
      </ul>
    ` : '<p class="muted">暂无事件记录</p>'}
    <div class="question-actions">
      <button type="button" data-ask="${escapeHtml(`请讲解“${node.label}”这个能力，结合我的问题说明怎么练。`)}" data-explain-type="ability" data-ability-id="${escapeHtml(node.id)}" data-event-type="ability_explained">问 AI 讲解</button>
      <button type="button" data-plan-node="${escapeHtml(node.id)}">生成培养方案</button>
    </div>
  `;
  attachAskButtons($("nodeDetailContent"));
  $("nodeDetailContent").querySelectorAll("[data-plan-node]").forEach((button) => {
    button.addEventListener("click", () => {
      openWorkspace("plan");
      loadPersonalizedPlan("today", button.dataset.planNode);
    });
  });
  // Load version list for this node
  fetch("/api/graph/job/versions").then(function(r) { return r.json(); }).then(function(data) {
    var verDiv = document.getElementById("versionInfo_" + node.id);
    if (verDiv && data.versions) {
      verDiv.innerHTML = "共 " + data.versions.length + " 个版本，最新：" + (data.versions[0] ? data.versions[0].version : "-");
    }
  }).catch(function() {});
  $("nodeDetailDrawer").classList.add("open");
  $("nodeDetailDrawer").setAttribute("aria-hidden", "false");
}

function closeNodeDetail() {
  $("nodeDetailDrawer").classList.remove("open");
  $("nodeDetailDrawer").setAttribute("aria-hidden", "true");
}

function renderGraph(graph, type = "current") {
  state.graphs[type] = graph || null;
  if (type === "job") {
    $("jobMermaidOutput").textContent = graph?.mermaid || "";
    renderGraphDiagram(graph, "jobGraphDiagram");
    renderGraphNodes(graph, "jobGraphList");
    renderDemandSources(graph);
    return;
  }
  if (type === "student") {
    $("studentMermaidOutput").textContent = graph?.mermaid || "";
    renderGraphDiagram(graph, "studentGraphDiagram");
    renderGraphNodes(graph, "studentGraphList");
    renderStudentEvidence(graph);
    renderGraphUpdateLog(graph?.update_log || []);
    return;
  }
  $("mermaidOutput").textContent = graph?.mermaid || "";
  renderGraphDiagram(graph, "currentGraphDiagram");
  renderGraphNodes(graph, "graphList");
  $("currentGraphMeta").textContent = graph?.nodes?.some((node) => node.status === "weak")
    ? "本次问题命中的能力节点已高亮为薄弱，请结合右侧知识缺口和实训任务补救。"
    : "提交问题后会显示本次暴露的能力缺口。";
}

function renderKnowledge(items) {
  $("knowledgeRefs").innerHTML = items?.length ? `
    <ul class="item-list">
      ${items.map((item) => `
        <li>
          <strong>${escapeHtml(item.id)} ${escapeHtml(item.topic)}</strong>
          <div>${escapeHtml(item.content)}</div>
          <div class="muted">source: ${escapeHtml(item.source)}</div>
        </li>
      `).join("")}
    </ul>
  ` : '<p class="muted">暂无</p>';
}

function renderTasks(items) {
  $("taskRefs").innerHTML = items?.length ? `
    <ul class="item-list">
      ${items.map((item) => `
        <li>
          <strong>${escapeHtml(item.title)}</strong>
          <div>${escapeHtml(item.action || item.deliverable)}</div>
          <div class="muted">${escapeHtml(item.type || item.difficulty || "")}${item.estimated_minutes ? ` · ${item.estimated_minutes} 分钟` : ""} · source: ${escapeHtml(item.source)}</div>
        </li>
      `).join("")}
    </ul>
  ` : '<p class="muted">暂无</p>';
}

function renderScenarioList() {
  $("scenarioList").innerHTML = state.scenarios.length ? `
    <div class="scenario-list">
      ${state.scenarios.map((scenario, index) => `
        <label class="scenario-option">
          <input type="radio" name="scenarioChoice" value="${escapeHtml(scenario.id)}" ${index === 0 ? "checked" : ""} />
          <span>
            <strong>${escapeHtml(scenario.title)}</strong>
            <small>${escapeHtml(scenario.initial_symptom || "")}</small>
          </span>
        </label>
      `).join("")}
    </div>
  ` : '<p class="muted">暂无排故角色扮演场景</p>';
}

function renderScenarioStage(data) {
  state.activeScenario = data;
  const scenario = data.scenario || {};
  const step = data.current_step;
  const feedback = data.feedback ? `
    <div class="${data.is_correct ? "notice compact" : "notice compact weak"}">
      <strong>${data.is_correct ? "判断正确" : "需要调整"}</strong>
      <div>${escapeHtml(data.feedback)}</div>
      <div>${escapeHtml(data.observation || "")}</div>
    </div>
  ` : "";
  if (!step) {
    $("scenarioStage").innerHTML = `
      ${feedback}
      <h3>${escapeHtml(scenario.title || "场景完成")}</h3>
      <p>${escapeHtml(data.status === "completed" ? "本轮排故角色扮演已完成，可以查看个人图谱或继续追问。" : "暂无下一步。")}</p>
      <div class="question-actions">
        <button type="button" data-ask="${escapeHtml(`复盘这个排故角色扮演：${scenario.title || ""}`)}">问 AI 复盘</button>
      </div>
    `;
    attachAskButtons($("scenarioStage"));
    return;
  }
  $("scenarioStage").innerHTML = `
    ${feedback}
    <h3>${escapeHtml(scenario.title || "")}</h3>
    <p>${escapeHtml(scenario.roleplay_frame || "")}</p>
    <div class="notice compact">${escapeHtml(scenario.safety_notice || "")}</div>
    <p><strong>${escapeHtml(step.prompt)}</strong></p>
    <div class="scenario-options">
      ${(step.options || []).map((option) => `
        <button type="button" data-scenario-choice="${escapeHtml(option.id)}">${escapeHtml(option.id)}. ${escapeHtml(option.text)}</button>
      `).join("")}
    </div>
    <div class="muted">命中能力：${(step.ability_hits || []).map((item) => escapeHtml(item.name || item.id)).join("、")}</div>
  `;
  $("scenarioStage").querySelectorAll("[data-scenario-choice]").forEach((button) => {
    button.addEventListener("click", () => submitScenarioStep(button.dataset.scenarioChoice));
  });
}

async function loadScenarios() {
  if (state.scenarios.length) {
    renderScenarioList();
    return;
  }
  try {
    const data = await api("/api/scenarios");
    state.scenarios = data.scenarios || [];
    renderScenarioList();
  } catch (error) {
    $("scenarioList").innerHTML = `<p class="muted">场景加载失败：${escapeHtml(error.message)}</p>`;
  }
}

async function startScenario() {
  await loadScenarios();
  const selected = document.querySelector("input[name='scenarioChoice']:checked")?.value || state.scenarios[0]?.id;
  if (!selected) return;
  $("scenarioStage").innerHTML = '<p class="muted">场景启动中...</p>';
  const data = await api("/api/scenario/start", {
    method: "POST",
    body: JSON.stringify({
      session_id: state.sessionId,
      scenario_id: selected
    })
  });
  renderScenarioStage(data);
  if (data.student_graph) renderGraph(data.student_graph, "student");
  await loadStudentDashboard();
}

async function submitScenarioStep(choiceId) {
  const scenarioId = state.activeScenario?.scenario?.id;
  const stepId = state.activeScenario?.current_step?.id;
  if (!scenarioId || !stepId || !choiceId) return;
  const data = await api("/api/scenario/step", {
    method: "POST",
    body: JSON.stringify({
      session_id: state.sessionId,
      scenario_id: scenarioId,
      step_id: stepId,
      choice_id: choiceId
    })
  });
  renderScenarioStage(data);
  if (data.student_graph) renderGraph(data.student_graph, "student");
  await loadGraphUpdates();
  await loadStudentDashboard();
}

function workspaceTitle(panel) {
  return {
    dashboard: "学习驾驶舱",
    graph: "能力图谱",
    knowledge: "知识缺口",
    tasks: "实训任务",
    scenario: "排故角色扮演",
    quiz: "自测验证",
    plan: "个人培养方案",
    teacher: "教师/师傅摘要"
  }[panel] || "功能工作台";
}

function setWorkspacePanel(panel) {
  state.activeWorkspace = panel;
  $("workspaceTitle").textContent = workspaceTitle(panel);
  document.querySelectorAll("[data-workspace-panel]").forEach((button) => {
    button.classList.toggle("active", button.dataset.workspacePanel === panel);
  });
  document.querySelectorAll(".workspace-panel").forEach((section) => {
    section.classList.toggle("active", section.id === `workspace${panel.charAt(0).toUpperCase()}${panel.slice(1)}`);
  });
  if (panel === "teacher") loadTeacherSummary();
  if (panel === "dashboard") loadStudentDashboard();
  if (panel === "plan") loadPersonalizedPlan();
  if (panel === "scenario") loadScenarios();
}

function setGraphView(view) {
  state.activeGraphView = view;
  document.querySelectorAll("[data-graph-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.graphView === view);
  });
  document.querySelectorAll(".graph-view").forEach((section) => {
    section.classList.toggle("active", section.id === `graphView${view.charAt(0).toUpperCase()}${view.slice(1)}`);
  });
}

async function refreshStudentGraph() {
  const graph = await api(`/api/graph/student?session_id=${encodeURIComponent(state.sessionId)}`);
  renderGraph(graph, "student");
  await loadGraphUpdates();
  return graph;
}

async function loadGraphUpdates() {
  const data = await api(`/api/graph/updates?session_id=${encodeURIComponent(state.sessionId)}`);
  renderGraphUpdateLog(data.updates || []);
}

async function loadStudentDashboard() {
  try {
    const data = await api(`/api/student/dashboard?session_id=${encodeURIComponent(state.sessionId)}`);
    renderStudentDashboard(data);
    return data;
  } catch (error) {
    $("studentDashboard").innerHTML = `<p class="muted">驾驶舱加载失败：${escapeHtml(error.message)}</p>`;
    return null;
  }
}

async function openWorkspace(panel, graphView) {
  $("workspaceOverlay").classList.add("open");
  $("workspaceOverlay").setAttribute("aria-hidden", "false");
  setWorkspacePanel(panel || "dashboard");
  if (panel === "graph" || graphView) {
    setGraphView(graphView || state.activeGraphView || "job");
    if ((graphView || state.activeGraphView) === "student") {
      await refreshStudentGraph();
    }
  }
}

function closeWorkspace() {
  $("workspaceOverlay").classList.remove("open");
  $("workspaceOverlay").setAttribute("aria-hidden", "true");
  closeNodeDetail();
}

function renderQuiz(questions) {
  state.questions = questions;
  $("quizCount").textContent = `${questions.length} 题`;
  $("quizForm").innerHTML = questions.map(renderQuestion).join("");
  attachAskButtons($("quizForm"));
}

function renderQuestion(question) {
  const options = question.options || [];
  const title = `<div class="question-title">${question.id}. ${escapeHtml(question.question)}</div>`;
  if (question.type === "multiple_choice") {
    return `
      <fieldset class="question" data-question-id="${question.id}" data-question-type="${question.type}">
        ${title}
        ${options.map((option) => `
          <label class="option"><input type="checkbox" name="${question.id}" value="${option.id}" /> ${option.id}. ${escapeHtml(option.text)}</label>
        `).join("")}
        ${questionAskActions(question)}
      </fieldset>
    `;
  }
  if (question.type === "ordering") {
    return `
      <fieldset class="question" data-question-id="${question.id}" data-question-type="${question.type}">
        ${title}
        ${options.map((option) => `<div class="option">${option.id}. ${escapeHtml(option.text)}</div>`).join("")}
        <input type="text" name="${question.id}" placeholder="例如：A,B,C,D,E,F" />
        ${questionAskActions(question)}
      </fieldset>
    `;
  }
  return `
    <fieldset class="question" data-question-id="${question.id}" data-question-type="${question.type}">
      ${title}
      ${options.map((option) => `
        <label class="option"><input type="radio" name="${question.id}" value="${option.id}" /> ${option.id}. ${escapeHtml(option.text)}</label>
      `).join("")}
      ${questionAskActions(question)}
    </fieldset>
  `;
}

function questionAskActions(question) {
  const prompt = question.ask_prompts?.[0] || `请讲解这道题：${question.question}`;
  return `
    <div class="question-actions">
      <button type="button" data-ask="${escapeHtml(prompt)}" data-event-type="question_explained" data-ability-id="${escapeHtml(question.ability_id || "")}" data-question-id="${escapeHtml(question.id || "")}" data-knowledge-id="${escapeHtml(question.knowledge_id || "")}">问 AI 讲解</button>
      <button type="button" data-ask="${escapeHtml(`这道题和我的传感器/PLC 排故问题有什么关系？题目是：${question.question}`)}" data-event-type="question_explained" data-ability-id="${escapeHtml(question.ability_id || "")}" data-question-id="${escapeHtml(question.id || "")}" data-knowledge-id="${escapeHtml(question.knowledge_id || "")}">联系我的问题</button>
    </div>
  `;
}

function attachAskButtons(root = document) {
  root.querySelectorAll("[data-ask]").forEach((button) => {
    button.addEventListener("click", async () => {
      const questionId = button.dataset.questionId || "";
      const explainType = button.dataset.explainType || (questionId ? "question" : button.dataset.abilityId ? "ability" : button.dataset.knowledgeId ? "knowledge" : "message");
      await openExplainDrawer({
        type: explainType,
        prompt: button.dataset.ask,
        message: button.dataset.ask,
        question_id: questionId,
        ability_id: button.dataset.abilityId,
        knowledge_id: button.dataset.knowledgeId,
        selected_answer: questionId ? selectedAnswerForQuestion(questionId) : "",
        event_type: button.dataset.eventType || "question_explained",
        source: "quiz_explain_button"
      });
    });
  });
}

async function recordStudentEvent(event) {
  try {
    const data = await api("/api/graph/student/event", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        ...event
      })
    });
    if (data.student_graph) renderGraph(data.student_graph, "student");
    await loadGraphUpdates();
    return data;
  } catch (error) {
    console.warn("recordStudentEvent failed", error);
    return null;
  }
}

function renderPersonalizedQuiz(questions) {
  state.personalizedQuestions = questions || [];
  $("personalizedQuiz").innerHTML = state.personalizedQuestions.length ? `
    <div class="personalized-head">
      <strong>已根据当前问答/薄弱点生成 ${state.personalizedQuestions.length} 道练习题</strong>
      <span class="muted">点击“问 AI 讲解”可以回到对话继续追问。</span>
    </div>
    <div class="quiz-list">
      ${state.personalizedQuestions.map((question) => `
        <article class="question personalized-card">
          <div class="question-title">${question.id}. ${escapeHtml(question.question)}</div>
          ${(question.options || []).map((option) => `
            <div class="option">${option.id}. ${escapeHtml(option.text)}</div>
          `).join("")}
          <details>
            <summary>查看答案与解析</summary>
            <p>答案：${escapeHtml(question.correct_answer)}</p>
            <p>${escapeHtml(question.explanation)}</p>
            <p class="muted">知识点：${escapeHtml(question.knowledge_id)} ${escapeHtml(question.knowledge_topic)} · source: ${escapeHtml(question.source)}</p>
          </details>
          ${questionAskActions(question)}
        </article>
      `).join("")}
    </div>
  ` : '<p class="muted">暂时没有可生成的个性化练习题。</p>';
  attachAskButtons($("personalizedQuiz"));
}

async function loadPersonalizedQuiz() {
  $("loadPersonalizedQuiz").disabled = true;
  $("loadPersonalizedQuiz").textContent = "生成中";
  try {
    const data = await api("/api/quiz/personalized", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        user_input: state.messages.filter((item) => item.role === "user").slice(-1)[0]?.content || "",
        weak_abilities: state.lastDiagnosis?.weak_abilities || [],
        highlighted_abilities: state.lastChat?.highlighted_abilities || [],
        limit: 4
      })
    });
    renderPersonalizedQuiz(data.questions || []);
  } catch (error) {
    $("personalizedQuiz").innerHTML = `<p class="muted">生成失败：${escapeHtml(error.message)}</p>`;
  } finally {
    $("loadPersonalizedQuiz").disabled = false;
    $("loadPersonalizedQuiz").textContent = "根据我的情况生成练习题";
  }
}

function renderJobProposals(proposals) {
  $("jobProposalList").innerHTML = proposals?.length ? `
    <ul class="item-list">
      ${proposals.map((proposal) => `
        <li>
          <strong>${escapeHtml(proposal.ability_name)} · ${escapeHtml(proposal.action)}</strong>
          <div>${escapeHtml(proposal.evidence)}</div>
          <div class="muted">${escapeHtml(proposal.proposal_id)} · delta ${escapeHtml(proposal.suggested_weight_delta)} · source: ${escapeHtml(proposal.source)}</div>
        </li>
      `).join("")}
    </ul>
  ` : '<p class="muted">暂无待确认建议</p>';
}

async function generateJobProposals() {
  const material = $("jobMaterialInput").value.trim();
  if (!material) {
    $("jobProposalList").innerHTML = '<p class="muted">请先粘贴岗位材料。</p>';
    return;
  }
  $("generateJobProposals").disabled = true;
  $("generateJobProposals").textContent = "生成中";
  try {
    const data = await api("/api/graph/job/proposals", {
      method: "POST",
      body: JSON.stringify({
        material,
        source_type: "teacher_curated",
        source: "web_workspace_input"
      })
    });
    renderJobProposals(data.proposals || []);
    const jobGraph = await api("/api/graph/job");
    renderGraph(jobGraph, "job");
  } catch (error) {
    $("jobProposalList").innerHTML = `<p class="muted">生成失败：${escapeHtml(error.message)}</p>`;
  } finally {
    $("generateJobProposals").disabled = false;
    $("generateJobProposals").textContent = "生成更新建议";
  }
}

async function confirmJobProposals() {
  $("confirmJobProposals").disabled = true;
  $("confirmJobProposals").textContent = "确认中";
  try {
    const data = await api("/api/graph/job/proposals/confirm", {
      method: "POST",
      body: JSON.stringify({
        confirm_all: true,
        confirmed_by: "demo_teacher"
      })
    });
    renderGraph(data.job_graph, "job");
    renderJobProposals(data.job_graph?.pending_proposals || []);
  } catch (error) {
    $("jobProposalList").innerHTML = `<p class="muted">确认失败：${escapeHtml(error.message)}</p>`;
  } finally {
    $("confirmJobProposals").disabled = false;
    $("confirmJobProposals").textContent = "确认全部待处理建议";
  }
}

function renderPersonalizedPlan(plan) {
  state.personalizedPlan = plan;
  state.learnerContext = plan?.learner_context || state.learnerContext;
  const today = plan?.today_training_sheet || null;
  const sevenDay = plan?.seven_day_plan || [];
  $("personalizedPlan").innerHTML = plan ? `
    <div class="notice compact">${escapeHtml(plan.safety_notice || "")}</div>
    <p><strong>${escapeHtml(plan.student_summary || "")}</strong></p>
    <p class="muted">模式：${escapeHtml(plan.plan_mode || "staged")} · 依据：${escapeHtml(plan.source || "")}</p>
    ${renderLearnerContext(plan.learner_context)}
    ${today ? `
      <article class="plan-card feature-plan">
        <div class="node-head">
          <h3>${escapeHtml(today.title || "今日训练单")}</h3>
          <span class="node-badge">${escapeHtml(today.estimated_minutes || "-")} 分钟</span>
        </div>
        <p><strong>${escapeHtml(today.objective || "")}</strong></p>
        <p class="muted">${escapeHtml(today.learner_snapshot || "")}</p>
        <h3>今日步骤</h3>
        <ol class="compact-list">
          ${(today.steps || []).map((step) => `
            <li>
              <strong>${escapeHtml(step.title)} · ${escapeHtml(step.minutes)} 分钟</strong>
              <div>${escapeHtml(step.action || "")}</div>
              <div class="muted">交付物：${escapeHtml(step.deliverable || "")}</div>
            </li>
          `).join("")}
        </ol>
        <h3>检查点</h3>
        <ul class="compact-list">
          ${(today.checkpoint_questions || []).map((question) => `<li>${escapeHtml(question.id || "")} ${escapeHtml(question.question || "")}</li>`).join("") || "<li>完成后记录已掌握/仍不会/需要更基础讲解。</li>"}
        </ul>
      </article>
    ` : ""}
    ${sevenDay.length ? `
      <article class="plan-card feature-plan">
        <h3>7 天补强计划</h3>
        <div class="timeline-list">
          ${sevenDay.map((day) => `
            <div class="timeline-item">
              <strong>Day ${escapeHtml(day.day)} · ${escapeHtml(day.title)}</strong>
              <p>${escapeHtml(day.focus)}：${escapeHtml(day.ability_name || "")}</p>
              <div class="muted">任务：${escapeHtml(day.task?.title || "")}；图谱目标：${escapeHtml(day.graph_update_goal || "")}</div>
            </div>
          `).join("")}
        </div>
      </article>
    ` : ""}
    <div class="plan-grid">
      ${(plan.learning_plan || []).map((stage) => `
        <article class="plan-card">
          <div class="node-head">
            <h3>${escapeHtml(stage.stage_title)}</h3>
            <span class="node-badge">${escapeHtml(statusLabel(stage.status))}</span>
          </div>
          <p>${escapeHtml(stage.text_explanation)}</p>
          <div class="node-score"><span>掌握度 ${escapeHtml(stage.mastery_score ?? "-")}</span><span>置信度 ${escapeHtml(stage.confidence ?? "-")}</span></div>
          <h3>知识点</h3>
          <ul class="compact-list">
            ${(stage.knowledge_cards || []).map((item) => `<li>${escapeHtml(item.id)} ${escapeHtml(item.topic)}</li>`).join("") || "<li>暂无知识点</li>"}
          </ul>
          <h3>视频讲解</h3>
          ${(stage.video_resources || []).length ? `
            <ul class="compact-list">
              ${stage.video_resources.map((item) => `<li><a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a></li>`).join("")}
            </ul>
          ` : `<p class="muted">${escapeHtml(stage.video_note || "暂无视频资源")}</p>`}
          <h3>实训任务</h3>
          <ul class="compact-list">
            ${(stage.practice_tasks || []).map((task) => `<li>${escapeHtml(task.title)}：${escapeHtml(task.deliverable || "")}</li>`).join("") || "<li>暂无匹配实训任务</li>"}
          </ul>
          <h3>检查点</h3>
          <ul class="compact-list">
            ${(stage.checkpoint_questions || []).map((question) => `<li>${escapeHtml(question.id)} ${escapeHtml(question.question)}</li>`).join("") || "<li>完成任务后重新做相关自测题</li>"}
          </ul>
        </article>
      `).join("")}
    </div>
    <p class="muted">${escapeHtml(plan.next_review || "")}</p>
  ` : '<p class="muted">尚未生成培养方案。</p>';
}

function planButtonByMode(planMode) {
  if (planMode === "today") return $("loadTodayPlan");
  if (planMode === "7_day") return $("loadSevenDayPlan");
  return $("loadPersonalizedPlan");
}

function planButtonText(planMode) {
  if (planMode === "today") return "今日训练单";
  if (planMode === "7_day") return "7 天补强计划";
  return "阶段方案";
}

async function loadPersonalizedPlan(planMode = "staged", abilityId = "") {
  const button = planButtonByMode(planMode);
  button.disabled = true;
  button.textContent = "生成中";
  try {
    const plan = await api("/api/plan/personalized", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        plan_mode: planMode,
        ability_id: abilityId
      })
    });
    renderPersonalizedPlan(plan);
  } catch (error) {
    $("personalizedPlan").innerHTML = `<p class="muted">生成失败：${escapeHtml(error.message)}</p>`;
  } finally {
    button.disabled = false;
    button.textContent = planButtonText(planMode);
  }
}

function collectAnswers() {
  const answers = {};
  document.querySelectorAll(".question").forEach((fieldset) => {
    const id = fieldset.dataset.questionId;
    const type = fieldset.dataset.questionType;
    if (type === "multiple_choice") {
      const selected = [...fieldset.querySelectorAll("input:checked")].map((item) => item.value);
      if (selected.length) answers[id] = selected;
      return;
    }
    if (type === "ordering") {
      const value = fieldset.querySelector("input")?.value.trim();
      if (value) answers[id] = value.split(/[,，\s>]+/).filter(Boolean);
      return;
    }
    const selected = fieldset.querySelector("input:checked");
    if (selected) answers[id] = selected.value;
  });
  return answers;
}

function renderScore(data) {
  const result = data.score_result || {};
  $("scoreResult").innerHTML = `
    <div class="metric"><strong>${result.score ?? "-"}</strong><span>总分</span></div>
    <div class="metric"><strong>${result.correct_count ?? "-"}/${result.total_count ?? "-"}</strong><span>答对题数</span></div>
    <div class="metric"><strong>${escapeHtml(result.feedback_level || "-")}</strong><span>反馈等级</span></div>
  `;
  $("weakAbilities").innerHTML = `
    <h3>薄弱能力</h3>
    ${(data.weak_abilities || []).length ? `
      <ul class="item-list">
        ${data.weak_abilities.map((item) => `
          <li class="weak"><strong>${escapeHtml(item.ability_name)}</strong><div>${escapeHtml(item.reason)}</div></li>
        `).join("")}
      </ul>
    ` : '<p class="muted">暂无薄弱能力。</p>'}
  `;
}

function applyChatResult(data) {
  state.lastChat = data;
  state.learnerContext = data.learner_context || state.learnerContext;
  addMessage("assistant", data.answer || "", {
    safety_notice: data.safety_notice,
    fallback_used: data.fallback_used,
    evidence_used: data.evidence_used || [],
    reasoning_steps: data.reasoning_steps || [],
    knowledge_refs: data.knowledge_refs || []
  });
  renderSuggestedQuestions(data.suggested_questions || []);
  renderToolSuggestions(data.tool_suggestions || []);
  renderGraph(data.ability_knowledge_view?.graph || {}, "current");
  if (data.student_graph) renderGraph(data.student_graph, "student");
  loadGraphUpdates();
  loadStudentDashboard();
  renderKnowledge(data.knowledge_gaps || []);
  renderTasks(data.remediation_cards || []);
}

async function sendChat(message) {
  const text = (message || $("chatInput").value).trim();
  if (!text) return;
  $("chatInput").value = "";
  addMessage("user", text);
  $("sendChat").disabled = true;
  $("sendChat").textContent = "发送中";
  try {
    const history = state.messages
      .filter((item) => item.role === "user" || item.role === "assistant")
      .slice(-8)
      .map((item) => ({ role: item.role, content: item.content }));
    const data = await api("/api/chat/message", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        message: text,
        learner_role: "职业新人",
        target_job_profile_id: state.jobProfile?.id,
        history,
        context: collectContext()
      })
    });
    applyChatResult(data);
  } catch (error) {
    addMessage("assistant", `请求失败：${error.message}`);
  } finally {
    $("sendChat").disabled = false;
    $("sendChat").textContent = "发送";
  }
}

async function submitDiagnosis() {
  $("submitDiagnosis").disabled = true;
  $("submitDiagnosis").textContent = "评分中";
  try {
    const data = await api("/api/diagnose", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        user_input: state.messages.filter((item) => item.role === "user").slice(-1)[0]?.content || "",
        answers: collectAnswers()
      })
    });
    state.lastDiagnosis = data;
    renderScore(data);
    renderGraph(data.ability_graph, "current");
    if (data.student_graph) renderGraph(data.student_graph, "student");
    await loadGraphUpdates();
    await loadStudentDashboard();
    renderKnowledge(data.knowledge_refs || []);
    renderTasks(data.task_recommendations || []);
  } catch (error) {
    alert(error.message);
  } finally {
    $("submitDiagnosis").disabled = false;
    $("submitDiagnosis").textContent = "提交自测评分";
  }
}

async function submitFeedback(feedback) {
  if (!state.lastChat && !state.lastDiagnosis) {
    $("feedbackStatus").textContent = "请先完成一次对话或自测。";
    return;
  }
  const source = state.lastDiagnosis || state.lastChat;
  const result = await api("/api/feedback", {
    method: "POST",
    body: JSON.stringify({
      session_id: state.sessionId,
      feedback,
      user_input: state.messages.filter((item) => item.role === "user").slice(-1)[0]?.content || "",
      score_result: source.score_result || {},
      weak_abilities: source.weak_abilities || source.highlighted_abilities || [],
      highlighted_abilities: source.highlighted_abilities || [],
      recommended_path: source.recommended_path || (source.remediation_cards || []).map((item) => item.title)
    })
  });
  $("feedbackStatus").textContent = `反馈已保存：${result.feedback}`;
  await refreshStudentGraph();
  await loadStudentDashboard();
}

async function loadTeacherSummary() {
  const data = await api("/api/teacher/summary");
  $("teacherSummary").innerHTML = `
    <p>会话数：${data.session_count}</p>
    <p>反馈统计：${escapeHtml(JSON.stringify(data.feedback_counts))}</p>
    <p>Top 薄弱点：${(data.top_weak_abilities || []).map((item) => `${escapeHtml(item.ability_name)}(${item.count})`).join("，") || "暂无"}</p>
    <p>${escapeHtml(data.teaching_suggestion)}</p>
  `;
}

async function boot() {
  try {
    const health = await api("/api/health");
    $("healthStatus").textContent = health.status === "ok" ? "已连接" : "异常";
    $("healthStatus").classList.add("ok");
    const [start, quiz, currentGraph, jobGraph, studentBootstrap, studentDashboard] = await Promise.all([
      api("/api/chat/start", { method: "POST", body: JSON.stringify({ session_id: state.sessionId }) }),
      api("/api/quiz"),
      api("/api/graph"),
      api("/api/graph/job"),
      api(`/api/student/bootstrap?session_id=${encodeURIComponent(state.sessionId)}`),
      api(`/api/student/dashboard?session_id=${encodeURIComponent(state.sessionId)}`)
    ]);
    state.learnerContext = studentBootstrap.learner_context || start.learner_context || null;
    renderJobProfile(start.job_profile || {});
    $("llmStatus").textContent = start.llm_configured ? "模型已配置" : "规则兜底";
    $("llmStatus").classList.toggle("ok", Boolean(start.llm_configured));

    // Restore previous messages if available, otherwise show welcome
    const saved = restoreMessages();
    if (saved.length > 0) {
      state.messages = saved;
      renderMessages();
    } else {
      addMessage("assistant", start.welcome || "");
    }
    renderSuggestedQuestions(start.suggested_questions || []);
    renderQuiz(quiz.questions);
    renderGraph(currentGraph, "current");
    renderGraph(jobGraph, "job");
    renderJobProposals(jobGraph.pending_proposals || []);
    renderGraph(studentBootstrap.student_graph, "student");
    renderGraphUpdateLog(studentBootstrap.student_graph?.update_log || []);
    renderStudentDashboard(studentDashboard);
  } catch (error) {
    $("healthStatus").textContent = "未连接";
    $("healthStatus").classList.remove("ok");
    $("quizCount").textContent = "加载失败";
    addMessage("assistant", `服务连接失败：${error.message}`);
  }
}

$("chatForm").addEventListener("submit", (event) => {
  event.preventDefault();
  sendChat();
});
$("submitDiagnosis").addEventListener("click", submitDiagnosis);
$("loadPersonalizedQuiz").addEventListener("click", loadPersonalizedQuiz);
$("loadPersonalizedPlan").addEventListener("click", () => loadPersonalizedPlan("staged"));
$("loadTodayPlan").addEventListener("click", () => loadPersonalizedPlan("today"));
$("loadSevenDayPlan").addEventListener("click", () => loadPersonalizedPlan("7_day"));
$("refreshDashboard").addEventListener("click", loadStudentDashboard);
$("startScenario").addEventListener("click", startScenario);
$("generateJobProposals").addEventListener("click", generateJobProposals);
$("confirmJobProposals").addEventListener("click", confirmJobProposals);
$("loadTeacherSummary").addEventListener("click", loadTeacherSummary);
document.querySelectorAll("[data-feedback]").forEach((button) => {
  button.addEventListener("click", () => submitFeedback(button.dataset.feedback));
});
document.querySelectorAll("[data-open-tool]").forEach((button) => {
  button.addEventListener("click", () => openWorkspace(button.dataset.openTool, button.dataset.graphView));
});
document.querySelectorAll("[data-workspace-panel]").forEach((button) => {
  button.addEventListener("click", () => setWorkspacePanel(button.dataset.workspacePanel));
});
document.querySelectorAll(".graph-tabs [data-graph-view]").forEach((button) => {
  button.addEventListener("click", () => setGraphView(button.dataset.graphView));
});
$("closeWorkspace").addEventListener("click", closeWorkspace);
$("closeNodeDetail").addEventListener("click", closeNodeDetail);
$("closeExplainDrawer").addEventListener("click", closeExplainDrawer);
$("continueExplainInChat").addEventListener("click", () => {
  const prompt = state.explainPrompt
    || state.lastExplanation?.suggested_questions?.[0]
    || state.lastExplanation?.title
    || "";
  closeExplainDrawer();
  askFromTool(prompt);
});
$("workspaceOverlay").addEventListener("click", (event) => {
  if (event.target === $("workspaceOverlay")) closeWorkspace();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && $("workspaceOverlay").classList.contains("open")) closeWorkspace();
  if (event.key === "Escape" && $("nodeDetailDrawer").classList.contains("open")) closeNodeDetail();
  if (event.key === "Escape" && $("explainDrawer").classList.contains("open")) closeExplainDrawer();
});


  // ForceGraph responsive resize
  window.addEventListener('resize', () => {
    setTimeout(() => {
      Object.values(state.graphRenderers || {}).forEach(function(gr) {
        if (gr && gr.resize) gr.resize();
      });
    }, 200);
  });

boot();
