// === teacher-ui.js - Teacher Decision Workspace (TF-6C Runtime Closure) ===
var TeacherUI = {
  currentTab: "today",
  currentIssueId: null,
  messages: [],
  aiContext: {
    class_id: null,
    job_role: "",
    current_tab: "today",
    current_issue_id: null,
    current_issue_title: "",
    current_student_ids: [],
    current_student_id: null,
    current_ability_id: null,
    current_candidate_id: null,
    current_intervention_id: null,
    current_intervention_draft: null
  },
  _navInitialized: false,
  _issuesCache: null,
  currentClassId: null,
  currentClass: null,
  _classes: [],
  _selectedStudents: [],
  _batchParsedStudents: [],
  _allStudents: [],
  workspacePanelForTab: {
    today: "teacherToday",
    insights: "classInsights",
    students: "studentMgmt",
    feedback: "teacherComments"
  }
};

// ---- Safe HTML escape ----
TeacherUI.escHtml = function(text) {
  var d = document.createElement("div");
  d.textContent = text || "";
  return d.innerHTML;
};

TeacherUI.updateAIContext = function(patch) {
  if (!patch) return TeacherUI.aiContext;
  Object.keys(patch).forEach(function(key) {
    if (key === "current_student_ids") {
      TeacherUI.aiContext.current_student_ids = Array.isArray(patch[key]) ? patch[key].slice() : [];
    } else {
      TeacherUI.aiContext[key] = patch[key];
    }
  });
  TeacherUI.syncAIContext();
  return TeacherUI.aiContext;
};

TeacherUI.syncAIContext = function() {
  TeacherUI.aiContext.class_id = TeacherUI.currentClassId || null;
  TeacherUI.aiContext.job_role = TeacherUI.currentClass ? (TeacherUI.currentClass.job_role || "") : "";
  TeacherUI.aiContext.current_tab = TeacherUI.currentTab || "today";
  if (window.state) {
    window.state.teacherContext = window.state.teacherContext || {};
    Object.keys(TeacherUI.aiContext).forEach(function(key) {
      window.state.teacherContext[key] = TeacherUI.aiContext[key];
    });
  }
  return TeacherUI.aiContext;
};

TeacherUI.applyContextUpdate = function(update) {
  if (!update) return TeacherUI.aiContext;
  var aliases = {
    last_issue_id: "current_issue_id",
    last_students: "current_student_ids",
    last_student_id: "current_student_id",
    last_candidate_id: "current_candidate_id",
    last_intervention_id: "current_intervention_id",
    current_candidate_id: "current_candidate_id",
    current_intervention_id: "current_intervention_id",
    current_intervention_draft: "current_intervention_draft"
  };
  Object.keys(update).forEach(function(key) {
    var target = aliases[key] || key;
    if (target === "current_student_ids") {
      TeacherUI.aiContext.current_student_ids = Array.isArray(update[key]) ? update[key].slice() : [];
    } else {
      TeacherUI.aiContext[target] = update[key];
    }
  });
  TeacherUI.syncAIContext();
  return TeacherUI.aiContext;
};

TeacherUI.uiContext = function() {
  TeacherUI.syncAIContext();
  return {
    tab: TeacherUI.aiContext.current_tab,
    visible_issue_id: TeacherUI.aiContext.current_issue_id,
    visible_student_id: TeacherUI.aiContext.current_student_id,
    visible_ability_id: TeacherUI.aiContext.current_ability_id,
    visible_candidate_id: TeacherUI.aiContext.current_candidate_id,
    visible_intervention_id: TeacherUI.aiContext.current_intervention_id,
    visible_panel: TeacherUI.workspacePanelForTab[TeacherUI.aiContext.current_tab] || "teacherToday"
  };
};

// ---- 优先级 helper ----
TeacherUI.priorityLevel = function(priority) {
  var p = parseFloat(priority);
  if (isNaN(p)) return { level: "low", label: String(priority || "low") };
  if (p >= 0.7) return { level: "high", label: p.toFixed(2) + " high" };
  if (p >= 0.4) return { level: "medium", label: p.toFixed(2) + " mid" };
  return { level: "low", label: p.toFixed(2) + " low" };
};

// ---- API helper ----
TeacherUI.fetchAuth = function(url, method, body) {
  var token = localStorage.getItem("mcp_auth_token") || "";
  var opts = { method: method || "POST", headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token } };
  if (body && method !== "GET") opts.body = JSON.stringify(body);
  return fetch(url, opts).then(function(r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  });
};

// ============================================================
// Class Management (TF-6D P2)
// ============================================================
TeacherUI.loadClasses = function() {
  TeacherUI.fetchAuth("/api/teacher/classes", "GET").then(function(data) {
    var classes = data.classes || [];
    TeacherUI._classes = classes;
    var savedClassId = parseInt(localStorage.getItem("mcp_teacher_class_id") || "0", 10);
    var selected = null;
    if (savedClassId) {
      for (var i = 0; i < classes.length; i++) {
        if (classes[i].id === savedClassId) { selected = classes[i]; break; }
      }
      // P6-E: clear stale localStorage if class no longer exists
      if (!selected) localStorage.removeItem("mcp_teacher_class_id");
    }
    if (!selected && classes.length > 0) {
      selected = classes[0];
      localStorage.setItem("mcp_teacher_class_id", String(selected.id));
    }
    TeacherUI.setCurrentClass(selected);
    TeacherUI.renderClassDropdown();
  }).catch(function(e) {
    console.warn("Load classes failed:", e.message);
    TeacherUI.setCurrentClass(null);
  });
};

TeacherUI.clearClassScopedState = function() {
  // P6-D: Clear all class-scoped cache when switching class
  TeacherUI._issuesCache = null;
  TeacherUI.currentIssueId = null;
  TeacherUI._selectedStudents = [];
  TeacherUI._batchParsedStudents = [];
  TeacherUI._allStudents = [];
  TeacherUI._commentFilter = "all";
  TeacherUI._currentCommentId = null;
  TeacherUI._selectedCommentIds = [];
  if (TeacherUI._commentState) TeacherUI._commentState = {};
  if (TeacherUI._ciState) TeacherUI._ciState = {};
  TeacherUI.updateAIContext({
    current_issue_id: null,
    current_issue_title: "",
    current_student_ids: [],
    current_student_id: null,
    current_ability_id: null,
    current_candidate_id: null,
    current_intervention_id: null,
    current_intervention_draft: null
  });
  // Close any open modals/drawers
  var drawer = document.getElementById("issueDetailDrawer");
  if (drawer) drawer.classList.remove("open");
  var manageModal = document.getElementById("manageStudentsModal");
  if (manageModal) manageModal.style.display = "none";
};

TeacherUI.setCurrentClass = function(cls) {
  // P6-D: Clear old class cache before switching
  if (TeacherUI.currentClassId && cls && TeacherUI.currentClassId !== cls.id) {
    TeacherUI.clearClassScopedState();
  }
  TeacherUI.currentClass = cls;
  TeacherUI.currentClassId = cls ? cls.id : null;
  TeacherUI.updateAIContext({
    class_id: TeacherUI.currentClassId,
    job_role: cls ? (cls.job_role || "") : ""
  });
  // P7-I: Update AI scope display
  var scopeEl = document.getElementById("teacherScope");
  if (scopeEl) scopeEl.textContent = cls ? "当前范围： " + cls.name : "未选择班级";
  var labelEl = document.getElementById("teacherClassLabel");
  var metaEl = document.getElementById("teacherClassMeta");
  var manageBtn = document.getElementById("manageClassBtn");
  if (cls) {
    if (labelEl) { labelEl.textContent = cls.name; labelEl.style.cursor = "pointer"; labelEl.onclick = function() { TeacherUI.toggleClassDropdown(); }; }
    if (metaEl) metaEl.textContent = (cls.student_count || 0) + " 人" + (cls.job_role ? " · " + cls.job_role : "");
    if (manageBtn) manageBtn.style.display = "";
    localStorage.setItem("mcp_teacher_class_id", String(cls.id));
  } else {
    if (labelEl) labelEl.textContent = "未选择班级";
    if (metaEl) metaEl.textContent = "";
    if (manageBtn) manageBtn.style.display = "none";
  }
  if (TeacherUI.currentTab) TeacherUI.switchTab(TeacherUI.currentTab);
};

TeacherUI.switchTeacherClass = function(classId) {
  // P7-C: Unified class switch workflow
  var target = null;
  for (var i = 0; i < TeacherUI._classes.length; i++) {
    if (TeacherUI._classes[i].id === classId) { target = TeacherUI._classes[i]; break; }
  }
  if (!target) return;
  TeacherUI.setCurrentClass(target);
  // Close dropdown
  var dropdown = document.getElementById("classDropdown");
  if (dropdown) dropdown.style.display = "none";
};

TeacherUI.toggleClassDropdown = function() {
  var dropdown = document.getElementById("classDropdown");
  if (!dropdown) return;
  if (dropdown.style.display === "block") {
    dropdown.style.display = "none";
  } else {
    dropdown.style.display = "block";
    TeacherUI.renderClassDropdown();
  }
};

TeacherUI.renderClassDropdown = function() {
  var dropdown = document.getElementById("classDropdown");
  if (!dropdown || dropdown.style.display !== "block") return;
  var html = "";
  TeacherUI._classes.forEach(function(cls) {
    var active = cls.id === TeacherUI.currentClassId ? " active" : "";
    html += '<div class="class-dropdown-item' + active + '" onclick="TeacherUI.switchTeacherClass(' + cls.id + ')">';
    html += '<span>' + TeacherUI.escHtml(cls.name) + '</span>';
    html += '<span class="class-dropdown-meta">' + (cls.student_count || 0) + ' 人</span>';
    html += '</div>';
  });
  html += '<div class="class-dropdown-divider"></div>';
  html += '<div class="class-dropdown-item" onclick="TeacherUI.openCreateClass();TeacherUI.toggleClassDropdown()">+ 创建班级</div>';
  html += '<div class="class-dropdown-item" onclick="TeacherUI.openManageStudents();TeacherUI.toggleClassDropdown()">管理当前班级</div>';
  dropdown.innerHTML = html;
};

TeacherUI.openCreateClass = function() {
  var modal = document.getElementById("createClassModal");
  if (modal) modal.style.display = "flex";
  var nameEl = document.getElementById("newClassName");
  var termEl = document.getElementById("newClassTerm");
  var errEl = document.getElementById("createClassError");
  if (nameEl) nameEl.value = "";
  if (termEl) termEl.value = "";
  if (errEl) errEl.style.display = "none";
};

TeacherUI.closeCreateClass = function() {
  var modal = document.getElementById("createClassModal");
  if (modal) modal.style.display = "none";
};

TeacherUI.submitCreateClass = function() {
  var nameEl = document.getElementById("newClassName");
  var jobEl = document.getElementById("newClassJobRole");
  var termEl = document.getElementById("newClassTerm");
  var errEl = document.getElementById("createClassError");
  var name = nameEl ? nameEl.value.trim() : "";
  var jobRole = jobEl ? jobEl.value : "";
  var term = termEl ? termEl.value.trim() : "";
  if (!name) {
    if (errEl) { errEl.textContent = "Please enter class name"; errEl.style.display = "block"; }
    return;
  }
  TeacherUI.fetchAuth("/api/teacher/classes", "POST", {
    name: name, job_role: jobRole, term: term
  }).then(function(data) {
    if (data.ok && data.class) {
      TeacherUI.closeCreateClass();
      TeacherUI._classes.push(data.class);
      TeacherUI.setCurrentClass(data.class);
    } else {
      if (errEl) { errEl.textContent = data.error || "创建失败"; errEl.style.display = "block"; }
    }
  }).catch(function(e) {
    if (errEl) { errEl.textContent = "创建失败: " + e.message; errEl.style.display = "block"; }
  });
};

// ============================================================
// Student Management (TF-6D P3)
// ============================================================
TeacherUI.openManageStudents = function() {
  if (!TeacherUI.currentClassId) return;
  var modal = document.getElementById("manageStudentsModal");
  if (!modal) return;
  modal.style.display = "flex";
  var titleEl = document.getElementById("manageClassTitle");
  if (titleEl && TeacherUI.currentClass) titleEl.textContent = TeacherUI.currentClass.name;
  var searchEl = document.getElementById("studentSearchInput");
  if (searchEl) searchEl.value = "";
  var batchArea = document.getElementById("batchInputArea");
  if (batchArea) batchArea.style.display = "none";
  TeacherUI._selectedStudents = [];
  TeacherUI.loadAvailableStudents();
};

TeacherUI.closeManageStudents = function() {
  var modal = document.getElementById("manageStudentsModal");
  if (modal) modal.style.display = "none";
  TeacherUI._selectedStudents = [];
};

TeacherUI.loadAvailableStudents = function(search) {
  if (!TeacherUI.currentClassId) return;
  var url = "/api/teacher/students/available?class_id=" + TeacherUI.currentClassId;
  if (search) url += "&search=" + encodeURIComponent(search);
  var listEl = document.getElementById("studentManageList");
  if (listEl) listEl.innerHTML = '<div class="muted" style="padding:20px">加载学生中...</div>';
  TeacherUI.fetchAuth(url, "GET").then(function(data) {
    TeacherUI._allStudents = data.students || [];
    TeacherUI.renderStudentManageList();
  }).catch(function(e) {
    if (listEl) listEl.innerHTML = '<div style="padding:20px;color:#f87171">学生列表加载失败。</div>';
  });
};

TeacherUI.renderStudentManageList = function() {
  var listEl = document.getElementById("studentManageList");
  if (!listEl) return;
  var html = "";
  var inClass = 0;
  var selectedSet = new Set(TeacherUI._selectedStudents);
  TeacherUI._allStudents.forEach(function(s) {
    var sid = String(s.username || "");
    var name = TeacherUI.escHtml(String(s.nickname || sid));
    var checked = selectedSet.has(sid) ? " checked" : "";
    if (s.in_current_class) inClass++;
    html += '<label class="student-manage-row" style="display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid #1e293b;cursor:pointer">';
    html += '<input type="checkbox" class="student-manage-check" data-username="' + sid + '"' + checked + ' style="width:16px;height:16px">';
    html += '<span style="flex:1">' + name + ' (' + sid + ')</span>';
    if (s.in_current_class) html += '<span class="badge badge-in-class">已在本班</span>';
    html += '</label>';
  });
  if (!TeacherUI._allStudents.length) {
    html = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">未找到学生。</div>';
  }
  listEl.innerHTML = html;
  var statusEl = document.getElementById("studentFilterStatus");
  if (statusEl) statusEl.textContent = "共 " + TeacherUI._allStudents.length + "，本班 " + inClass;
  listEl.querySelectorAll(".student-manage-check").forEach(function(cb) {
    cb.addEventListener("change", function() {
      var uname = cb.dataset.username;
      if (cb.checked) {
        if (!TeacherUI._selectedStudents.includes(uname)) TeacherUI._selectedStudents.push(uname);
      } else {
        TeacherUI._selectedStudents = TeacherUI._selectedStudents.filter(function(x) { return x !== uname; });
      }
      TeacherUI.updateSelectionCount();
    });
  });
  TeacherUI.updateSelectionCount();
};

TeacherUI.filterStudents = function() {
  var q = document.getElementById("studentSearchInput").value.trim();
  TeacherUI.loadAvailableStudents(q);
};

TeacherUI.updateSelectionCount = function() {
  var el = document.getElementById("studentSelectionCount");
  if (el) el.textContent = "已选择 " + TeacherUI._selectedStudents.length + " 人";
};

TeacherUI.addSelectedStudents = function() {
  if (!TeacherUI._selectedStudents.length) return;
  TeacherUI.fetchAuth("/api/teacher/classes/" + TeacherUI.currentClassId + "/students", "POST", {
    student_usernames: TeacherUI._selectedStudents.slice()
  }).then(function(data) {
    if (data.ok) {
      alert("Added " + data.added.length + " 人" + (data.already_in_class.length ? ", already in class " + data.already_in_class.length : ""));
      TeacherUI._selectedStudents = [];
      TeacherUI.loadAvailableStudents();
      TeacherUI.loadClasses();
    }
  }).catch(function(e) {
    alert("添加失败： " + e.message);
  });
};

TeacherUI.removeSelectedStudents = function() {
  if (!TeacherUI._selectedStudents.length) return;
  TeacherUI.fetchAuth("/api/teacher/classes/" + TeacherUI.currentClassId + "/students/remove", "POST", {
    student_usernames: TeacherUI._selectedStudents.slice()
  }).then(function(data) {
    if (data.ok) {
      alert("Removed " + data.removed.length + " 人");
      TeacherUI._selectedStudents = [];
      TeacherUI.loadAvailableStudents();
      TeacherUI.loadClasses();
    }
  }).catch(function(e) {
    alert("移除失败： " + e.message);
  });
};

TeacherUI.showBatchInput = function() {
  var area = document.getElementById("batchInputArea");
  if (area) area.style.display = "block";
  var resultEl = document.getElementById("batchParseResult");
  if (resultEl) resultEl.innerHTML = "";
};

TeacherUI.hideBatchInput = function() {
  var area = document.getElementById("batchInputArea");
  if (area) area.style.display = "none";
};

TeacherUI.parseBatchInput = function() {
  var raw = document.getElementById("batchStudentIds").value;
  var tokens = raw.split(/[\s,，;；]+/).filter(function(t) { return t.trim(); });
  var resultEl = document.getElementById("batchParseResult");
  var known = {};
  TeacherUI._allStudents.forEach(function(s) { known[String(s.username)] = true; });
  var found = [], notFound = [];
  tokens.forEach(function(t) {
    var uname = t.trim();
    if (!uname) return;
    if (known[uname]) found.push(uname);
    else notFound.push(uname);
  });
  TeacherUI._batchParsedStudents = found;
  var html = '<div><strong>Parse result</strong></div>';
  html += '<div>Found ' + found.length + '</div>';
  if (notFound.length) html += '<div style="color:#f87171">Not found: ' + notFound.join(", ") + '</div>';
  if (found.length) html += '<div style="margin-top:8px"><button class="btn-primary" onclick="TeacherUI.addBatchStudents()">Add ' + found.length + ' found</button></div>';
  resultEl.innerHTML = html;
};

TeacherUI.addBatchStudents = function() {
  if (!TeacherUI._batchParsedStudents.length) return;
  TeacherUI.fetchAuth("/api/teacher/classes/" + TeacherUI.currentClassId + "/students", "POST", {
    student_usernames: TeacherUI._batchParsedStudents.slice()
  }).then(function(data) {
    if (data.ok) {
      alert("Added " + data.added.length + " 人" + (data.not_found.length ? ", not found " + data.not_found.length : ""));
      TeacherUI._batchParsedStudents = [];
      document.getElementById("batchInputArea").style.display = "none";
      TeacherUI.loadAvailableStudents();
      TeacherUI.loadClasses();
    }
  }).catch(function(e) {
    alert("添加失败： " + e.message);
  });
};

// ============================================================
// Navigation
// ============================================================
TeacherUI.initNav = function() {
  if (TeacherUI._navInitialized) return;
  TeacherUI._navInitialized = true;
  TeacherUI.loadClasses();
};

TeacherUI.switchTab = function(tabId) {
  TeacherUI.currentTab = tabId;
  TeacherUI.updateAIContext({ current_tab: tabId });
  var panels = document.querySelectorAll(".teacher-workspace-panel");
  panels.forEach(function(p) { p.classList.remove("active"); });
  var target = document.getElementById("tw-" + tabId);
  if (target) target.classList.add("active");
  var panelName = TeacherUI.workspacePanelForTab[tabId];
  if (panelName) {
    document.querySelectorAll("[data-workspace-panel]").forEach(function(b) {
      b.classList.toggle("active", b.dataset.workspacePanel === panelName);
    });
    document.querySelectorAll(".workspace-panel").forEach(function(s) {
      s.classList.toggle("active", s.id === "workspace" + panelName.charAt(0).toUpperCase() + panelName.slice(1));
    });
  }
  var loaders = {
    today: TeacherUI.loadToday,
    insights: TeacherUI.loadInsights,
    students: TeacherUI.loadStudents,
    feedback: TeacherUI.loadFeedback
  };
  if (loaders[tabId]) loaders[tabId]();
};

TeacherUI.showStudentList = function() {
  document.querySelectorAll(".student-mgmt-btn").forEach(function(btn) {
    btn.classList.toggle("active", btn.textContent.trim() === "学生列表");
  });
  TeacherUI.loadStudents();
};

// ============================================================
// Tab: Today (V2 Teaching Issues)
// ============================================================
TeacherUI.loadToday = function() {
  var c = document.getElementById("todayTeachingContent");
  if (!c) return;
  c.innerHTML = '<div class="muted" style="padding:20px">加载教学问题中...</div>';
  var payload = {};
  if (TeacherUI.currentClassId) payload.class_id = TeacherUI.currentClassId;
  TeacherUI.fetchAuth("/api/v2/teacher/issues", "POST", payload).then(function(data) {
    var issues = data.issues || data || [];
    if (!issues.length) {
      c.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">当前没有足够证据形成需要优先处理的教学问题。</div>';
      return;
    }
    TeacherUI._issuesCache = issues;
    TeacherUI.renderIssueList(issues, c);
    TeacherUI.renderTodaySuggestion(issues);
  }).catch(function(e) {
    c.innerHTML = '<div style="padding:20px;color:#f87171">加载失败。 <a href="#" onclick="TeacherUI.loadToday();return false">重试</a></div>';
  });
};

TeacherUI.renderIssueList = function(issues, container) {
  var html = '<div class="issue-list">';
  issues.forEach(function(issue) {
    var pl = TeacherUI.priorityLevel(issue.priority);
    var pc = "badge-priority-" + pl.level;
    var students = issue.affected_students || [];
    var title = TeacherUI.escHtml(issue.title || issue.issue_id || "未知");
    html += '<div class="issue-card" data-issue-id="' + issue.issue_id + '">';
    html += '<div class="issue-card-header"><span class="issue-card-title">' + title + '</span></div>';
    html += '<div class="issue-card-meta"><span class="' + pc + '">' + pl.label + '</span><span>' + students.length + ' 人</span></div>';
    html += '</div>';
  });
  html += '</div>';
  container.innerHTML = html;
  container.querySelectorAll(".issue-card").forEach(function(card) {
    card.addEventListener("click", function() {
      TeacherUI.openIssueDetail(card.dataset.issueId);
    });
  });
};

// ============================================================
// Issue Detail Drawer
// ============================================================
TeacherUI.openIssueDetail = function(issueId) {
  var drawer = document.getElementById("issueDetailDrawer");
  if (!drawer) return;
  TeacherUI.currentIssueId = issueId;
  TeacherUI.updateAIContext({
    current_issue_id: issueId,
    current_issue_title: "",
    current_student_ids: []
  });
  drawer.classList.add("open");
  var titleEl = drawer.querySelector(".issue-drawer-title");
  var bodyEl = drawer.querySelector(".issue-drawer-body") || drawer.querySelector(".issue-drawer-content");
  if (titleEl) titleEl.textContent = "Loading...";
  if (bodyEl) bodyEl.innerHTML = '<div style="padding:20px">Loading issue detail...</div>';

  var closeBtn = drawer.querySelector(".issue-drawer-close");
  if (closeBtn && !closeBtn._boundClose) {
    closeBtn._boundClose = true;
    closeBtn.addEventListener("click", function() { drawer.classList.remove("open"); });
  }

  var issue = null;
  if (TeacherUI._issuesCache) {
    for (var i = 0; i < TeacherUI._issuesCache.length; i++) {
      if (TeacherUI._issuesCache[i].issue_id === issueId) { issue = TeacherUI._issuesCache[i]; break; }
    }
  }
  if (issue) {
    TeacherUI.renderIssueDetail(issue, drawer);
  } else {
    var payload = {};
  if (TeacherUI.currentClassId) payload.class_id = TeacherUI.currentClassId;
  TeacherUI.fetchAuth("/api/v2/teacher/issues", "POST", payload).then(function(data) {
      var issues = data.issues || data || [];
      var found = null;
      for (var i = 0; i < issues.length; i++) {
        if (issues[i].issue_id === issueId) { found = issues[i]; break; }
      }
      if (found) TeacherUI.renderIssueDetail(found, drawer);
      else {
        if (titleEl) titleEl.textContent = "Not Found";
        if (bodyEl) bodyEl.innerHTML = '<div style="padding:40px;text-align:center">教学问题不存在或已过期。</div>';
      }
    }).catch(function() {
      if (titleEl) titleEl.textContent = "Error";
      if (bodyEl) bodyEl.innerHTML = '<div style="padding:40px;text-align:center;color:#f87171">Failed to load issue.</div>';
    });
  }
};

TeacherUI.renderIssueDetail = function(issue, drawer) {
  var titleEl = drawer.querySelector(".issue-drawer-title");
  var bodyEl = drawer.querySelector(".issue-drawer-body") || drawer.querySelector(".issue-drawer-content");
  var pl = TeacherUI.priorityLevel(issue.priority);
  var students = issue.affected_students || [];
  var ability = TeacherUI.escHtml(issue.primary_ability_id || "");
  TeacherUI.updateAIContext({
    current_issue_id: issue.issue_id || TeacherUI.currentIssueId || "",
    current_issue_title: issue.title || issue.issue_id || "",
    current_student_ids: (issue.affected_students || []).slice(),
    current_ability_id: issue.primary_ability_id || null
  });

  if (titleEl) titleEl.textContent = issue.title || issue.issue_id || "未知";

  var html = '<div class="drawer-detail">';
  html += '<div class="issue-summary">' + TeacherUI.escHtml(issue.title || "当前教学问题") + '</div>';
  html += '<div class="detail-row"><span class="label">主要问题</span><span>学生在该能力上存在共性错误，建议优先干预。</span></div>';
  html += '<div class="detail-row"><span class="label">影响学生</span><span>' + students.length + ' 人</span></div>';
  html += '<div class="detail-row"><span class="label">主要能力</span><span>' + ability + '</span></div>';

  if (students.length > 0) {
    html += '<div class="detail-row"><span class="label">学生名单</span><span>';
    for (var i = 0; i < Math.min(students.length, 5); i++) {
      var sid = String(students[i]);
      html += '<button class="student-chip" data-student="' + sid + '">' + TeacherUI.escHtml(sid) + '</button> ';
    }
    if (students.length > 5) html += '... 共 ' + students.length + ' 人';
    html += '</span></div>';
  }

  var evidence = issue.evidence_summary || {};
  var topPatterns = issue.top_patterns || [];
  html += '<div class="detail-row"><strong>为什么判断成共性问题</strong></div>';
  html += '<div class="detail-row">' + TeacherUI.escHtml(evidence.student_count || students.length || 0) + ' 名学生出现相关证据，共 ' + TeacherUI.escHtml(evidence.event_count || 0) + ' 条学习事件。</div>';
  if (topPatterns.length) {
    html += '<div class="detail-row" style="margin-top:8px"><strong>学生具体错在哪里</strong></div>';
    topPatterns.forEach(function(p) {
      html += '<div class="detail-row" style="color:#fbbf24">- ' + TeacherUI.escHtml(p.label || "unknown") + ' x' + p.count + ' · ' + p.student_count + ' 人</div>';
    });
  } else {
    html += '<div class="detail-row" style="color:#94a3b8">暂无更细的重复过程证据。</div>';
  }
  html += '<details class="analysis-details"><summary>查看分析依据</summary>';
  html += '<div class="detail-row"><span class="label">优先级</span><span class="badge-priority-' + pl.level + '">' + pl.label + '</span></div>';
  html += '<div class="detail-row"><span class="label">置信度</span><span>' + ((issue.confidence || 0) * 100).toFixed(0) + '%</span></div>';
  html += '<div class="detail-row"><span class="label">严重程度</span><span>' + ((issue.severity || 0) * 100).toFixed(0) + '%</span></div>';
  html += '</details>';
  html += '<div style="margin-top:16px;display:flex;gap:8px">';
  html += '<button class="btn-secondary" onclick="TeacherUI.askIssueWhy()">问 AI 为什么</button>';
  html += '<button class="btn-primary" onclick="TeacherUI.generateCandidates()">生成干预方案</button>';
  html += '</div>';
  html += '</div>';

  if (bodyEl) {
    bodyEl.innerHTML = html;
    // Bind student chip clicks
    bodyEl.querySelectorAll(".student-chip").forEach(function(btn) {
      btn.addEventListener("click", function() {
        if (typeof openWorkspace === "function") openWorkspace("studentMgmt");
        setTimeout(function() { TeacherUI.lookupStudent(btn.dataset.student); }, 300);
      });
    });
  }
};

TeacherUI.renderTodaySuggestion = function(issues) {
  var sq = document.getElementById("suggestedQuestions");
  if (!sq || !issues.length) return;
  var top = issues[0];
  var title = top.title || top.issue_id || "教学问题";
  var students = (top.affected_students || []).length;
  var buttons = [
    { label: "查看问题", question: "解释当前教学问题" },
    { label: "为什么", question: "为什么？" },
    { label: "生成今日教学建议", question: "生成教学方案" }
  ];
  sq.innerHTML = '<div class="suggestion-label">' + TeacherUI.escHtml(title) + '，影响 ' + students + ' 人</div>' +
    buttons.map(function(q) {
      return '<button type="button" data-teacher-suggestion="' + TeacherUI.escHtml(q.question) + '">' + TeacherUI.escHtml(q.label) + '</button>';
    }).join("");
  sq.querySelectorAll("[data-teacher-suggestion]").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var input = document.getElementById("chatInput");
      if (input) input.value = btn.dataset.teacherSuggestion;
      if (typeof sendChat === "function") sendChat(btn.dataset.teacherSuggestion);
    });
  });
};

TeacherUI.askIssueWhy = function() {
  var drawer = document.getElementById("issueDetailDrawer");
  if (drawer) drawer.classList.remove("open");
  if (typeof closeWorkspace === "function") closeWorkspace();
  var input = document.getElementById("chatInput");
  if (input) {
    input.value = "为什么？";
    input.focus();
  }
};

TeacherUI.generateCandidates = function() {
  var drawer = document.getElementById("issueDetailDrawer");
  var bodyEl = drawer ? (drawer.querySelector(".issue-drawer-body") || drawer.querySelector(".issue-drawer-content")) : null;
  if (bodyEl) bodyEl.innerHTML = '<div style="padding:20px">生成方案中...</div>';

  var issueId = TeacherUI.currentIssueId;
  var students = [];
  var issueTitle = "";
  if (TeacherUI._issuesCache) {
    for (var i = 0; i < TeacherUI._issuesCache.length; i++) {
      if (TeacherUI._issuesCache[i].issue_id === issueId) {
        students = TeacherUI._issuesCache[i].affected_students || [];
        issueTitle = TeacherUI._issuesCache[i].title || "";
        break;
      }
    }
  }

  if (!TeacherUI.currentClassId) {
    if (bodyEl) bodyEl.innerHTML = '<div style="padding:20px;color:#f87171">请先选择班级。</div>';
    return;
  }
  TeacherUI.fetchAuth("/api/v2/teacher/issues/candidates", "POST", {
    class_id: TeacherUI.currentClassId, issue_id: issueId, student_ids: students.slice(0, 10)
  }).then(function(data) {
    var candidates = data.candidates || data || [];
    TeacherUI._candidatesCache = candidates;
    var html = '<div class="drawer-detail"><div style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)">Intervention Candidates</div><h3 style="margin:0 0 12px;color:#e2e8f0">教学干预方案（' + candidates.length + '）</h3>';
    if (!candidates.length) {
      html += '<div style="padding:20px;text-align:center">暂无可用干预方案。</div>';
    } else {
      candidates.slice(0, 5).forEach(function(c, idx) {
        html += TeacherUI.renderCandidateCard(c, idx);
      });
    }
    html += '<button class="btn-secondary" style="margin-top:12px" onclick="TeacherUI.loadToday()">返回今日教学</button>';
    html += '</div>';
    if (bodyEl) bodyEl.innerHTML = html;
    bodyEl.querySelectorAll(".candidate-card").forEach(function(card) {
      var btn = card.querySelector(".candidate-adopt");
      if (btn) {
        btn.addEventListener("click", function() {
          var candidateId = btn.dataset.candidateId;
          TeacherUI.selectCandidate(candidateId);
        });
      }
      var adjustBtn = card.querySelector(".candidate-ai-adjust");
      if (adjustBtn) {
        adjustBtn.addEventListener("click", function() {
          var candidateId = adjustBtn.dataset.candidateId;
          TeacherUI.selectCandidate(candidateId);
          var drawer = document.getElementById("issueDetailDrawer");
          if (drawer) drawer.classList.remove("open");
          var input = document.getElementById("chatInput");
          if (input) {
            input.value = "改成20分钟，并把001单独安排。";
            input.focus();
          }
        });
      }
    });
  }).catch(function(e) {
    if (bodyEl) bodyEl.innerHTML = '<div style="padding:20px;color:#f87171">方案生成失败。</div>';
  });
};

TeacherUI.getIssueData = function(issueId) {
  if (!TeacherUI._issuesCache) return null;
  for (var i = 0; i < TeacherUI._issuesCache.length; i++) {
    if (TeacherUI._issuesCache[i].issue_id === issueId) return TeacherUI._issuesCache[i];
  }
  return null;
};

TeacherUI.candidatePlan = function(candidate, issue, students) {
  var c = candidate || {};
  var abilityIds = c.ability_ids || [];
  if (!Array.isArray(abilityIds)) abilityIds = [abilityIds];
  var issueId = c.issue_id || (issue && issue.issue_id) || TeacherUI.currentIssueId || "";
  var targetStudents = c.target_students || students || TeacherUI.aiContext.current_student_ids || [];
  var plan = {
    candidate_id: c.candidate_id || "",
    issue_id: issueId,
    title: c.title || "教学干预方案",
    duration_minutes: 20,
    objective: "强化学生对本问题对应能力的理解，并通过实操纠正共性错误。",
    method: "集中讲解 + 实物辨认 + 分组练习",
    target_students: targetStudents.slice(),
    focus_students: [],
    ability_ids: abilityIds.slice(),
    resources: ["传感器实物/接线图", "PLC 输入模块或等效实训台"],
    steps: ["5分钟：回顾错误现象与安全要求", "10分钟：实物辨认和接线判断", "5分钟：分组复述并检查"],
    verification: "学生能够独立说明判断依据，并完成一次正确接线或辨析。",
    why: c.description || "该方案直接针对本问题的主要薄弱能力，适合短时间课堂干预。",
    expected_outcome: "相关错误事件减少，学生能正确完成目标能力判断。"
  };
  if (abilityIds.indexOf("sn_type_identify") >= 0) {
    plan.title = "集中纠错 + NPN/PNP 实物辨认";
    plan.objective = "区分 NPN/PNP 输出类型，并正确匹配 PLC 输入公共端。";
    plan.resources = ["NPN/PNP 传感器实物", "PLC 输入模块与接线图"];
    plan.verification = "学生能独立说明公共端匹配规则并完成接线判断。";
  }
  return plan;
};

TeacherUI.renderCandidateCard = function(candidate, idx) {
  var c = candidate || {};
  var cid = TeacherUI.escHtml(String(c.candidate_id || "C" + idx));
  var issue = TeacherUI.getIssueData(TeacherUI.currentIssueId);
  var students = c.target_students || (issue && issue.affected_students) || [];
  var plan = TeacherUI.candidatePlan(c, issue, students);
  var title = TeacherUI.escHtml(plan.title || c.title || "方案 " + (idx + 1));
  var typeLabel = { quiz: "诊断自测", scenario: "排故演练", explanation: "即时讲解", training_task: "实训任务", reassessment: "复测", knowledge_card: "知识卡片" }[c.intervention_type] || "教学干预";
  var html = '<div class="candidate-card" data-candidate-id="' + cid + '" style="padding:14px;border:1px solid #334155;border-radius:8px;margin:10px 0">';
  html += '<div class="candidate-card-title">方案 ' + (idx + 1) + ' · ' + title + '</div>';
  html += '<div class="candidate-meta"><span>建议用时：' + plan.duration_minutes + ' 分钟</span><span>适用：' + students.length + ' 名学生</span><span>' + typeLabel + '</span></div>';
  html += '<div class="candidate-body"><strong>教学目标</strong><div>' + TeacherUI.escHtml(plan.objective) + '</div></div>';
  html += '<div class="candidate-body"><strong>教学方式</strong><div>' + TeacherUI.escHtml(plan.method) + '</div></div>';
  html += '<div class="candidate-body"><strong>为什么推荐</strong><div>' + TeacherUI.escHtml(plan.why) + '</div></div>';
  html += '<div class="candidate-actions"><button type="button" class="btn-primary candidate-adopt" data-candidate-id="' + cid + '">采用方案</button>';
  html += '<button type="button" class="btn-secondary candidate-ai-adjust" data-candidate-id="' + cid + '">让 AI 调整</button></div>';
  html += '</div>';
  return html;
};

TeacherUI.selectCandidate = function(candidateId) {
  var candidates = TeacherUI._candidatesCache || [];
  var candidate = null;
  for (var i = 0; i < candidates.length; i++) {
    if (String(candidates[i].candidate_id) === String(candidateId)) { candidate = candidates[i]; break; }
  }
  if (!candidate) return;
  var issue = TeacherUI.getIssueData(TeacherUI.currentIssueId);
  var students = candidate.target_students || (issue && issue.affected_students) || TeacherUI.aiContext.current_student_ids || [];
  var plan = TeacherUI.candidatePlan(candidate, issue, students);
  TeacherUI.updateAIContext({
    current_candidate_id: candidateId,
    current_intervention_id: null,
    current_intervention_draft: plan,
    current_student_ids: students.slice()
  });
  TeacherUI.openInterventionPreview(plan, candidateId, TeacherUI.currentIssueId, students, null);
};

TeacherUI.openInterventionPreview = function(plan, candidateId, issueId, students, interventionId) {
  var drawer = document.getElementById("issueDetailDrawer");
  if (!drawer) return;
  drawer.classList.add("open");
  var titleEl = drawer.querySelector(".issue-drawer-title");
  var bodyEl = drawer.querySelector(".issue-drawer-body") || drawer.querySelector(".issue-drawer-content");
  if (titleEl) titleEl.textContent = "教学方案预览";
  var html = '<div class="intervention-preview">';
  html += '<div class="detail-row"><span class="label">教学目标</span><span>' + TeacherUI.escHtml(plan.objective || "") + '</span></div>';
  html += '<div class="detail-row"><span class="label">对象学生</span><span>' + TeacherUI.escHtml((students || []).join("、") || "待选择") + '</span></div>';
  html += '<div class="detail-row"><span class="label">教学方式</span><span>' + TeacherUI.escHtml(plan.method || "") + '</span></div>';
  html += '<div class="detail-row"><span class="label">建议时长</span><span>' + TeacherUI.escHtml(String(plan.duration_minutes || 20)) + ' 分钟</span></div>';
  html += '<div class="detail-row"><span class="label">课堂步骤</span><span>' + TeacherUI.escHtml((plan.steps || []).join("；")) + '</span></div>';
  html += '<div class="detail-row"><span class="label">所需资源</span><span>' + TeacherUI.escHtml((plan.resources || []).join("；")) + '</span></div>';
  html += '<div class="detail-row"><span class="label">验证方式</span><span>' + TeacherUI.escHtml(plan.verification || "") + '</span></div>';
  if (plan.focus_students && plan.focus_students.length) {
    html += '<div class="detail-row" style="color:#fbbf24"><span class="label">单独安排</span><span>' + TeacherUI.escHtml(plan.focus_students.join("、")) + '</span></div>';
  }
  html += '<div class="intervention-preview-actions">';
  html += '<button type="button" class="btn-primary" onclick="TeacherUI.confirmIntervention()">确认创建</button>';
  html += '<button type="button" class="btn-secondary" onclick="TeacherUI.modifyInterventionFromPreview()">让 AI 修改</button>';
  html += '<button type="button" class="btn-secondary" onclick="TeacherUI.closeInterventionPreview()">取消</button>';
  html += '</div></div>';
  if (bodyEl) bodyEl.innerHTML = html;
  TeacherUI._pendingIntervention = {
    plan: plan,
    candidate_id: candidateId,
    issue_id: issueId,
    student_ids: students || [],
    intervention_id: interventionId
  };
};

TeacherUI.closeInterventionPreview = function() {
  var drawer = document.getElementById("issueDetailDrawer");
  if (drawer) drawer.classList.remove("open");
  TeacherUI._pendingIntervention = null;
};

TeacherUI.modifyInterventionFromPreview = function() {
  var drawer = document.getElementById("issueDetailDrawer");
  if (drawer) drawer.classList.remove("open");
  if (typeof closeWorkspace === "function") closeWorkspace();
  var input = document.getElementById("chatInput");
  if (input) {
    input.value = "改成20分钟，并把001单独安排。";
    input.focus();
  }
};

TeacherUI.confirmIntervention = function() {
  var pending = TeacherUI._pendingIntervention;
  if (!pending) return;
  var body = {
    class_id: TeacherUI.currentClassId,
    issue_id: pending.issue_id,
    candidate_id: pending.candidate_id,
    student_ids: pending.student_ids,
    plan: pending.plan
  };
  TeacherUI.fetchAuth("/api/v2/teacher/interventions", "POST", body).then(function(data) {
    if (data.error) throw new Error(data.error);
    TeacherUI.updateAIContext({
      current_intervention_id: data.intervention_id,
      current_intervention_draft: pending.plan
    });
    TeacherUI.renderInterventionCreated(data);
  }).catch(function(e) {
    var drawer = document.getElementById("issueDetailDrawer");
    if (drawer) drawer.classList.add("open");
    var bodyEl = drawer.querySelector(".issue-drawer-body") || drawer.querySelector(".issue-drawer-content");
    if (bodyEl) bodyEl.innerHTML = '<div style="padding:20px;color:#f87171">创建干预失败：' + TeacherUI.escHtml(e.message) + '</div>';
  });
};

TeacherUI.renderInterventionCreated = function(data) {
  var drawer = document.getElementById("issueDetailDrawer");
  if (!drawer) return;
  drawer.classList.add("open");
  var titleEl = drawer.querySelector(".issue-drawer-title");
  var bodyEl = drawer.querySelector(".issue-drawer-body") || drawer.querySelector(".issue-drawer-content");
  if (titleEl) titleEl.textContent = "干预已创建";
  var html = '<div class="intervention-created">';
  html += '<div class="detail-row"><span class="label">干预 ID</span><span>' + TeacherUI.escHtml(data.intervention_id || "") + '</span></div>';
  html += '<div class="detail-row"><span class="label">状态</span><span>草稿</span></div>';
  html += '<div class="detail-row"><span class="label">适用学生</span><span>' + TeacherUI.escHtml((TeacherUI._pendingIntervention ? TeacherUI._pendingIntervention.student_ids : []).join("、")) + '</span></div>';
  html += '<div class="detail-row"><span class="label">说明</span><span>干预已进入正式草稿，教师确认后可进入执行。</span></div>';
  html += '<div style="margin-top:16px;display:flex;gap:8px">';
  html += '<button type="button" class="btn-primary" onclick="TeacherUI.confirmInterventionStatus()">确认进入执行</button>';
  html += '<button type="button" class="btn-secondary" onclick="TeacherUI.openInterventionDetail(\'' + TeacherUI.escHtml(data.intervention_id) + '\')">查看状态</button>';
  html += '</div></div>';
  if (bodyEl) bodyEl.innerHTML = html;
};

TeacherUI.confirmInterventionStatus = function() {
  var interventionId = TeacherUI.aiContext.current_intervention_id;
  if (!interventionId) return;
  TeacherUI.fetchAuth("/api/v2/teacher/interventions/" + encodeURIComponent(interventionId) + "/confirm", "POST", {}).then(function(data) {
    if (!data.ok) throw new Error(data.error || "确认失败");
    TeacherUI.renderInterventionStatus({ intervention_id: interventionId, status: "planned", plan_snapshot: TeacherUI.aiContext.current_intervention_draft || {} });
  }).catch(function(e) {
    alert("确认失败：" + e.message);
  });
};

TeacherUI.openInterventionDetail = function(interventionId) {
  TeacherUI.fetchAuth("/api/v2/teacher/interventions/" + encodeURIComponent(interventionId), "GET").then(function(data) {
    TeacherUI.updateAIContext({
      current_intervention_id: interventionId,
      current_intervention_draft: data.plan_snapshot || TeacherUI.aiContext.current_intervention_draft || {}
    });
    TeacherUI.renderInterventionStatus(data);
  }).catch(function() {
    TeacherUI.renderInterventionStatus({ intervention_id: interventionId, status: "not_found", plan_snapshot: {} });
  });
};

TeacherUI.renderInterventionStatus = function(data) {
  var drawer = document.getElementById("issueDetailDrawer");
  if (!drawer) return;
  drawer.classList.add("open");
  var titleEl = drawer.querySelector(".issue-drawer-title");
  var bodyEl = drawer.querySelector(".issue-drawer-body") || drawer.querySelector(".issue-drawer-content");
  var status = data.status || "draft";
  var label = { draft: "草稿", planned: "已确认 / 待执行", reviewed: "已审核", assigned: "已分配", in_progress: "执行中", completed: "已完成", evaluated: "已评估" }[status] || status;
  if (titleEl) titleEl.textContent = "干预状态";
  var plan = data.plan_snapshot || TeacherUI.aiContext.current_intervention_draft || {};
  var html = '<div class="intervention-status">';
  html += '<div class="detail-row"><span class="label">干预 ID</span><span>' + TeacherUI.escHtml(data.intervention_id || "") + '</span></div>';
  html += '<div class="detail-row"><span class="label">状态</span><span>' + TeacherUI.escHtml(label) + '</span></div>';
  html += '<div class="detail-row"><span class="label">建议用时</span><span>' + TeacherUI.escHtml(String(plan.duration_minutes || 20)) + ' 分钟</span></div>';
  html += '<div class="detail-row"><span class="label">适用学生</span><span>' + TeacherUI.escHtml((plan.target_students || []).join("、") || "无") + '</span></div>';
  if (status === "draft") {
    html += '<div style="margin-top:16px;display:flex;gap:8px"><button class="btn-primary" onclick="TeacherUI.confirmInterventionStatus()">确认进入执行</button></div>';
  }
  html += '</div>';
  if (bodyEl) bodyEl.innerHTML = html;
};

// ============================================================
// Tab: Insights
// ============================================================
TeacherUI.loadInsights = function() {
  var c = document.getElementById("tw-insights");
  if (!c) return;
  if (!TeacherUI.currentClassId) {
    c.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">请先创建班级。</div>';
    return;
  }
  c.innerHTML = '<div class="muted" style="padding:20px">Loading class insights...</div>';
  var cid = TeacherUI.currentClassId;
  Promise.all([
    TeacherUI.fetchAuth("/api/teacher/class/overview?class_id=" + cid, "GET"),
    TeacherUI.fetchAuth("/api/teacher/class/ability-graph?class_id=" + cid, "GET"),
    TeacherUI.fetchAuth("/api/teacher/class/common-issues?class_id=" + cid, "GET")
  ]).then(function(results) {
    var overview = results[0] || {};
    var graph = results[1] || { nodes: [] };
    var issues = results[2] || { issues: [] };
    var issueList = issues.issues || [];
    var html = '<div style="padding:16px"><h3 style="color:#e2e8f0;margin:0 0 8px">班级洞察</h3>';
    html += '<div style="display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap">';
    html += '<span class="badge">学生数： ' + (overview.total_students || 0) + '</span>';
    html += '<span class="badge">证据： ' + Math.round((overview.evidence_coverage || 0) * 100) + '%</span>';
    html += '<span class="badge">共性问题： ' + issueList.length + '</span>';
    var risk = overview.risk_distribution || {};
    if (risk.high) html += '<span class="badge badge-danger">高风险： ' + risk.high + '</span>';
    if (risk.attention) html += '<span class="badge badge-warning">需关注： ' + risk.attention + '</span>';
    html += '</div>';
    var weakest = overview.weakest_abilities || [];
    if (weakest.length) {
      html += '<div style="margin-bottom:16px"><strong style="color:#e2e8f0">班级最薄弱能力</strong></div>';
      weakest.forEach(function(w, idx) {
        var masteryPct = Math.round((w.mean_mastery || 0) * 100);
        var ratioPct = Math.round((w.weak_ratio || 0) * 100);
        var abilityId = w.ability_id || w.id || "";
        html += '<div class="insight-ability-row" data-ability-id="' + TeacherUI.escHtml(abilityId) + '" style="margin-bottom:8px;cursor:pointer">';
        html += '<div style="display:flex;justify-content:space-between;color:#cbd5e1;font-size:0.9rem">';
        html += '<span>' + (idx + 1) + '. ' + TeacherUI.escHtml(w.label || w.ability_id) + '</span>';
        html += '<span>' + w.weak_student_count + ' 薄弱 · ' + ratioPct + '%</span>';
        html += '</div>';
        html += '<div style="background:rgba(255,255,255,0.08);border-radius:4px;height:8px;margin-top:4px">';
        html += '<div style="background:#f87171;height:8px;border-radius:4px;width:' + masteryPct + '%"></div>';
        html += '</div>';
        html += '<div style="display:flex;gap:6px;margin-top:6px">';
        html += '<button type="button" class="btn-small" data-ability-action="why">解释为什么薄弱</button>';
        html += '<button type="button" class="btn-small" data-ability-action="students">查看受影响学生</button>';
        html += '<button type="button" class="btn-small" data-ability-action="group">生成分组教学</button>';
        html += '</div>';
        html += '</div>';
      });
    }
    html += '<div id="teacherClassGraphDiagram" style="width:100%;height:300px"></div>';
    html += '</div>';
    c.innerHTML = html;
    c.querySelectorAll(".insight-ability-row").forEach(function(row) {
      row.addEventListener("click", function(ev) {
        if (ev.target.closest("button")) return;
        TeacherUI.updateAIContext({ current_ability_id: row.dataset.abilityId || null });
      });
    });
    c.querySelectorAll("[data-ability-action]").forEach(function(btn) {
      btn.addEventListener("click", function() {
        TeacherUI.updateAIContext({ current_ability_id: btn.closest(".insight-ability-row")?.dataset.abilityId || null });
        var prompts = {
          why: "解释这个能力为什么薄弱",
          students: "查看受影响学生",
          group: "生成分组教学"
        };
        TeacherUI.askAbility(prompts[btn.dataset.abilityAction] || "解释这个能力为什么薄弱");
      });
    });
    if (typeof renderGraphDiagram === "function" && (graph.nodes || []).length) {
      setTimeout(function() { renderGraphDiagram(graph, "teacherClassGraphDiagram"); }, 200);
    }
  }).catch(function() {
    c.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">班级洞察加载失败。</div>';
  });
};

// ============================================================
// Tab: Students
// ============================================================
TeacherUI.loadStudents = function() {
  var c = document.getElementById("tw-students");
  if (!c) return;
  c.innerHTML = '<div class="teacher-students-layout"><div id="teacherStudentListPane" style="flex:1;overflow-y:auto"></div><div id="teacherStudentDetailPane" style="flex:1;overflow-y:auto;border-left:1px solid #334155;padding:16px;display:none"></div></div>';
  var listPane = document.getElementById("teacherStudentListPane");
  listPane.innerHTML = '<div class="muted" style="padding:20px">加载学生列表中...</div>';

  if (!TeacherUI.currentClassId) {
    listPane.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">请先选择班级。</div>';
    return;
  }
  TeacherUI.fetchAuth("/api/teacher/classes/" + TeacherUI.currentClassId + "/students", "GET").then(function(data) {
    var students = data.students || [];
    if (!Array.isArray(students)) students = [];
    if (!students.length) {
      listPane.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">当前班级暂无学生。</div>';
      return;
    }
    var html = '<div class="student-list" style="overflow-y:auto;max-height:calc(100vh - 200px)">';
    students.forEach(function(s) {
      var sid = String(s.student_id || s.id || s.username || "");
      var name = TeacherUI.escHtml(String(s.nickname || s.name || sid));
      var weak = (s.weak_abilities || []).slice(0, 2).join(", ");
      html += '<div class="student-card" data-student-id="' + sid + '" style="padding:12px;border-bottom:1px solid #1e293b;cursor:pointer">';
      html += '<div style="font-weight:600;color:#e2e8f0">' + name + ' (' + sid + ')</div>';
      if (weak) html += '<div style="font-size:0.85em;color:#94a3b8">弱项： ' + TeacherUI.escHtml(weak) + '</div>';
      html += '</div>';
    });
    html += '</div>';
    listPane.innerHTML = html;
    listPane.querySelectorAll(".student-card").forEach(function(card) {
      card.addEventListener("click", function() { TeacherUI.lookupStudent(card.dataset.studentId); });
    });
  }).catch(function(e) {
    listPane.innerHTML = '<div style="padding:20px;color:#f87171">学生列表加载失败。</div>';
  });
};

TeacherUI.lookupStudent = function(studentId) {
  TeacherUI.updateAIContext({ current_student_id: String(studentId || "") });
  var detailPane = document.getElementById("teacherStudentDetailPane");
  if (!detailPane) {
    var old = document.getElementById("studentDetailContent");
    if (old) old.innerHTML = '<div style="padding:20px">Loading student ' + studentId + ' ...</div>';
    if (typeof fetchStudentDetail === "function") { fetchStudentDetail(studentId); return; }
    if (typeof loadStudentDetail === "function") { loadStudentDetail(studentId); return; }
    return;
  }
  detailPane.style.display = "block";
  detailPane.innerHTML = '<div style="padding:20px">加载学生详情中...</div>';
  var jobId = TeacherUI.currentClass ? TeacherUI.currentClass.job_role : "";
  var detailUrl = "/api/teacher/students/" + studentId;
  if (TeacherUI.currentClassId) detailUrl += "?class_id=" + TeacherUI.currentClassId;
  TeacherUI.fetchAuth(detailUrl, "GET").then(function(data) {
    if (data.error) {
      detailPane.innerHTML = '<div style="padding:20px;color:#f87171">No data for student ' + studentId + '</div>';
      return;
    }
    var name = TeacherUI.escHtml(String(data.nickname || studentId));
    var weak = (data.weak_abilities || []).slice(0, 5);
    var strong = (data.strong_abilities || []).slice(0, 5);
    var patterns = data.diagnostic_patterns || [];
    var recentEvents = data.recent_events || [];
    var html = '<div class="student-detail"><h3>' + name + ' (' + studentId + ')</h3>';
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0">';
    html += '<button class="btn-secondary" onclick="TeacherUI.askStudent(\'总结该生\')">总结该生</button>';
    html += '<button class="btn-secondary" onclick="TeacherUI.askStudent(\'为什么他最近表现不好？\')">为什么薄弱</button>';
    html += '<button class="btn-secondary" onclick="TeacherUI.askStudent(\'生成针对性任务\')">生成针对性任务</button>';
    html += '</div>';
    html += '<div class="detail-row"><span>状态： <strong>' + TeacherUI.escHtml(String(data.status || "未知")) + '</strong></span></div>';
    if (data.overall_score !== undefined) html += '<div class="detail-row"><span>测评分： <strong>' + data.overall_score + '</strong></span></div>';
    if (data.evidence_count) html += '<div class="detail-row"><span>证据： ' + data.evidence_count + ' events</span></div>';
    if (data.evidence_coverage) html += '<div class="detail-row"><span>覆盖率： ' + Math.round(data.evidence_coverage * 100) + '%</span></div>';
    html += '<hr style="border-color:rgba(255,255,255,0.1);margin:12px 0">';
    if (weak.length) html += '<div class="detail-row"><span style="color:#f87171">弱项： ' + weak.map(TeacherUI.escHtml).join(", ") + '</span></div>';
    if (strong.length) html += '<div class="detail-row"><span style="color:#22c55e">强项： ' + strong.map(TeacherUI.escHtml).join(", ") + '</span></div>';
    if (patterns.length) {
      html += '<hr style="border-color:rgba(255,255,255,0.1);margin:12px 0">';
      html += '<div class="detail-row"><strong>诊断模式</strong></div>';
      patterns.slice(0, 5).forEach(function(p) {
        var label = typeof p === "string" ? p : (p.pattern_name || p.name || p.type || JSON.stringify(p));
        html += '<div class="detail-row" style="color:#fbbf24">- ' + TeacherUI.escHtml(label) + '</div>';
      });
    }
    if (recentEvents.length) {
      html += '<hr style="border-color:rgba(255,255,255,0.1);margin:12px 0">';
      html += '<div class="detail-row"><strong>最近学习</strong></div>';
      recentEvents.slice(0, 5).forEach(function(ev) {
        var desc = typeof ev === "string" ? ev : (ev.event_type || ev.type || ev.action || "Learning event");
        html += '<div class="detail-row" style="color:#94a3b8">- ' + TeacherUI.escHtml(desc) + '</div>';
      });
    }
    html += '</div>';
    detailPane.innerHTML = html;
  }).catch(function(e) {
    detailPane.innerHTML = '<div style="padding:20px;color:#f87171">学生详情加载失败。</div>';
  });
};

TeacherUI.askStudent = function(prompt) {
  if (typeof closeWorkspace === "function") closeWorkspace();
  var input = document.getElementById("chatInput");
  if (input) {
    input.value = prompt || "总结该生";
    input.focus();
  }
};

TeacherUI.askAbility = function(prompt) {
  if (typeof closeWorkspace === "function") closeWorkspace();
  var input = document.getElementById("chatInput");
  if (input) {
    input.value = prompt || "解释这个能力为什么薄弱";
    input.focus();
  }
};

// ============================================================
// Tab: Feedback
// ============================================================
TeacherUI._commentFilter = "all";

TeacherUI.loadFeedback = function() {
  var c = document.getElementById("tw-feedback");
  if (!c) return;
  if (!TeacherUI.currentClassId) {
    c.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">请先选择班级。</div>';
    return;
  }
  c.innerHTML = '<div class="muted" style="padding:20px">加载教学反馈中...</div>';
  var url = "/api/teacher/comments?class_id=" + TeacherUI.currentClassId;
  if (TeacherUI._commentFilter !== "all") url += "&status=" + TeacherUI._commentFilter;
  TeacherUI.fetchAuth(url, "GET").then(function(data) {
    var stats = data.stats || {};
    var comments = data.comments || [];
    var html = '<div style="padding:16px"><h3 style="color:#e2e8f0;margin:0 0 12px">教学反馈</h3>';
    html += '<div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">';
    var filters = [["all", "全部"], ["draft", "草稿"], ["reviewed", "已审核"], ["published", "已发布"]];
    filters.forEach(function(f) {
      var active = TeacherUI._commentFilter === f[0] ? "background:#14b8a6;color:#fff" : "background:rgba(255,255,255,0.08)";
      html += '<button style="padding:6px 12px;border-radius:6px;border:none;cursor:pointer;' + active + '" onclick="TeacherUI.setCommentFilter(\'' + f[0] + '\')">' + f[1] + ' (' + (stats[f[0]] || comments.length) + ')</button>';
    });
    html += '</div>';
    if (!comments.length) {
      html += '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">暂无评语。</div>';
    } else {
      comments.forEach(function(cm) {
        var sid = TeacherUI.escHtml(String(cm.student_id || ""));
        var status = TeacherUI.escHtml(String(cm.status || "draft"));
        var content = TeacherUI.escHtml(String(cm.content || cm.ai_draft || "").slice(0, 80));
        var evidenceCount = 0;
        evidenceCount = (cm.evidence || []).length;
        html += '<div class="comment-card" style="padding:12px;border:1px solid #334155;border-radius:8px;margin-bottom:8px;cursor:pointer" onclick="TeacherUI.openCommentDetail(' + cm.id + ')">';
        html += '<div style="font-weight:600;color:#e2e8f0">Student ' + sid + ' <span class="badge">' + status + '</span></div>';
        html += '<div style="color:#94a3b8;margin-top:4px">' + content + '</div>';
        html += '<div style="color:#64748b;font-size:0.8rem;margin-top:4px">' + evidenceCount + ' 条证据</div>';
        html += '</div>';
      });
    }
    html += '</div>';
    c.innerHTML = html;
  }).catch(function() {
    c.innerHTML = '<div style="padding:20px;color:rgba(255,255,255,0.4)">评语加载失败。</div>';
  });
};

TeacherUI.setCommentFilter = function(filter) {
  TeacherUI._commentFilter = filter;
  TeacherUI.loadFeedback();
};

TeacherUI.openCommentDetail = function(commentId) {
  var c = document.getElementById("tw-feedback");
  if (!c) return;
  TeacherUI.fetchAuth("/api/teacher/comments/" + commentId, "GET").then(function(cm) {
    var evidence = [];
    evidence = cm.evidence || [];
    var html = '<div style="padding:16px"><button class="btn-secondary" style="margin-bottom:8px" onclick="TeacherUI.loadFeedback()">返回列表</button>';
    html += '<h3 style="color:#e2e8f0;margin:0 0 8px">评语详情</h3>';
    html += '<div class="detail-row"><span>学生： ' + TeacherUI.escHtml(String(cm.student_id || "")) + '</span></div>';
    html += '<div class="detail-row"><span>状态： <strong>' + TeacherUI.escHtml(String(cm.status || "draft")) + '</strong></span></div>';
    if (cm.period_start) html += '<div class="detail-row"><span>周期： ' + cm.period_start + ' ~ ' + (cm.period_end || "") + '</span></div>';
    if (cm.ai_draft) html += '<div class="detail-row" style="margin-top:8px"><strong>AI 初稿</strong><p style="color:#94a3b8">' + TeacherUI.escHtml(cm.ai_draft) + '</p></div>';
    html += '<div class="detail-row"><strong>正文</strong><p style="color:#cbd5e1">' + TeacherUI.escHtml(cm.content || "") + '</p></div>';
    if (evidence.length) {
      html += '<hr style="border-color:rgba(255,255,255,0.1);margin:12px 0">';
      html += '<div class="detail-row"><strong>证据</strong></div>';
      evidence.forEach(function(ev) {
        var label = typeof ev === "string" ? ev : (ev.label || ev.type || JSON.stringify(ev));
        html += '<div class="detail-row" style="color:#94a3b8">- ' + TeacherUI.escHtml(label) + '</div>';
      });
    }
    html += '<div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">';
    html += '<button class="btn-secondary" onclick="TeacherUI.refineComment(' + commentId + ',\'regenerate\')">根据最新证据重新生成</button>';
    html += '<button class="btn-secondary" onclick="TeacherUI.refineComment(' + commentId + ',\'shorter\')">缩短</button>';
    html += '<button class="btn-secondary" onclick="TeacherUI.refineComment(' + commentId + ',\'specific\')">更具体</button>';
    html += '</div>';
    html += '<div style="display:flex;gap:8px;margin-top:16px">';
    if (cm.status === "draft") {
      html += '<button class="btn-primary" onclick="TeacherUI.reviewComment(' + commentId + ')">审核</button>';
    }
    if (cm.status === "reviewed") {
      html += '<button class="btn-primary" onclick="TeacherUI.publishComment(' + commentId + ')">发布</button>';
    }
    html += '</div>';
    html += '</div>';
    c.innerHTML = html;
  }).catch(function() {
    c.innerHTML = '<div style="padding:20px;color:#f87171">评语详情加载失败。</div>';
  });
};

TeacherUI.reviewComment = function(commentId) {
  TeacherUI.fetchAuth("/api/teacher/comments/" + commentId + "/review", "POST", {}).then(function() {
    TeacherUI.openCommentDetail(commentId);
  }).catch(function(e) {
    alert("审核 failed: " + e.message);
  });
};

TeacherUI.publishComment = function(commentId) {
  TeacherUI.fetchAuth("/api/teacher/comments/" + commentId + "/publish", "POST", {}).then(function() {
    TeacherUI.openCommentDetail(commentId);
  }).catch(function(e) {
    alert("发布 failed: " + e.message);
  });
};

TeacherUI.refineComment = function(commentId, mode) {
  var prompts = {
    regenerate: "根据最新证据重新生成这条评语",
    shorter: "把这条评语缩短",
    specific: "把这条评语写得更具体"
  };
  var input = document.getElementById("chatInput");
  if (input) {
    input.value = (prompts[mode] || prompts.regenerate) + "，评语ID " + commentId;
    input.focus();
  }
};

// ============================================================
// Teacher Copilot
// ============================================================
TeacherUI.initCopilot = function() {
  var form = document.getElementById("teacherChatForm");
  if (!form || form._copilotBound) return;
  form._copilotBound = true;
  form.removeAttribute("onsubmit");
  form.addEventListener("submit", function(ev) {
    ev.preventDefault();
    TeacherUI.sendCopilotMessage();
  });
};

TeacherUI.sendCopilotMessage = function() {
  var input = document.getElementById("copilotInput");
  if (!input || !input.value.trim()) return;
  var msg = input.value.trim();
  input.value = "";

  TeacherUI.messages.push({ role: "user", content: msg });
  TeacherUI.messages.push({ role: "loading", content: "AI 正在分析..." });
  TeacherUI.renderMessages();

  var token = localStorage.getItem("mcp_auth_token") || "";
  var jobRole = TeacherUI.currentClass ? TeacherUI.currentClass.job_role : "";
  var payload = { message: msg, job_role: jobRole };
  if (TeacherUI.currentClassId) payload.class_id = TeacherUI.currentClassId;
  fetch("/api/teacher/assistant/message", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
    body: JSON.stringify(payload)
  }).then(function(r) { return r.json(); })
  .then(function(data) {
    TeacherUI.messages.pop();
    TeacherUI.messages.push({ role: "assistant", content: data.answer || data.reply || data.message || "已收到回复" });
    TeacherUI.renderMessages();
  }).catch(function(e) {
    TeacherUI.messages.pop();
    TeacherUI.messages.push({ role: "error", content: "错误： " + (e.message || "网络错误") });
    TeacherUI.renderMessages();
  });
};

TeacherUI.renderMessages = function() {
  var container = document.getElementById("teacherChatMessages");
  if (!container) return;
  var html = "";
  TeacherUI.messages.forEach(function(m) {
    var cls = "msg-" + m.role;
    if (m.role === "error") cls += " msg-error";
    html += '<div class="' + cls + '" style="padding:8px 12px;margin:4px 0;border-radius:6px;word-break:break-word">';
    html += TeacherUI.escHtml(m.content);
    html += '</div>';
  });
  container.innerHTML = html;
  container.scrollTop = container.scrollHeight;
};

TeacherUI.executeAIAction = function(action) {
  if (!action || !action.type) return false;
  var type = action.type;
  if (type === "navigate") {
    if (typeof openWorkspace === "function" && action.module) openWorkspace(action.module);
    return true;
  }
  if (type === "open_issue" && action.issue_id) {
    if (typeof openWorkspace === "function") openWorkspace("teacherToday");
    setTimeout(function() { TeacherUI.openIssueDetail(action.issue_id); }, 250);
    return true;
  }
  if (type === "open_student" && action.student_id) {
    TeacherUI.updateAIContext({ current_student_id: String(action.student_id) });
    if (typeof openWorkspace === "function") openWorkspace("studentMgmt");
    setTimeout(function() { TeacherUI.lookupStudent(String(action.student_id)); }, 300);
    return true;
  }
  if (type === "open_ability" && action.ability_id) {
    TeacherUI.updateAIContext({ current_ability_id: action.ability_id });
    if (typeof openWorkspace === "function") openWorkspace("classInsights");
    return true;
  }
  if (type === "generate_candidates") {
    TeacherUI.updateAIContext({
      current_issue_id: action.issue_id || TeacherUI.aiContext.current_issue_id,
      current_student_ids: action.student_ids || TeacherUI.aiContext.current_student_ids
    });
    if (typeof openWorkspace === "function") openWorkspace("teacherToday");
    setTimeout(function() {
      if (action.issue_id) TeacherUI.openIssueDetail(action.issue_id);
      setTimeout(function() { TeacherUI.generateCandidates(); }, 500);
    }, 250);
    return true;
  }
  if (type === "select_candidate" && action.candidate_id) {
    TeacherUI.updateAIContext({
      current_candidate_id: action.candidate_id,
      current_issue_id: action.issue_id || TeacherUI.aiContext.current_issue_id,
      current_student_ids: action.student_ids || TeacherUI.aiContext.current_student_ids,
      current_intervention_draft: action.plan || TeacherUI.candidatePlan({
        candidate_id: action.candidate_id,
        issue_id: action.issue_id,
        target_students: action.student_ids
      }, null, action.student_ids)
    });
    TeacherUI.openInterventionPreview(
      TeacherUI.aiContext.current_intervention_draft,
      action.candidate_id,
      action.issue_id,
      action.student_ids,
      action.intervention_id || null
    );
    return true;
  }
  if (type === "draft_intervention") {
    TeacherUI.updateAIContext({
      current_candidate_id: action.candidate_id || TeacherUI.aiContext.current_candidate_id,
      current_issue_id: action.issue_id || TeacherUI.aiContext.current_issue_id,
      current_student_ids: action.student_ids || TeacherUI.aiContext.current_student_ids,
      current_intervention_draft: action.plan || TeacherUI.aiContext.current_intervention_draft
    });
    if (TeacherUI.aiContext.current_intervention_draft) {
      TeacherUI.openInterventionPreview(
        TeacherUI.aiContext.current_intervention_draft,
        TeacherUI.aiContext.current_candidate_id,
        TeacherUI.aiContext.current_issue_id,
        TeacherUI.aiContext.current_student_ids,
        TeacherUI.aiContext.current_intervention_id
      );
    } else {
      TeacherUI.generateCandidates();
    }
    return true;
  }
  if (type === "open_intervention" && action.intervention_id) {
    TeacherUI.openInterventionDetail(action.intervention_id);
    return true;
  }
  if (type === "ask_ai" && action.question) {
    var input = document.getElementById("chatInput");
    if (input) input.value = action.question;
    if (typeof sendChat === "function") sendChat(action.question);
    return true;
  }
  return false;
};
