// === teacher-ui.js - Teacher Decision Workspace (TF-6C Runtime Closure) ===
var TeacherUI = {
  currentTab: "today",
  currentIssueId: null,
  messages: [],
  _navInitialized: false,
  _issuesCache: null,
  currentClassId: null,
  currentClass: null,
  _classes: [],
  _selectedStudents: [],
  _batchParsedStudents: [],
  _allStudents: []
};

// ---- Safe HTML escape ----
TeacherUI.escHtml = function(text) {
  var d = document.createElement("div");
  d.textContent = text || "";
  return d.innerHTML;
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
  }).catch(function(e) {
    console.warn("Load classes failed:", e.message);
    TeacherUI.setCurrentClass(null);
  });
};

TeacherUI.clearClassScopedState = function() {
  // P6-D: Clear all class-scoped cache when switching class
  TeacherUI._issuesCache = null;
  TeacherUI.currentIssueId = null;
  TeacherUI.messages = [];
  TeacherUI._selectedStudents = [];
  TeacherUI._batchParsedStudents = [];
  TeacherUI._allStudents = [];
  if (TeacherUI._commentState) TeacherUI._commentState = {};
  if (TeacherUI._ciState) TeacherUI._ciState = {};
  // Clear AI message DOM
  var chatMsgs = document.getElementById("teacherChatMessages");
  if (chatMsgs) {
    chatMsgs.innerHTML = '<div class="chat-message assistant"><div class="chat-bubble">欢迎使用教学决策工作台。请提问或查看左侧教学问题。</div></div>';
  }
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
  // Clear old class scoped state
  TeacherUI.clearClassScopedState();
  // Update state
  TeacherUI.setCurrentClass(target);
  // Refresh current tab with new class data
  if (TeacherUI.currentTab) TeacherUI.switchTab(TeacherUI.currentTab);
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
    // Build dropdown items
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
    dropdown.style.display = "block";
  }
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

TeacherUI.add已选择Students = function() {
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

TeacherUI.remove已选择Students = function() {
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
  // Bind class management buttons
  var manageBtn = document.getElementById("manageClassBtn");
  if (manageBtn) manageBtn.addEventListener("click", function() { TeacherUI.openManageStudents(); });
  var createBtn = document.getElementById("createClassBtn");
  if (createBtn) createBtn.addEventListener("click", function() { TeacherUI.openCreateClass(); });
  var tabs = document.querySelectorAll(".teacher-nav-tab");
  tabs.forEach(function(tab) {
    tab.addEventListener("click", function() {
      tabs.forEach(function(t) { t.classList.remove("active"); });
      this.classList.add("active");
      TeacherUI.switchTab(this.dataset.tab);
    });
  });
  TeacherUI.switchTab("today");
};

TeacherUI.switchTab = function(tabId) {
  TeacherUI.currentTab = tabId;
  var panels = document.querySelectorAll(".teacher-workspace-panel");
  panels.forEach(function(p) { p.classList.remove("active"); });
  var target = document.getElementById("tw-" + tabId);
  if (target) target.classList.add("active");
  var loaders = {
    today: TeacherUI.loadToday,
    insights: TeacherUI.loadInsights,
    students: TeacherUI.loadStudents,
    feedback: TeacherUI.loadFeedback,
    standards: TeacherUI.loadStandards
  };
  if (loaders[tabId]) loaders[tabId]();
};

// ============================================================
// Tab: Today (V2 Teaching Issues)
// ============================================================
TeacherUI.loadToday = function() {
  var c = document.getElementById("todayTeaching正文");
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

  if (titleEl) titleEl.textContent = issue.title || issue.issue_id || "未知";

  var html = '<div class="drawer-detail">';
  html += '<div class="detail-row"><span class="label">优先级</span><span class="badge-priority-' + pl.level + '">' + pl.label + '</span></div>';
  html += '<div class="detail-row"><span class="label">置信度</span><span>' + ((issue.confidence || 0) * 100).toFixed(0) + '%</span></div>';
  html += '<div class="detail-row"><span class="label">严重程度</span><span>' + ((issue.severity || 0) * 100).toFixed(0) + '%</span></div>';
  html += '<div class="detail-row"><span class="label">主要能力</span><span>' + ability + '</span></div>';
  html += '<div class="detail-row"><span class="label">影响学生</span><span>' + students.length + '</span></div>';

  if (Students.length > 0) {
    html += '<div class="detail-row"><span class="label">Students</span><span>';
    for (var i = 0; i < Math.min(Students.length, 5); i++) {
      var sid = String(Students[i]);
      html += '<button class="student-chip" data-student="' + sid + '">' + TeacherUI.escHtml(sid) + '</button> ';
    }
    if (Students.length > 5) html += '... ' + students.length + ' total';
    html += '</span></div>';
  }

  var evidence = issue.evidence_summary || {};
  var topPatterns = issue.top_patterns || [];
  html += '<hr style="border-color:rgba(255,255,255,0.1);margin:12px 0">';
  html += '<div class="detail-row"><strong>为什么这是教学问题？</strong></div>';
  html += '<div class="detail-row">学生数： ' + (evidence.student_count || affected.length || 0) + '</div>';
  html += '<div class="detail-row">学习事件： ' + (evidence.event_count || 0) + '</div>';
  html += '<div class="detail-row">诊断模式： ' + (evidence.pattern_count || 0) + '</div>';
  if (topPatterns.length) {
    html += '<div class="detail-row" style="margin-top:8px"><strong>典型问题模式</strong></div>';
    topPatterns.forEach(function(p) {
      html += '<div class="detail-row" style="color:#fbbf24">- ' + TeacherUI.escHtml(p.label || "unknown") + ' x' + p.count + ' · ' + p.student_count + ' 人</div>';
    });
  } else {
    html += '<div class="detail-row" style="color:#94a3b8">暂无重复过程模式证据。</div>';
  }
  html += '<div style="margin-top:16px;display:flex;gap:8px">';
  html += '<button class="btn-primary" onclick="TeacherUI.generateCandidates()">生成干预方案</button>';
  html += '</div>';
  html += '</div>';

  if (bodyEl) {
    bodyEl.innerHTML = html;
    // Bind student chip clicks
    bodyEl.querySelectorAll(".student-chip").forEach(function(btn) {
      btn.addEventListener("click", function() {
        TeacherUI.switchTab("人");
        setTimeout(function() { TeacherUI.lookupStudent(btn.dataset.student); }, 300);
      });
    });
  }
};

TeacherUI.generateCandidates = function() {
  var drawer = document.getElementById("issueDetailDrawer");
  var bodyEl = drawer ? (drawer.querySelector(".issue-drawer-body") || drawer.querySelector(".issue-drawer-content")) : null;
  if (bodyEl) bodyEl.innerHTML = '<div style="padding:20px">生成方案中...</div>';

  var issueId = TeacherUI.currentIssueId;
  var students = [];
  if (TeacherUI._issuesCache) {
    for (var i = 0; i < TeacherUI._issuesCache.length; i++) {
      if (TeacherUI._issuesCache[i].issue_id === issueId) {
        students = TeacherUI._issuesCache[i].affected_students || [];
        break;
      }
    }
  }

  if (!TeacherUI.currentClassId) {
    if (bodyEl) bodyEl.innerHTML = '<div style="padding:20px;color:#f87171">请先选择班级。</div>';
    return;
  }
  TeacherUI.fetchAuth("/api/v2/teacher/issues/candidates", "POST", {
    class_id: TeacherUI.currentClassId, issue_id: issueId, student_ids: Students.slice(0, 10)
  }).then(function(data) {
    var candidates = data.candidates || data || [];
    var html = '<div class="drawer-detail"><h3 style="margin:0 0 12px;color:#e2e8f0">Intervention Candidates (' + candidates.length + ')</h3>';
    if (!candidates.length) {
      html += '<div style="padding:20px;text-align:center">暂无可用干预方案。</div>';
    } else {
      candidates.slice(0, 5).forEach(function(c, idx) {
        var cid = TeacherUI.escHtml(String(c.candidate_id || "C" + idx));
        var rtype = TeacherUI.escHtml(String(c.resource_type || "unknown"));
        var score = (c.score !== undefined ? Number(c.score).toFixed(2) : "N/A");
        html += '<div class="candidate-card" style="padding:12px;border:1px solid #334155;border-radius:8px;margin:8px 0">';
        html += '<div style="font-weight:600">Candidate #' + (idx + 1) + ': ' + cid + '</div>';
        html += '<div>Resource: ' + rtype + ' | Score: ' + score + '</div>';
        if (c.reasons && c.reasons.length) html += '<div style="font-size:0.85em;color:#94a3b8">' + TeacherUI.escHtml(String(c.reasons[0])) + '</div>';
        html += '</div>';
      });
    }
    html += '<button class="btn-primary" style="margin-top:12px" onclick="TeacherUI.loadToday()">Back</button>';
    html += '</div>';
    if (bodyEl) bodyEl.innerHTML = html;
  }).catch(function(e) {
    if (bodyEl) bodyEl.innerHTML = '<div style="padding:20px;color:#f87171">方案生成失败。</div>';
  });
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
    var 薄弱est = overview.薄弱est_abilities || [];
    if (薄弱est.length) {
      html += '<div style="margin-bottom:16px"><strong style="color:#e2e8f0">班级最薄弱能力</strong></div>';
      薄弱est.forEach(function(w, idx) {
        var masteryPct = Math.round((w.mean_mastery || 0) * 100);
        var ratioPct = Math.round((w.薄弱_ratio || 0) * 100);
        html += '<div style="margin-bottom:8px">';
        html += '<div style="display:flex;justify-content:space-between;color:#cbd5e1;font-size:0.9rem">';
        html += '<span>' + (idx + 1) + '. ' + TeacherUI.escHtml(w.label || w.ability_id) + '</span>';
        html += '<span>' + w.薄弱_student_count + ' 薄弱 · ' + ratioPct + '%</span>';
        html += '</div>';
        html += '<div style="background:rgba(255,255,255,0.08);border-radius:4px;height:8px;margin-top:4px">';
        html += '<div style="background:#f87171;height:8px;border-radius:4px;width:' + masteryPct + '%"></div>';
        html += '</div>';
        html += '</div>';
      });
    }
    html += '<div id="teacherClass当前图谱Diagram" style="width:100%;height:300px"></div>';
    html += '</div>';
    c.innerHTML = html;
    if (typeof render当前图谱Diagram === "function" && (graph.nodes || []).length) {
      setTimeout(function() { render当前图谱Diagram(graph, "teacherClass当前图谱Diagram"); }, 200);
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
      var 薄弱 = (s.薄弱_abilities || []).slice(0, 2).join(", ");
      html += '<div class="student-card" data-student-id="' + sid + '" style="padding:12px;border-bottom:1px solid #1e293b;cursor:pointer">';
      html += '<div style="font-weight:600;color:#e2e8f0">' + name + ' (' + sid + ')</div>';
      if (薄弱) html += '<div style="font-size:0.85em;color:#94a3b8">弱项： ' + TeacherUI.escHtml(薄弱) + '</div>';
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
  var detailPane = document.getElementById("teacherStudentDetailPane");
  if (!detailPane) {
    var old = document.getElementById("studentDetail正文");
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
    var 薄弱 = (data.薄弱_abilities || []).slice(0, 5);
    var strong = (data.strong_abilities || []).slice(0, 5);
    var patterns = data.diagnostic_patterns || [];
    var recentEvents = data.recent_events || [];
    var html = '<div class="student-detail"><h3>' + name + ' (' + studentId + ')</h3>';
    html += '<div class="detail-row"><span>状态： <strong>' + TeacherUI.escHtml(String(data.status || "未知")) + '</strong></span></div>';
    if (data.overall_score !== undefined) html += '<div class="detail-row"><span>测评分： <strong>' + data.overall_score + '</strong></span></div>';
    if (data.evidence_count) html += '<div class="detail-row"><span>证据： ' + data.evidence_count + ' events</span></div>';
    if (data.evidence_coverage) html += '<div class="detail-row"><span>覆盖率： ' + Math.round(data.evidence_coverage * 100) + '%</span></div>';
    html += '<hr style="border-color:rgba(255,255,255,0.1);margin:12px 0">';
    if (薄弱.length) html += '<div class="detail-row"><span style="color:#f87171">弱项： ' + 薄弱.map(TeacherUI.escHtml).join(", ") + '</span></div>';
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
    var filters = [["all", "全部"], ["draft", "草稿"], ["reviewed", "审核ed"], ["published", "发布ed"]];
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
        try { evidenceCount = (JSON.parse(cm.evidence_json || "[]")).length; } catch(e) {}
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
    try { evidence = JSON.parse(cm.evidence_json || "[]"); } catch(e) {}
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

// ============================================================
// Tab: Standards
// ============================================================
TeacherUI._standardsView = "graph";

TeacherUI.loadStandards = function() {
  var c = document.getElementById("tw-standards");
  if (!c) return;
  if (!TeacherUI.currentClass) {
    c.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">请先选择班级。</div>';
    return;
  }
  c.innerHTML = '<div class="muted" style="padding:20px">加载岗位标准中...</div>';
  var jobRole = TeacherUI.currentClass.job_role || "";
  Promise.all([
    TeacherUI.fetchAuth("/api/graph/job?job_role=" + encodeURIComponent(jobRole), "GET"),
    TeacherUI.fetchAuth("/api/graph/job/proposals/pending?job_role=" + encodeURIComponent(jobRole), "GET"),
    TeacherUI.fetchAuth("/api/graph/job/versions?job_role=" + encodeURIComponent(jobRole), "GET")
  ]).then(function(results) {
    var graph = results[0] || { nodes: [] };
    var proposalsData = results[1] || {};
    var versionsData = results[2] || {};
    var proposals = proposalsData.proposals || proposalsData.pending_proposals || [];
    var versions = versionsData.versions || [];
    var nodes = graph.nodes || [];
    var html = '<div style="padding:16px"><h3 style="color:#e2e8f0;margin:0 0 8px">岗位标准</h3>';
    html += '<div style="display:flex;gap:8px;margin-bottom:12px">';
    var views = [["graph", "当前图谱"], ["proposals", "更新建议"], ["versions", "版本s"]];
    views.forEach(function(v) {
      var active = TeacherUI._standardsView === v[0] ? "background:#14b8a6;color:#fff" : "background:rgba(255,255,255,0.08)";
      html += '<button style="padding:6px 12px;border-radius:6px;border:none;cursor:pointer;' + active + '" onclick="TeacherUI.setStandardsView(\'' + v[0] + '\')">' + v[1] + '</button>';
    });
    html += '</div>';
    html += '<p style="color:#94a3b8;margin:0 0 8px">' + (graph.job_role || jobRole) + ' · ' + nodes.length + ' nodes · ' + proposals.length + ' proposals · ' + versions.length + ' versions</p>';
    if (TeacherUI._standardsView === "graph") {
      html += '<div id="teacherJob当前图谱Diagram" style="width:100%;height:300px"></div>';
    } else if (TeacherUI._standardsView === "proposals") {
      if (!proposals.length) {
        html += '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">暂无待审核更新建议。</div>';
      } else {
        proposals.forEach(function(p) {
          var ptype = TeacherUI.escHtml(String(p.proposal_type || p.type || "update"));
          var target = TeacherUI.escHtml(String(p.target_ability_id || p.ability_id || p.node_id || "unknown"));
          var source = TeacherUI.escHtml(String(p.source || "unknown"));
          html += '<div class="proposal-card" style="padding:12px;border:1px solid #334155;border-radius:8px;margin-bottom:8px">';
          html += '<div style="font-weight:600;color:#e2e8f0">' + ptype + ': ' + target + '</div>';
          html += '<div style="color:#94a3b8;font-size:0.85em">来源： ' + source + '</div>';
          html += '</div>';
        });
      }
    } else {
      if (!versions.length) {
        html += '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">暂无版本记录。</div>';
      } else {
        versions.forEach(function(v) {
          var vid = TeacherUI.escHtml(String(v.version || v.id || ""));
          var vtime = TeacherUI.escHtml(String(v.created_at || v.timestamp || ""));
          html += '<div class="version-card" style="padding:12px;border:1px solid #334155;border-radius:8px;margin-bottom:8px">';
          html += '<div style="font-weight:600;color:#e2e8f0">版本 ' + vid + '</div>';
          html += '<div style="color:#94a3b8;font-size:0.85em">' + vtime + '</div>';
          html += '</div>';
        });
      }
    }
    html += '</div>';
    c.innerHTML = html;
    if (TeacherUI._standardsView === "graph" && typeof render当前图谱Diagram === "function" && nodes.length) {
      setTimeout(function() { render当前图谱Diagram(graph, "teacherJob当前图谱Diagram"); }, 200);
    }
  }).catch(function() {
    c.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">岗位标准加载失败。</div>';
  });
};

TeacherUI.setStandardsView = function(view) {
  TeacherUI._standardsView = view;
  TeacherUI.loadStandards();
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
