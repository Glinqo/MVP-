const state = {
  questions: [],
  jobProfile: null,
  jobAdmin: {
    documents: [],
    posts: [],
    proposals: [],
    versions: [],
    graph: null
  },
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
  },
  activeWorkspace: "graph",
 activeGraphView: "job",
  completedSteps: JSON.parse(localStorage.getItem("completed_steps") || "[]"),
 sessionId: localStorage.getItem("mcp_session_id") || `demo-${Date.now()}`,
  selectedJobId: null,
  jobName: null
};

const DEFAULT_JOB_ROLE = "自动化生产线装调与运维技术员";

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
    var msgs = raw ? JSON.parse(raw) : [];
    msgs.forEach(function(m) { if (!m.id) m.id = Date.now().toString(36)+Math.random().toString(36).slice(2,8); });
    return msgs;
  } catch (e) { return []; }
}

function createNewChat() {
  var newId = "demo-" + Date.now();
  state.sessionId = newId;
  state.messages = [];
  localStorage.setItem("mcp_session_id", newId);
  renderMessages();
}

function newSession() {
  localStorage.removeItem("mcp_session_id");
  localStorage.removeItem("mcp_messages");
  location.reload();
}

const $_raw = (id) => document.getElementById(id);
const $ = (id) => {
  const el = $_raw(id);
  if (!el) {
    return new Proxy({}, {
      get(t, prop) {
        if (prop === "classList") return { add() {}, remove() {}, toggle() {}, contains() { return false; } };
        if (prop === "addEventListener") return () => {};
        return () => {};
      },
      set(t, prop, value) { return true; }
    });
  }
  return el;
};

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
        openWorkspace("knowledge");
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
      </div>
      <div class="kbci-content">${escapeHtml(item.content || "").replaceAll("\n", "<br>")}</div>
      <div class="kbci-source">${escapeHtml(item.source || "")}</div>
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

function addMessage(role, content, meta) {
  if (meta === undefined) meta = {};
  state.messages.push({ id: Date.now().toString(36)+Math.random().toString(36).slice(2,8), role: role, content: content, meta: meta, time: Date.now() });
  renderMessages();
  persistSession();
  // AI title generation on first user message
  if (role === "user" && state.messages.filter(function(m) { return m.role === "user"; }).length === 1) {
    if (typeof generateAITitle === "function") setTimeout(function() { generateAITitle(state.sessionId); }, 800);
  }

}

function renderMessages() {
  $("chatMessages").innerHTML = state.messages.map((message) => {
    if (message.role === "typing") {
      return '<article class="message typing"><div class="message-body"><span class="typing-dots"><span></span><span></span><span></span></span></div></article>';
    }
    const roleLabel = message.role === "user" ? "我" : "AI";
    const safety = message.meta?.safety_notice
      ? `<div class="notice compact">${escapeHtml(message.meta.safety_notice)}</div>`
      : "";
    const fallback = message.meta?.fallback_used
      ? `<div class="message-meta">规则兜底回答</div>`
      : "";
    const extras = message.role === "assistant" ? renderMessageCards(message.meta) : "";
    var _ts = message.time ? (typeof formatMsgTime==="function"?formatMsgTime(message.time):"") : "";
    var _btns = '<button class="msg-action-btn copy" onclick="copyMsg(this)" title="Copy">C</button>' + (message.role==="user"?('<button class="msg-action-btn edit" onclick="editMessage(\'' + message.id + '\')\" title="编辑">\u270e</button>'):"") +
        (message.role==="assistant"?('<button class="msg-action-btn retry" onclick="retryMessage(\'' + message.id + '\')\" title="重新生成">\u21bb</button>'):"") ;
    var footerHtml = message.id ? '<div class="msg-footer"><span class="msg-time">' + _ts + '</span><span class="msg-actions">' + _btns + '</span></div>' : "";
    return `
      <article class="message ${message.role}">
        <div class="message-role">${roleLabel}</div>
        <div class="message-body">
          ${safety}
          <div>${escapeHtml(message.content).replaceAll("\n", "<br />")}</div>
          ${extras}
          ${fallback}
          ${footerHtml}
        </div>
      </article>
    `;
  }).join("");
  attachAskButtons($("chatMessages"));
  $("chatMessages").scrollTop = $("chatMessages").scrollHeight;
}

function editMessage(id) {
  var idx = state.messages.findIndex(function(m) { return m.id === id; });
  if (idx === -1 || state.messages[idx].role !== "user") return;
  $("#chatInput").value = state.messages[idx].content;
  state.messages.splice(idx, 1);
  renderMessages();
  persistSession();
  $("#chatInput").focus();
}

function deleteMessage(id) {
  var idx = state.messages.findIndex(function(m) { return m.id === id; });
  if (idx === -1) return;
  state.messages.splice(idx, 1);
  renderMessages();
  persistSession();
}

function retryMessage(id) {
  var idx = state.messages.findIndex(function(m) { return m.id === id; });
  if (idx === -1) return;
  var prev = state.messages[idx-1];
  if (!prev || prev.role !== "user") return;
  state.messages.splice(idx-1, 2);
  renderMessages();
  persistSession();
  sendChat(prev.content);
}




function copyMsg(btn) {
  var article = btn.closest("article");
  if (!article) return;
  var body = article.querySelector(".message-body");
  if (!body) return;
  var text = (body.textContent || "").trim();
  if (!text) return;
  navigator.clipboard.writeText(text).then(function() {
    btn.classList.add("copied");
    btn.textContent = "✓";
    setTimeout(function() { btn.classList.remove("copied"); btn.textContent = "复制"; }, 1200);
  }).catch(function() {});
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
      job_admin: '[data-open-tool="jobAdmin"]',
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
      <strong>${targetId.includes("student") ? "外环 = 掌握度" : "外环 = 节点状态"}</strong>
      <div class="legend-items">
        ${targetId.includes("student")
          ? '<span class="legend-chip"><i class="legend-ring mastery-ring-legend" style="border-color:#22c55e"></i>绿色进度 = 掌握度</span>'
          : statusItems.map((item) => {
              const color = graphColor(item.status);
              const dashed = ["industry_hot", "industry", "recommended_next"].includes(item.status) ? " dashed" : "";
              return '<span class="legend-chip"><i class="legend-ring' + dashed + '" style="border-color:' + color.stroke + '"></i>' + escapeHtml(item.label) + '</span>';
            }).join("")
        }
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

function renderStrategyTags(node) {
  const tags = node.strategy_tags || [];
  const gate = node.safety_gate;
  if (!tags.length && !gate) return "";
  return `
    <h3>策略与安全门</h3>
    <div class="strategy-tags">
      ${gate ? `<span class="strategy-tag ${gate.passed ? "ok" : "warn"}">${gate.passed ? "安全门通过" : "安全需复核"}：${escapeHtml(gate.reason || "")}</span>` : ""}
      ${tags.map((tag) => `<span class="strategy-tag warn">${escapeHtml(tag.label || tag.tag)}${tag.persistence ? ` · ${escapeHtml(tag.persistence)}` : ""}</span>`).join("")}
    </div>
  `;
}

function renderProcessMetrics(node) {
  const metrics = node.process_metrics || {};
  const items = [
    ["safety_compliance", "安全顺序"],
    ["evidence_quality", "证据质量"],
    ["fault_localization", "故障定位"],
    ["diagnostic_efficiency", "排故效率"],
    ["closure_verification", "闭环验证"]
  ].filter(([key]) => metrics[key] !== undefined && metrics[key] !== null);
  if (!items.length) return "";
  return `
    <h3>排故过程指标</h3>
    <div class="process-metrics">
      ${items.map(([key, label]) => `<span>${escapeHtml(label)} ${escapeHtml(Math.round(Number(metrics[key] || 0) * 100))}</span>`).join("")}
    </div>
  `;
}

function renderEvidenceTimeline(node, events) {
  const normalized = node.normalized_events || [];
  const process = node.process_evidence || [];
  const merged = [
    ...normalized.map((event) => ({
      type: event.event_type,
      reason: event.evidence_summary,
      created_at: event.created_at,
      source: event.source,
      outcome: event.outcome
    })),
    ...process.map((event) => ({
      type: "diagnostic_action",
      reason: `${event.action_id || ""} / ${event.classification || ""}`,
      created_at: event.timestamp,
      source: event.source,
      outcome: event.classification
    })),
    ...(events || [])
  ].filter((event) => event.type || event.reason);
  if (!merged.length) return '<p class="muted">暂无事件记录</p>';
  return `
    <ol class="evidence-timeline">
      ${merged.slice(-8).reverse().map((event) => `
        <li>
          <strong>${escapeHtml(event.type || "event")}${event.outcome ? ` · ${escapeHtml(event.outcome)}` : ""}</strong>
          <div>${escapeHtml(event.reason || event.note || "")}</div>
          <div class="muted">${escapeHtml(event.created_at || "")} · source: ${escapeHtml(event.source || "")}</div>
        </li>
      `).join("")}
    </ol>
  `;
}

function showGraphNodeDetail(node, graph) {
  const events = node.evidence_events || [];
  $("graphEvidencePanel").innerHTML = `
    <strong>${escapeHtml(node.label)}</strong>
    <p>状态：${escapeHtml(node.status_label || statusLabel(node.status))}；掌握度：${escapeHtml(node.mastery_score ?? "-")}；认知分：${escapeHtml(node.cognitive_mastery_score ?? "-")}；置信度：${escapeHtml(node.confidence ?? "-")}</p>
    <p>${(node.update_reasons || node.evidence || []).map(escapeHtml).join("；") || "暂无明确证据"}</p>
  `;
  $("nodeDetailContent").innerHTML = `
    <h3>${escapeHtml(node.label)}</h3>
    <p>状态：${escapeHtml(node.status_label || statusLabel(node.status))}</p>
    <div class="score-grid">
      <div class="metric"><strong>${escapeHtml(node.mastery_score ?? "-")}</strong><span>掌握度</span></div>
      <div class="metric"><strong>${escapeHtml(node.cognitive_mastery_score ?? "-")}</strong><span>认知综合分</span></div>
      <div class="metric"><strong>${escapeHtml(node.confidence ?? "-")}</strong><span>置信度</span></div>
      <div class="metric"><strong>${escapeHtml(node.evidence_count ?? 0)}</strong><span>证据总数</span></div>
      <div class="metric"><strong>${escapeHtml(node.uncertainty ?? "-")}</strong><span>不确定性</span></div>
    </div>

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
    ${node.why_next ? `<p class="muted">推荐理由：${escapeHtml(node.why_next)}</p>` : ""}
    <h3>证据时间线</h3>
    ${renderEvidenceTimeline(node, events)}
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
  $("nodeDetailDrawer").classList.add("open");
  $("nodeDetailDrawer").setAttribute("aria-hidden", "false");
}

function closeNodeDetail() {
  $("nodeDetailDrawer").classList.remove("open");
  $("nodeDetailDrawer").setAttribute("aria-hidden", "true");
}

function renderGraph(graph, type = "job") {
  state.graphs[type] = graph || null;
  if (type === "job") {
    $("jobMermaidOutput").textContent = graph?.mermaid || "";
    renderGraphLegend(graph, "jobGraphDiagram");
    renderGraphDiagram(graph, "jobGraphDiagram");
    renderGraphNodes(graph, "jobGraphList");
    renderDemandSources(graph);
    return;
  }
  if (type === "student") {
    $("studentMermaidOutput").textContent = graph?.mermaid || "";
    renderGraphLegend(graph, "studentGraphDiagram");
    renderGraphDiagram(graph, "studentGraphDiagram");
    renderGraphNodes(graph, "studentGraphList");
    renderStudentEvidence(graph);
    renderGraphUpdateLog(graph?.update_log || []);
    return;
  }
}

function jobAdminRole() {
  return ($("jobAdminRole")?.value || DEFAULT_JOB_ROLE).trim() || DEFAULT_JOB_ROLE;
}

function setJobAdminStatus(message, tone = "muted") {
  const target = $("jobAdminStatus");
  if (!target) return;
  target.className = tone;
  target.textContent = message;
}

function proposalScoreText(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(2) : "-";
}

async function refreshJobGraph(jobRole = "") {
  const query = jobRole ? `?job_role=${encodeURIComponent(jobRole)}` : "";
  const graph = await api(`/api/graph/job${query}`);
  renderGraph(graph, "job");
  return graph;
}

function renderJobAdminSummary(data) {
  const documents = data.documents || [];
  const posts = data.posts || [];
  const proposals = data.proposals || [];
  const versions = data.versions || [];
  const graph = data.graph || {};
  const confirmedCount = (graph.nodes || []).filter((node) => node.confirmed_proposal_id).length;
  $("jobAdminSummary").classList.remove("muted");
  $("jobAdminSummary").innerHTML = `
    <div class="score-grid job-admin-metrics">
      <div class="metric"><strong>${escapeHtml(documents.length)}</strong><span>最近原始资料</span></div>
      <div class="metric"><strong>${escapeHtml(posts.length)}</strong><span>结构化岗位</span></div>
      <div class="metric"><strong>${escapeHtml(proposals.length)}</strong><span>待审核提案</span></div>
      <div class="metric"><strong>${escapeHtml(versions.length)}</strong><span>图谱快照</span></div>
    </div>
    <p class="muted">当前岗位：${escapeHtml(jobAdminRole())}；正式图谱中已有 ${escapeHtml(confirmedCount)} 个节点带确认提案证据。</p>
  `;
}

function renderJobDataRecords(data) {
  const posts = data.posts || [];
  const documents = data.documents || [];
  const postHtml = posts.length ? `
    <ul class="item-list">
      ${posts.slice(0, 6).map((post) => {
        const fields = post.normalized_fields || post.fields || {};
        const title = fields.title || post.title || post.job_role || "岗位记录";
        const company = fields.company || post.company || "";
        const skills = (fields.skills || []).slice(0, 3).join("；");
        return `
          <li>
            <strong>${escapeHtml(title)}</strong>
            <div>${escapeHtml(company || post.source_url || post.job_post_id || "")}</div>
            ${skills ? `<div class="muted">${escapeHtml(skills)}</div>` : ""}
          </li>
        `;
      }).join("")}
    </ul>
  ` : "";
  const docHtml = documents.length ? `
    <ul class="compact-list">
      ${documents.slice(0, 6).map((doc) => `
        <li>
          <strong>${escapeHtml(doc.source_type || "source")}</strong>
          <div>${escapeHtml(doc.source || doc.source_url || doc.document_id || "")}</div>
          <div class="muted">${escapeHtml(doc.collected_at || "")}</div>
        </li>
      `).join("")}
    </ul>
  ` : "";
  $("jobDataRecords").classList.remove("muted");
  $("jobDataRecords").innerHTML = postHtml || docHtml || '<p class="muted">暂无导入数据。</p>';
}

function renderJobProposals(proposals) {
  const target = $("jobProposalList");
  if (!target) return;
  if (!proposals || !proposals.length) {
    target.classList.add("muted");
    target.innerHTML = "暂无待审核提案。";
    return;
  }
  target.classList.remove("muted");
  target.innerHTML = `
    <ul class="item-list job-proposal-list">
      ${proposals.map((proposal) => `
        <li>
          <div class="proposal-head">
            <strong>${escapeHtml(proposal.ability_name || proposal.ability_id || "能力节点")}</strong>
            <span class="node-badge">score ${escapeHtml(proposalScoreText(proposal.proposal_score))}</span>
          </div>
          <div>${escapeHtml(proposal.evidence || "暂无证据摘要")}</div>
          <div class="muted">${escapeHtml(proposal.proposal_id)} · ${escapeHtml(proposal.action || "strengthen")} · ${escapeHtml(proposal.source || "")}</div>
          <div class="question-actions">
            <button type="button" class="primary" data-confirm-proposal="${escapeHtml(proposal.proposal_id)}">确认并生成快照</button>
            <button type="button" data-reject-proposal="${escapeHtml(proposal.proposal_id)}">驳回</button>
          </div>
        </li>
      `).join("")}
    </ul>
  `;
  target.querySelectorAll("[data-confirm-proposal]").forEach((button) => {
    button.addEventListener("click", () => reviewJobProposal(button.dataset.confirmProposal, "confirm"));
  });
  target.querySelectorAll("[data-reject-proposal]").forEach((button) => {
    button.addEventListener("click", () => reviewJobProposal(button.dataset.rejectProposal, "reject"));
  });
}

async function loadJobAdmin() {
  const role = jobAdminRole();
  setJobAdminStatus("正在加载岗位数据...");
  try {
    const query = encodeURIComponent(role);
    const [documents, posts, pending, versions, graph] = await Promise.all([
      api("/api/job-data/documents?limit=12"),
      api(`/api/job-data/posts?job_role=${query}&limit=12`),
      api(`/api/graph/job/proposals/pending?job_role=${query}`),
      api(`/api/graph/job/versions?job_role=${query}`),
      api(`/api/graph/job?job_role=${query}`)
    ]);
    state.jobAdmin = {
      documents: documents.documents || [],
      posts: posts.posts || [],
      proposals: pending.proposals || [],
      versions: versions.versions || [],
      graph
    };
    renderJobAdminSummary(state.jobAdmin);
    renderJobDataRecords(state.jobAdmin);
    renderJobProposals(state.jobAdmin.proposals);
    setJobAdminStatus(`已加载：${state.jobAdmin.posts.length} 条岗位数据，${state.jobAdmin.proposals.length} 条待审核提案。`);
    return state.jobAdmin;
  } catch (error) {
    setJobAdminStatus(`加载失败：${error.message}`);
    $("jobAdminSummary").innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
    $("jobProposalList").innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
    return null;
  }
}

async function ingestJobAdminMaterial() {
  const text = ($("jobAdminText")?.value || "").trim();
  if (!text) {
    setJobAdminStatus("请先粘贴岗位材料。");
    return;
  }
  setJobAdminStatus("正在导入材料并生成待审核提案...");
  try {
    const result = await api("/api/graph/job/ingest", {
      method: "POST",
      body: JSON.stringify({
        job_role: jobAdminRole(),
        text,
        source_type: $("jobAdminSourceType")?.value || "teacher_material",
        source: $("jobAdminSource")?.value || "manual_admin_import",
        use_llm: Boolean($("jobAdminUseLlm")?.checked),
        max_abilities: 8
      })
    });
    setJobAdminStatus(`导入完成：新增 ${result.events_created?.length || 0} 条证据，生成 ${result.proposals_generated?.length || 0} 条提案。`, "status ok");
    await loadJobAdmin();
    await refreshJobGraph(jobAdminRole());
  } catch (error) {
    setJobAdminStatus(`导入失败：${error.message}`);
  }
}

async function collectJobSources() {
  setJobAdminStatus("正在运行授权来源采集...");
  try {
    const result = await api("/api/job-data/collect", {
      method: "POST",
      body: JSON.stringify({
        max_sources: 3,
        store: "sqlite",
        use_llm: Boolean($("jobAdminUseLlm")?.checked),
        max_abilities: 8
      })
    });
    const structured = (result.collected_sources || []).reduce((total, item) => total + Number(item.structured_post_count || 0), 0);
    setJobAdminStatus(`采集完成：${result.collected_count || 0} 个来源，${structured} 条结构化企业岗位，${result.proposal_count || 0} 条提案。`, "status ok");
    await loadJobAdmin();
    await refreshJobGraph(jobAdminRole());
  } catch (error) {
    setJobAdminStatus(`采集失败：${error.message}`);
  }
}

async function reviewJobProposal(proposalId, action = "confirm") {
  if (!proposalId) return;
  setJobAdminStatus(action === "confirm" ? "正在确认提案并生成快照..." : "正在驳回提案...");
  try {
    const result = await api("/api/graph/job/proposals/confirm-sqlite", {
      method: "POST",
      body: JSON.stringify({
        proposal_id: proposalId,
        action,
        confirmed_by: "admin_workspace"
      })
    });
    if (result.proposal?.error) throw new Error(result.proposal.error);
    setJobAdminStatus(action === "confirm" ? "提案已确认，岗位图谱已生成新快照。" : "提案已驳回。", "status ok");
    await loadJobAdmin();
    await refreshJobGraph(jobAdminRole());
  } catch (error) {
    setJobAdminStatus(`审核失败：${error.message}`);
  }
}

async function batchConfirmJobProposals() {
  const role = jobAdminRole();
  if (!state.jobAdmin.proposals?.length) {
    setJobAdminStatus("当前岗位没有待确认提案。");
    return;
  }
  setJobAdminStatus("正在批量确认当前岗位提案...");
  try {
    const result = await api("/api/graph/job/proposals/confirm-sqlite-batch", {
      method: "POST",
      body: JSON.stringify({
        confirm_all: true,
        job_role: role,
        confirmed_by: "admin_workspace_batch"
      })
    });
    setJobAdminStatus(`批量确认完成：${result.confirmed_count || 0} 条提案，生成 ${result.snapshots?.length || 0} 个快照。`, "status ok");
    await loadJobAdmin();
    await refreshJobGraph(role);
  } catch (error) {
    setJobAdminStatus(`批量确认失败：${error.message}`);
  }
}

function renderKnowledge(items) {
  if (!items || !items.length) {
    $("knowledgeRefs").innerHTML = '<p class="muted">暂无</p>';
    return;
  }
  $("knowledgeRefs").innerHTML = items.slice(0, 6).map(item => `
    <div class="kb-card-inline" data-kb-id="${escapeHtml(item.id || "")}" onclick="this.classList.toggle('expanded')">
      <div class="kbci-head">
        <span class="kbci-id">${escapeHtml(item.id || "")}</span>
        <span class="kbci-topic">${escapeHtml(item.topic || item.id || "")}</span>
      </div>
      <div class="kbci-content">${escapeHtml((item.content || "").substring(0, 200))}${(item.content || "").length > 200 ? '...' : ''}</div>
      <div class="kbci-source">${escapeHtml(item.source || "")}</div>
      <div class="kbci-actions">
        <button type="button" data-ask="${escapeHtml('请详细讲解「' + (item.topic || item.id) + '」这个知识点')}" data-knowledge-id="${escapeHtml(item.id || "")}">追问</button>
      </div>
    </div>
  `).join("");
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
}

function workspaceTitle(panel) {
  return {
    dashboard: "学习驾驶舱",
    graph: "能力图谱",
    jobAdmin: "岗位数据导入与提案审核",
    knowledge: "知识缺口",
    tasks: "实训任务",
    scenario: "排故角色扮演",
    quiz: "自测验证",
    plan: "个人培养方案",
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
  if (panel === "jobAdmin") loadJobAdmin();
  if (panel === "plan") loadTrainingPlans("staged");
  if (panel === "scenario") loadScenarios();
  // Reset scroll position when switching panels
  var body = document.querySelector(".workspace-body");
  if (body) body.scrollTop = 0;
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


function applyAssessmentScoresToGraph(scores) {
  if (!scores || !state.graphs || !state.graphs.student) return;
  var mapping = {"electrical_safety":["electrical_safety_check","at_01","pc_05","cm_06","power_isolation_confirmation","mw_06","mw_07","mw_09"],"emergency_stop":["ir_13","electrical_safety_check","at_01","at_19","at_20","ad_12","ir_11","ir_12"],"hmi_basic":["mw_01","ir_04","pc_07","sn_11","sd_01","sd_02","cm_01","cm_20"],"input_common_terminal":["plc_input_common_terminal","at_11","no_response_common_terminal_check","at_30","sensor_led_observation","plc_input_grouping","input_led_compare","at_08"],"motor_control":["sd_01","sd_02","mw_01","ad_10","ir_04","pc_07","pc_16","pc_18"],"plc_basic_principle":["mw_07","ir_01"],"plc_wiring":["sensor_wiring_color_code","sensor_wiring_judgement","mw_08","at_09","at_10","at_20","ad_04","ad_12"],"safety_ppe":["electrical_safety_check","at_01","ir_11","ir_12","ir_14","ir_15","pc_05","cm_06"],"sensor_selection":["sensor_type_identification","at_05","ad_01","sn_01","sensor_nameplate_reading","sensor_output_logic","sensor_led_observation","sensor_wiring_color_code"],"sensor_wiring":["sensor_wiring_color_code","sensor_wiring_judgement","at_09","at_10","ad_04","sn_03","sn_04","sensor_led_observation"],"troubleshoot_order":["mw_17","at_22","ir_17","input_no_response_fault_scope","no_response_power_path_check","no_response_sensor_side_check","no_response_common_terminal_check","no_response_address_mapping_check"],"vfd_basic":["mw_01","ir_04","pc_07","sn_11","sd_01","sd_02","cm_01","cm_20"]};
  var nodes = state.graphs.student.nodes || [];
  
  var nodeMap = {};
  nodes.forEach(function(n) { nodeMap[n.id] = n; });
  
  var updated = 0;
  Object.keys(scores).forEach(function(aid) {
    var ids = mapping[aid];
    if (!ids) return;
    var score = parseFloat(scores[aid].toFixed(2));
    ids.forEach(function(tid) {
      var node = nodeMap[tid];
      if (node) { node.mastery_score = score; updated++; }
    });
  });
  
  if (updated > 0 && state.graphRenderers && state.graphRenderers["studentGraphDiagram"]) {
    state.graphRenderers["studentGraphDiagram"].update(state.graphs.student);
  }
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
  setWorkspacePanel(panel || "graph");
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

// ---- Training Plans (from static JSON) ----
async function fetchTrainingPlans(jobName) {
  if (!jobName) jobName = state.jobName || '';
  try {
    var r = await fetch('/training-plans.json');
    var allPlans = await r.json();
    return allPlans[jobName] || {};
  } catch (e) { console.error('fetchTrainingPlans', e); return {}; }
}

function renderTrainingPlanStages(planData) {
  if (!planData||!planData.stages||!planData.stages.length) return '<div class="muted">暂无培养方案数据</div>';
  var h = '<div class="stage-timeline"><div class="stage-timeline-track">';
  planData.stages.forEach(function(st,idx){
    var c = stageColor(idx);
    h += '<div class="stage-timeline-step">';
    h += '<div class="st-step-marker" style="background:'+c+'">'+(idx+1)+'</div>';
    h += '<div class="st-step-bar"></div>';
    h += '<div class="st-step-label">';
    h += '<span class="st-step-name">'+escapeHtml((st.name.split('：')[1]||st.name))+'</span>';
    h += '</div></div>';
  });h+='</div></div>';
  h += '<div class="plan-content">';
  planData.stages.forEach(function(st,idx){
    var c=stageColor(idx);
    var done=(state.completedStages||[]).indexOf(st.name)>=0;
    h += '<div class="plan-stage-card'+(done?' completed':'')+'" style="border-left:4px solid '+c+'" stage="'+idx+'">';
    h += '<div class="node-head"><h4>'+escapeHtml(st.name)+'</h4></div>';
    h += '<p>'+escapeHtml(st.goal)+'</p>';
    if(st.knowledge&&st.knowledge.length)
      h += '<div class="muted">知识点：'+escapeHtml(st.knowledge.join('、'))+'</div>';
    h += '<div class="muted">课程：'+escapeHtml(st.courses||'')+'</div>';
    h += '<div class="stage-task">实训：'+escapeHtml(st.tasks||'')+'</div>';
    h += '<div class="stage-actions">';
    h += '<button class="mark-complete-btn" data-stage="'+escapeHtml(st.name)+'">';
    h += (done?'✓ 已完成':'标记完成')+'</button>';
    h += '<button class="stage-priority-up" data-stage="'+escapeHtml(st.name)+'">↑</button>';
    h += '<button class="stage-priority-down" data-stage="'+escapeHtml(st.name)+'">↓</button>';
    h += '</div></div>';
  });h+='</div>';return h;
}

function renderTrainingPlanToday(planData) {
    if (!planData || !planData.seven_day || !planData.seven_day.length) return '<div class=\"muted\">暂无今日训练任务</div>';
    var todayTask = planData.seven_day[0];
   var parts = todayTask.split('|');
   var steps = [];
    var stepBase = (state.jobName || 'default').replace(/\s+/g, '_');
    parts.forEach(function(p, i) { steps.push({id: stepBase + '-step-' + i, title: p.trim()}); });
   var doneSteps = state.completedSteps || [];
    var done = doneSteps.length ? steps.filter(function(s){return doneSteps.indexOf(s.id)>=0}).length : 0;
    var html = '<div class=\"checklist-progress\">进度：' + done + '/' + steps.length + ' 步已完成</div>';
    html += '<div class=\"checklist\">';
    steps.forEach(function(step) {
      var checked = doneSteps.indexOf(step.id) >= 0;
      html += '<label class=\"checklist-item'+(checked?' done':'')+'\">';
      html += '<input type=\"checkbox\" class=\"checklist-cb\" data-step-id=\"'+step.id+'\"'+(checked?' checked':'')+'>';
      html += '<span>'+escapeHtml(step.title)+'</span>';
      html += '</label>';
    });
    html += '</div>';
    html += '<div style=\"margin-top:14px\"><h4 style=\"color:#94a3b8;margin:0 0 8px\">全部阶段实训任务</h4>';
    if (planData.stages) {
      planData.stages.forEach(function(stage, idx) {
        var sn = (stage.name.split('：')[1] || stage.name);
        html += '<div style=\"font-size:0.78rem;color:#cbd5e1;margin-bottom:6px;padding:8px 10px;background:rgba(255,255,255,0.03);border-radius:6px\">';
        html += '<strong style=\"color:#38bdf8\">'+(idx+1)+'. '+escapeHtml(sn)+'：</strong>'+escapeHtml(stage.tasks||'')+'</div>';
      });
    }
    html += '</div>';
    return html;
  }

function renderTrainingPlan7Day(planData) {
  if (!planData||!planData.seven_day||!planData.seven_day.length) return '<div class="muted">暂无7天训练计划</div>';
  var cols = ['#38bdf8','#818cf8','#34d399','#fbbf24','#f472b6','#fb923c','#a78bfa'];
  var h = '<div class="gantt-chart">';
  planData.seven_day.forEach(function(day,idx){
    var parts = day.split('|');
    var title = (parts[0]||'').trim();
    var core = (parts[1]||'').trim();
    var task = (parts[2]||'').trim();
    var c = cols[idx % cols.length];
    h += '<div class="gantt-row">';
    h += '<div class="gantt-head">';
    h += '<span class="gantt-day-num" style="background:'+c+'">'+(idx+1)+'</span>';
    h += '<span class="gantt-day-title">'+escapeHtml(title)+'</span>';
    h += '</div>';
    h += '<div class="gantt-body">';
    h += '<div class="gantt-bar" style="background:'+c+'">';
    h += '<span class="gantt-bar-text">'+escapeHtml(core||task||'')+'</span>';
    h += '</div>';
    h += '<div class="gantt-meta muted">'+escapeHtml(task||'')+'</div>';
    h += '</div></div>';
  });h+='</div>';return h;
}

function renderWorkspaceTasks(planData) {
  var el = document.getElementById('taskRefs');
  if (!el) return;
  if (!planData || !planData.stages) { el.innerHTML = '<div class="muted">暂无实训任务</div>'; return; }
  var html = '';
  planData.stages.forEach(function(stage, idx) {
    html += '<div style="padding:8px 10px;margin-bottom:6px;background:rgba(255,255,255,0.03);border-radius:6px;font-size:0.78rem;color:#cbd5e1;line-height:1.5">';
    html += '<strong style="color:#38bdf8">' + (idx+1) + '. ' + escapeHtml((stage.name.split('：')[1] || stage.name)) + '：</strong>' + escapeHtml(stage.tasks || '');
    html += '</div>';
  });
  el.innerHTML = html;
}

async function loadTrainingPlans(planMode) {
  var pp = document.getElementById('personalizedPlan');
  if (pp) pp.style.display = '';
  var jobName = state.jobName || '';
  if (!jobName) { document.getElementById('personalizedPlan').innerHTML = '<div class="muted">请先选择岗位</div>'; return; }
  document.getElementById('personalizedPlan').innerHTML = '<div class="muted">加载中...</div>';
 var planData = await fetchTrainingPlans(jobName);
  // Load saved stage order
  if (planData && planData.stages) {
    var savedKey = 'stages_order_' + (state.jobName || 'default').replace(/\s+/g, '_');
    var savedOrder = localStorage.getItem(savedKey);
    if (savedOrder) {
      try { var parsed = JSON.parse(savedOrder); if (parsed.length === planData.stages.length) planData.stages = parsed; } catch(e) {}
    }
  }
 if (planMode === 'staged') {
    document.getElementById('personalizedPlan').innerHTML = renderTrainingPlanStages(planData);
    addStageReorderHandlers(planData);
  } else if (planMode === 'today') {
    document.getElementById('personalizedPlan').innerHTML = renderTrainingPlanToday(planData);
    renderWorkspaceTasks(planData);
  } else if (planMode === '7_day') {
    document.getElementById('personalizedPlan').innerHTML = renderTrainingPlan7Day(planData);
    renderWorkspaceTasks(planData);
  }
  renderWorkspaceTasks(planData);
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

async function applyChatResult(data) {
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
  if (data.student_graph) renderGraph(data.student_graph, "student");
  await loadGraphUpdates();
  state.knowledgeGaps = data.knowledge_refs || [];
  renderKnowledge(data.knowledge_refs || []);
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
        job_role: state.jobProfile?.id,
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
    if (data.student_graph) renderGraph(data.student_graph, "student");
    await loadGraphUpdates();
    await loadStudentDashboard();
    renderKnowledge((state.knowledgeGaps && state.knowledgeGaps.length) ? state.knowledgeGaps : (data.knowledge_refs || []));
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
}


function assessmentSkipKey() {
  return [
    "mcp_assessment_skipped",
    state.sessionId || "",
    selectedJobRole() || ""
  ].join(":");
}

function assessmentCompletedKey() {
  return "mcp_assessment_completed_" + state.sessionId;
}
// ---- Unified app boot ----

var appBootStarted = false;
var appBootPromise = null;

function bootOnce() {
  if (appBootStarted) return appBootPromise;
  appBootStarted = true;
  try {
    appBootPromise = typeof boot === "function"
      ? Promise.resolve(boot())
      : Promise.resolve();
  } catch (error) {
    appBootStarted = false;
    appBootPromise = null;
    throw error;
  }
  return appBootPromise;
}

// ---- Assessment Functions ----

var assessmentState = {
  currentQid: "",
  currentQuestion: null,
  currentIndex: 0,
  answeredCount: 0,
  totalQuestions: 0,
  selectedOption: null,
  jobRole: "",
  abilityLabels: {},
  started: false,
  starting: false,
  submitting: false
};

function selectedJobRole() {
  return assessmentState.jobRole
    || state.selectedJobId
    || localStorage.getItem("mcp_job_id")
    || "";
}

// ---- Overlay helpers ----

function showAssessmentOverlay() {
  var overlay = document.getElementById("assessmentOverlay");
  overlay.style.display = "flex";
  overlay.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function hideAssessmentOverlay() {
  var overlay = document.getElementById("assessmentOverlay");
  overlay.style.display = "none";
  overlay.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

// ---- Error & retry ----

var assessmentRetryAction = null;

function setAssessmentError(message, retryAction) {
  var statusEl = document.getElementById("assessmentStatus");
  var retryBtn = document.getElementById("assessmentRetryBtn");
  statusEl.textContent = message;
  statusEl.style.display = "block";
  assessmentRetryAction = typeof retryAction === "function" ? retryAction : null;
  retryBtn.hidden = !assessmentRetryAction;
}

function clearAssessmentError() {
  var statusEl = document.getElementById("assessmentStatus");
  statusEl.textContent = "";
  statusEl.style.display = "none";
  var retryBtn = document.getElementById("assessmentRetryBtn");
  retryBtn.hidden = true;
  assessmentRetryAction = null;
}

// ---- Assessment flow ----

async function startAssessment(jobRole) {
  if (assessmentState.starting) return;

  // Skip if already completed or skipped
  try {
    if (localStorage.getItem(assessmentCompletedKey()) === "1") {
      await bootOnce();
      return;
    }
    if (sessionStorage.getItem(assessmentSkipKey()) === "1") {
      await bootOnce();
      return;
    }
  } catch (_) { /* storage unavailable */ }

  assessmentState.starting = true;
  showAssessmentOverlay();
  var container = document.getElementById("assessmentOverlay").querySelector(".assessment-container");
  var result = document.getElementById("assessmentResult");
  container.style.display = "block";
  result.style.display = "none";
  clearAssessmentError();

  var role = jobRole || state.selectedJobId || localStorage.getItem("mcp_job_id") || "";
  try {
    var resp = await api("/api/student/assess/start", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        job_role: role
      })
    });

    // Completed assessment: server sends status=completed, not an error
    if (resp.status === "completed" || resp.state === "completed") {
      assessmentState.starting = false;
      hideAssessmentOverlay();
      await bootOnce();
      return;
    }

    if (resp.error) {
      assessmentState.starting = false;
      setAssessmentError(resp.error || "启动测评失败", function() {
        startAssessment(selectedJobRole());
      });
      return;
    }

    assessmentState.jobRole = role;
    assessmentState.currentQid = "";
    assessmentState.currentIndex = 0;
    assessmentState.answeredCount = 0;
    assessmentState.started = true;
    assessmentState.selectedOption = null;
    assessmentState.starting = false;
    renderAssessmentQuestion(resp);
  } catch (e) {
    console.error("Assessment startup failed:", e);
    setAssessmentError("网络错误，启动测评失败，请点击重试", function() {
      assessmentState.starting = false;
      startAssessment(selectedJobRole());
    });
  }
}

function renderAssessmentQuestion(resp) {
  var q = resp.first_question || resp.next_question;
  if (!q || !q.qid) {
    setAssessmentError("测评数据异常，请重试", function() {
      assessmentState.starting = false;
      startAssessment(selectedJobRole());
    });
    return;
  }

  assessmentState.currentQid = q.qid;
  assessmentState.currentQuestion = q;

  // Save ability label for result display
  if (q.ability_id) {
    assessmentState.abilityLabels[q.ability_id] =
      q.ability_label || q.dimension || q.ability_id;
  }

  var total = resp.total_questions || 30;
  assessmentState.totalQuestions = total;
  var idx = resp.current_index !== undefined ? resp.current_index : assessmentState.currentIndex;
  assessmentState.currentIndex = idx;
  assessmentState.answeredCount = resp.answered_count !== undefined ? resp.answered_count : idx;

  var progressPct = total > 0 ? (idx / total * 100) : 0;
  document.getElementById("assessmentProgress").querySelector(".progress-fill").style.width = progressPct + "%";
  document.getElementById("assessmentProgress").querySelector(".progress-text").textContent = idx + " / " + total;

  var card = document.getElementById("assessmentQuestionCard");
  card.querySelector(".question-dimension").textContent = q.dimension || "";
  card.querySelector(".question-text").textContent = q.text || "";

  var optsDiv = card.querySelector(".question-options");
  optsDiv.innerHTML = "";
  assessmentState.selectedOption = null;

  if (q.options) {
    q.options.forEach(function(opt) {
      var btn = document.createElement("button");
      btn.className = "option-btn";
      btn.textContent = opt.key + ". " + opt.text;
      btn.type = "button";
      btn.addEventListener("click", function() {
        var allBtns = optsDiv.querySelectorAll(".option-btn");
        allBtns.forEach(function(b) { b.classList.remove("selected"); });
        btn.classList.add("selected");
        assessmentState.selectedOption = opt.key;
        document.getElementById("assessmentNextBtn").disabled = false;
      });
      optsDiv.appendChild(btn);
    });
  }

  document.getElementById("assessmentNextBtn").disabled = true;
  document.getElementById("assessmentNextBtn").onclick = submitAssessmentAnswer;
  document.getElementById("assessmentSkipBtn").onclick = skipAssessment;
}

async function submitAssessmentAnswer() {
  if (!assessmentState.selectedOption) return;
  if (assessmentState.submitting) return;
  assessmentState.submitting = true;
  clearAssessmentError();

  // Disable UI during submission
  var nextBtn = document.getElementById("assessmentNextBtn");
  var skipBtn = document.getElementById("assessmentSkipBtn");
  var optionsDiv = document.getElementById("assessmentQuestionCard").querySelector(".question-options");
  nextBtn.textContent = "提交中...";
    nextBtn.disabled = true;
  skipBtn.disabled = true;
  optionsDiv.style.pointerEvents = "none";
  optionsDiv.style.opacity = "0.6";

  var qid = assessmentState.currentQid;
  if (!qid) {
    setAssessmentError("题目数据异常，请重试", function() { submitAssessmentAnswer(); });
    assessmentState.submitting = false;
    nextBtn.textContent = "确认并继续";
    nextBtn.disabled = !assessmentState.selectedOption;
    skipBtn.disabled = false;
    optionsDiv.style.pointerEvents = "";
    optionsDiv.style.opacity = "";
    return;
  }

  try {
    var resp = await api("/api/student/assess/answer", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        qid: qid,
        selected_key: assessmentState.selectedOption,
        job_role: assessmentState.jobRole
      })
    });

    if (resp.status === "completed") {
      showAssessmentResult(resp.result);
      return;
    }

    if (resp.error) {
      setAssessmentError(resp.error || "提交失败，请重试", function() { submitAssessmentAnswer(); });
      return;
    }

    if (resp.next_question) {
      renderAssessmentQuestion(resp);
    } else {
      setAssessmentError("服务端返回异常，请重试", function() { submitAssessmentAnswer(); });
    }
  } catch (e) {
    console.error("Assessment answer error:", e);
    setAssessmentError("网络错误，提交失败，请点击重试", function() { submitAssessmentAnswer(); });
  } finally {
    assessmentState.submitting = false;
    nextBtn.textContent = "确认并继续";
    nextBtn.disabled = !assessmentState.selectedOption;
    skipBtn.disabled = false;
    optionsDiv.style.pointerEvents = "";
    optionsDiv.style.opacity = "";
  }
}

function showAssessmentResult(result) {
  if (!result) {
    setAssessmentError("测评结果为空", function() {
      startAssessment(selectedJobRole());
    });
    return;
  }
  document.getElementById("assessmentOverlay").querySelector(".assessment-container").style.display = "none";
  document.getElementById("assessmentStatus").style.display = "none";
  document.getElementById("assessmentRetryBtn").hidden = true;
  var resultDiv = document.getElementById("assessmentResult");
  resultDiv.style.display = "block";

  document.getElementById("resultScore").textContent = Math.round((result.total_score || 0) * 100) + "%";

  var dimsDiv = document.getElementById("resultDimensions");
  dimsDiv.innerHTML = "";
  var scores = result.ability_scores || {};
  var labelMap = assessmentState.abilityLabels || {};
  Object.keys(scores).forEach(function(aid) {
    var s = scores[aid];
    var cssClass = s >= 0.8 ? "strong" : (s >= 0.5 ? "medium" : "weak");
    var row = document.createElement("div");
    row.className = "dimension-row";
    var label = escapeHtml(labelMap[aid] || aid);
    row.innerHTML = '<span class="dimension-label">' + label + '</span>' +
      '<div class="dimension-bar-wrap"><div class="dimension-bar-fill ' + cssClass + '" style="width:' + (s * 100) + '%"></div></div>' +
      '<span class="dimension-score">' + Math.round(s * 100) + '%</span>';
    dimsDiv.appendChild(row);
  });

  var recDiv = document.getElementById("resultRecommendations");
  recDiv.innerHTML = result.recommendations && result.recommendations.length > 0 ?
    '<h4>学习建议</h4><ul>' + result.recommendations.map(function(r) { return '<li>' + escapeHtml(r) + '</li>'; }).join("") + '</ul>' : "";

  var stepDiv = document.getElementById("resultNextSteps");
  stepDiv.innerHTML = result.next_steps && result.next_steps.length > 0 ?
    '<h4>下一步</h4>' + result.next_steps.map(function(s) { return '<div class="next-step">' + escapeHtml(s) + '</div>'; }).join("") : "";

  try { localStorage.setItem(assessmentCompletedKey(), "1"); } catch (_) {}

  // Collect labels to search: wrong-answer labels + weak ability labels
  var searchLabels = [];
  var answers = result.answers || [];
  if (answers.length > 0) {
    var wrongAnswers = answers.filter(function(a) { return a.correct === false; });
    wrongAnswers.forEach(function(a) {
      var label = a.ability_label || "";
      if (label && searchLabels.indexOf(label) === -1) searchLabels.push(label);
    });
  }
  // Fallback: use weak_abilities with their labels from ability_scores
  var weakIds = result.weak_abilities || [];
  var abilityLabels = assessmentState.abilityLabels || {};
  weakIds.forEach(function(aid) {
    var label = abilityLabels[aid] || aid;
    if (label && searchLabels.indexOf(label) === -1 && searchLabels.length < 8) {
      searchLabels.push(label);
    }
  });

  var allCards = [];
  var promises = [];
  if (searchLabels.length === 0) {
    // No search labels: render empty state immediately
    var gapEl2 = document.getElementById("knowledgeGapCards");
    var refsEl2 = document.getElementById("knowledgeRefs");
    if (gapEl2) gapEl2.innerHTML = '<p class="muted">测评已完成，未检测到薄弱知识点。</p>';
    if (refsEl2) refsEl2.innerHTML = '<p class="muted">测评已完成，未检测到薄弱知识点。</p>';
    if (typeof refreshStudentGraph === "function") refreshStudentGraph();
  } else {
    promises = searchLabels.map(function(label) {
      return api("/api/knowledge/search?query=" + encodeURIComponent(label))
        .then(function(res) {
          if (res.results && res.results.length > 0) {
            res.results.forEach(function(item) { allCards.push(item); });
          }
        }).catch(function() {});
    });

    var doneBtn = document.getElementById("assessmentDoneBtn");
    var originalBtnText = doneBtn.textContent;
    doneBtn.textContent = "正在生成知识缺口...";
    doneBtn.disabled = true;

    Promise.all(promises).then(function() {
      var seen = {};
      var unique = allCards.filter(function(c) { if (seen[c.id]) return false; seen[c.id] = true; return true; });
      var gapEl = document.getElementById("knowledgeGapCards");
      var refsEl = document.getElementById("knowledgeRefs");
      if (unique.length > 0) {
        var h = renderKnowledgeCards(unique);
        if (gapEl) { gapEl.innerHTML = h; gapEl.classList.remove("muted"); }
        if (refsEl) { refsEl.innerHTML = h; refsEl.classList.remove("muted"); }
      }
      if (typeof refreshStudentGraph === "function") refreshStudentGraph();
      doneBtn.textContent = originalBtnText;
      doneBtn.disabled = false;
    });
  }

  // Store assessment scores for graph update
  state.assessmentScores = result.ability_scores || {};

  document.getElementById("assessmentDoneBtn").onclick = function() {
    hideAssessmentOverlay();
    bootOnce().then(function() {
      // Apply assessment scores to student graph after boot
      setTimeout(function() {
        if (typeof applyAssessmentScoresToGraph === "function" && state.assessmentScores) {
          applyAssessmentScoresToGraph(state.assessmentScores);
        }
        if (typeof openWorkspace === "function") {
          openWorkspace("knowledge");
        }
      }, 1200);
    });
  };
}

function skipAssessment() {
  if (!confirm("确定暂时跳过测评吗？跳过后将无法获得个性化学习路径。")) return;
  try { sessionStorage.setItem(assessmentSkipKey(), "1"); } catch (_) {}
  hideAssessmentOverlay();
  bootOnce();
}

function finishAssessmentAndBoot() {
  hideAssessmentOverlay();
  bootOnce();
}

// Unified retry button binding (set once at init time)
document.addEventListener("DOMContentLoaded", function() {
  var retryBtn = document.getElementById("assessmentRetryBtn");
  if (retryBtn) {
    retryBtn.onclick = function() {
      var action = assessmentRetryAction;
      clearAssessmentError();
      if (action) action();
    };
  }
});

// ---- End Assessment ----
async function boot() {
  try {
    const health = await api("/api/health");
    $("healthStatus").textContent = health.status === "ok" ? "已连接" : "异常";
    $("healthStatus").classList.add("ok");
    const jobId = localStorage.getItem("mcp_job_id") || "automation_line_commissioning_maintenance_newcomer";
    const [start, quiz, jobGraph, studentBootstrap] = await Promise.all([
      api("/api/chat/start", { method: "POST", body: JSON.stringify({ session_id: state.sessionId, job_role: jobId }) }),
      api(`/api/quiz?job_role=${encodeURIComponent(jobId)}`),
      api(`/api/graph/job?job_role=${encodeURIComponent(jobId)}`),
      api(`/api/student/bootstrap?session_id=${encodeURIComponent(state.sessionId)}`),
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
    renderGraph(jobGraph, "job");
    renderJobProposals(jobGraph.pending_proposals || []);
    renderGraph(studentBootstrap.student_graph, "student");
    renderGraphUpdateLog(studentBootstrap.student_graph?.update_log || []);
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
$("loadPersonalizedPlan").addEventListener("click", () => loadTrainingPlans("staged"));
$("loadTodayPlan").addEventListener("click", () => loadTrainingPlans("today"));
$("loadSevenDayPlan").addEventListener("click", () => loadTrainingPlans("7_day"));
$("refreshJobAdmin")?.addEventListener("click", loadJobAdmin);
$("ingestJobMaterial")?.addEventListener("click", ingestJobAdminMaterial);
$("collectJobSources")?.addEventListener("click", collectJobSources);
$("batchConfirmProposals")?.addEventListener("click", batchConfirmJobProposals);
$("startScenario").addEventListener("click", startScenario);
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


document.querySelectorAll(".tb-btn").forEach(function(b){b.addEventListener("click",function(){document.querySelectorAll(".tb-btn").forEach(function(x){x.classList.remove("active")});this.classList.add("active");state.timeBudget=parseInt(this.dataset.budget);localStorage.setItem("time_budget",state.timeBudget)})});
if (document.getElementById("learningGoalSelect")) {
  document.getElementById("learningGoalSelect").value = localStorage.getItem("learning_goal") || "日常实事";
  document.getElementById("learningGoalSelect").addEventListener("change", function() {
    state.learningGoal = this.value;
    localStorage.setItem("learning_goal", this.value);
  });
}



document.getElementById("personalizedPlan").addEventListener("click", function(e) {
  var btn = e.target.closest("button");
  if (!btn) return;
  var st = btn.dataset.stage;
  if (btn.classList.contains("mark-complete-btn") && st) {
    e.preventDefault();
    var arr = state.completedStages || [];
    var idx = arr.indexOf(st);
    if (idx > -1) { arr.splice(idx, 1); }
    else { arr.push(st); }
    state.completedStages = arr;
    localStorage.setItem("completed_stages", JSON.stringify(arr));
    loadTrainingPlans("staged");
  }
});

document.getElementById("personalizedPlan").addEventListener("change", function(e) {
  if (e.target && e.target.classList.contains("checklist-cb")) {
    var sid = e.target.dataset.stepId;
    if (!sid) return;
    var idx = state.completedSteps.indexOf(sid);
    if (e.target.checked) {
      if (idx === -1) state.completedSteps.push(sid);
    } else {
      if (idx > -1) state.completedSteps.splice(idx, 1);
    }
    localStorage.setItem("completed_steps", JSON.stringify(state.completedSteps));
    updateChecklistProgress();
    var lbl = e.target.closest(".checklist-item");
    if (lbl) lbl.classList.toggle("done", e.target.checked);
  }
});
function addStageReorderHandlers(planData) {
  document.querySelectorAll('.stage-priority-up').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var name = this.dataset.stage;
      var stages = planData.stages;
      var idx = stages.findIndex(function(s) { return s.name === name; });
      if (idx < 1) return;
      var tmp = stages[idx - 1]; stages[idx - 1] = stages[idx]; stages[idx] = tmp;
      stages.forEach(function(s, i) { var p = s.name.split(/[：:]/); s.name = '第' + (i+1) + '阶段：' + (p.length > 1 ? p.slice(1).join('：') : s.name); });
     document.getElementById('personalizedPlan').innerHTML = renderTrainingPlanStages(planData);
     addStageReorderHandlers(planData);
      localStorage.setItem('stages_order_' + (state.jobName || 'default').replace(/\\s+/g, '_'), JSON.stringify(stages));
   });
 });
 document.querySelectorAll('.stage-priority-down').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var name = this.dataset.stage;
      var stages = planData.stages;
      var idx = stages.findIndex(function(s) { return s.name === name; });
      if (idx >= stages.length - 1) return;
      var tmp = stages[idx + 1]; stages[idx + 1] = stages[idx]; stages[idx] = tmp;
      stages.forEach(function(s, i) { var p = s.name.split(/[：:]/); s.name = '第' + (i+1) + '阶段：' + (p.length > 1 ? p.slice(1).join('：') : s.name); });
     document.getElementById('personalizedPlan').innerHTML = renderTrainingPlanStages(planData);
     addStageReorderHandlers(planData);
      localStorage.setItem('stages_order_' + (state.jobName || 'default').replace(/\\s+/g, '_'), JSON.stringify(stages));
   });
 });
}

function updateChecklistProgress(){var el=document.getElementById("personalizedPlan");if(!el)return;var boxes=el.querySelectorAll(".checklist-cb:checked");var total=el.querySelectorAll(".checklist-cb").length;var done=boxes.length;var prog=el.querySelector(".checklist-progress");if(prog)prog.textContent="进度："+done+"/"+total+" 步已完成"}


function renderRadarChart(stages,id){var c=document.getElementById(id);if(!c||!stages||stages.length<3)return;c.innerHTML="";var w=c.clientWidth||280;var h=190;var cx=w/2,cy=h/2-10;var r=Math.min(cx-40,cy-25);if(r<30)return;var data=stages.slice(0,6).map(function(s,i){return{a:s.name||"",v:0.5}});var angleStep=Math.PI*2/data.length;var svg='<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" xmlns="http://www.w3.org/2000/svg"><g transform="translate('+cx+','+cy+')">';[0.2,0.4,0.6,0.8,1].forEach(function(lv){var pts=[];for(var i=0;i<=data.length;i++){var a=angleStep*(i%data.length)-Math.PI/2;pts.push((r*lv*Math.cos(a)).toFixed(1)+","+(r*lv*Math.sin(a)).toFixed(1))}svg+='<polygon points="'+pts.join(" ")+'" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="0.8"/>'});data.forEach(function(d,i){var a=angleStep*i-Math.PI/2;var x2=(r*Math.cos(a)).toFixed(1);var y2=(r*Math.sin(a)).toFixed(1);svg+='<line x1="0" y1="0" x2="'+x2+'" y2="'+y2+'" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>';var lx=((r+22)*Math.cos(a)).toFixed(1);var ly=((r+22)*Math.sin(a)).toFixed(1);svg+='<text x="'+lx+'" y="'+ly+'" text-anchor="middle" dominant-baseline="middle" fill="#94a3b8" font-size="9">'+d.a.slice(0,5)+".."+'</text>'});var pts2=[];for(var j=0;j<data.length;j++){var a2=angleStep*j-Math.PI/2;var r2=r*data[j].v;pts2.push(r2*Math.cos(a2)+","+r2*Math.sin(a2))}pts2.push(pts2[0]);svg+='<polygon points="'+pts2.join(" ")+'" fill="rgba(56,189,248,0.15)" stroke="#38bdf8" stroke-width="1.5" stroke-linejoin="round"/>';svg+='</g></svg>';c.innerHTML=svg}

function stageColor(idx){var c=["#38bdf8","#818cf8","#34d399","#fbbf24","#f472b6","#fb923c","#a78bfa"];return c[idx%c.length]}

// boot() called after job selection via selectJob()

// ── Landing / Identity & Job Selection ──
function selectIdentity(identity) {
  localStorage.setItem("mcp_identity", identity);
  document.getElementById("landingStepIdentity").classList.remove("active");
  document.getElementById("landingStepJob").classList.add("active");
}

function backToIdentity() {
  document.getElementById("landingStepJob").classList.remove("active");
  document.getElementById("landingStepIdentity").classList.add("active");
}

function selectJob(jobId, event) {
  var identity = localStorage.getItem("mcp_identity") || "";
  localStorage.setItem("mcp_job_id", jobId);
  if (event && event.currentTarget) {
    var jobName = event.currentTarget.getAttribute("data-job-name");
    if (jobName) state.jobName = jobName;
  }

  // Admin bypass: no assessment, boot app directly
  if (identity !== "student") {
    state.selectedJobId = jobId;
    state.sessionId = "admin-" + Date.now();
    state.messages = [];
    state.jobProfile = { id: jobId, role_name: state.jobName || jobId };
    const overlay = document.getElementById("landingOverlay");
    overlay.classList.add("fade-out");
    setTimeout(function() {
      overlay.style.display = "none";
      document.body.style.overflow = "";
      bootOnce();
    }, 400);
    return;
  }

  // Student: use assessment flow
  state.selectedJobId = jobId;
  state.sessionId = "demo-" + Date.now();
  localStorage.setItem("mcp_session_id", state.sessionId);
  state.messages = [];
  state.jobProfile = { id: jobId, role_name: state.jobName || jobId };
  dismissLanding().then(function() {
    startAssessment(jobId);
  });
}

function dismissLanding() {
  return new Promise(function(resolve) {
    var overlay = document.getElementById("landingOverlay");
    overlay.classList.add("fade-out");
    setTimeout(function() {
      overlay.style.display = "none";
      document.body.style.overflow = "";
      resolve();
    }, 400);
  });
}

function toggleDrawer() {
  document.querySelector(".chat-layout").classList.toggle("drawer-collapsed");
}
