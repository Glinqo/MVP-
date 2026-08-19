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

// ---- Priority helper ----
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

TeacherUI.setCurrentClass = function(cls) {
  TeacherUI.currentClass = cls;
  TeacherUI.currentClassId = cls ? cls.id : null;
  var labelEl = document.getElementById("teacherClassLabel");
  var metaEl = document.getElementById("teacherClassMeta");
  var manageBtn = document.getElementById("manageClassBtn");
  if (cls) {
    if (labelEl) labelEl.textContent = cls.name;
    if (metaEl) metaEl.textContent = (cls.student_count || 0) + " students" + (cls.job_role ? " · " + cls.job_role : "");
    if (manageBtn) manageBtn.style.display = "";
    localStorage.setItem("mcp_teacher_class_id", String(cls.id));
  } else {
    if (labelEl) labelEl.textContent = "No class selected";
    if (metaEl) metaEl.textContent = "";
    if (manageBtn) manageBtn.style.display = "none";
  }
  if (TeacherUI.currentTab) TeacherUI.switchTab(TeacherUI.currentTab);
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
      if (errEl) { errEl.textContent = data.error || "Create failed"; errEl.style.display = "block"; }
    }
  }).catch(function(e) {
    if (errEl) { errEl.textContent = "Create failed: " + e.message; errEl.style.display = "block"; }
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
  if (listEl) listEl.innerHTML = '<div class="muted" style="padding:20px">Loading students...</div>';
  TeacherUI.fetchAuth(url, "GET").then(function(data) {
    TeacherUI._allStudents = data.students || [];
    TeacherUI.renderStudentManageList();
  }).catch(function(e) {
    if (listEl) listEl.innerHTML = '<div style="padding:20px;color:#f87171">Failed to load students.</div>';
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
    if (s.in_current_class) html += '<span class="badge badge-in-class">In class</span>';
    html += '</label>';
  });
  if (!TeacherUI._allStudents.length) {
    html = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">No students found.</div>';
  }
  listEl.innerHTML = html;
  var statusEl = document.getElementById("studentFilterStatus");
  if (statusEl) statusEl.textContent = "Total " + TeacherUI._allStudents.length + ", in class " + inClass;
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
  if (el) el.textContent = "Selected " + TeacherUI._selectedStudents.length + " students";
};

TeacherUI.addSelectedStudents = function() {
  if (!TeacherUI._selectedStudents.length) return;
  TeacherUI.fetchAuth("/api/teacher/classes/" + TeacherUI.currentClassId + "/students", "POST", {
    student_usernames: TeacherUI._selectedStudents.slice()
  }).then(function(data) {
    if (data.ok) {
      alert("Added " + data.added.length + " students" + (data.already_in_class.length ? ", already in class " + data.already_in_class.length : ""));
      TeacherUI._selectedStudents = [];
      TeacherUI.loadAvailableStudents();
      TeacherUI.loadClasses();
    }
  }).catch(function(e) {
    alert("Add failed: " + e.message);
  });
};

TeacherUI.removeSelectedStudents = function() {
  if (!TeacherUI._selectedStudents.length) return;
  TeacherUI.fetchAuth("/api/teacher/classes/" + TeacherUI.currentClassId + "/students/remove", "POST", {
    student_usernames: TeacherUI._selectedStudents.slice()
  }).then(function(data) {
    if (data.ok) {
      alert("Removed " + data.removed.length + " students");
      TeacherUI._selectedStudents = [];
      TeacherUI.loadAvailableStudents();
      TeacherUI.loadClasses();
    }
  }).catch(function(e) {
    alert("Remove failed: " + e.message);
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
      alert("Added " + data.added.length + " students" + (data.not_found.length ? ", not found " + data.not_found.length : ""));
      TeacherUI._batchParsedStudents = [];
      document.getElementById("batchInputArea").style.display = "none";
      TeacherUI.loadAvailableStudents();
      TeacherUI.loadClasses();
    }
  }).catch(function(e) {
    alert("Add failed: " + e.message);
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
  var c = document.getElementById("todayTeachingContent");
  if (!c) return;
  c.innerHTML = '<div class="muted" style="padding:20px">Loading issues...</div>';
  var payload = {};
  if (TeacherUI.currentClassId) payload.class_id = TeacherUI.currentClassId;
  TeacherUI.fetchAuth("/api/v2/teacher/issues", "POST", payload).then(function(data) {
    var issues = data.issues || data || [];
    if (!issues.length) {
      c.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">Not enough evidence to form teaching issues yet.</div>';
      return;
    }
    TeacherUI._issuesCache = issues;
    TeacherUI.renderIssueList(issues, c);
  }).catch(function(e) {
    c.innerHTML = '<div style="padding:20px;color:#f87171">Load failed. <a href="#" onclick="TeacherUI.loadToday();return false">Retry</a></div>';
  });
};

TeacherUI.renderIssueList = function(issues, container) {
  var html = '<div class="issue-list">';
  issues.forEach(function(issue) {
    var pl = TeacherUI.priorityLevel(issue.priority);
    var pc = "badge-priority-" + pl.level;
    var students = issue.affected_students || [];
    var title = TeacherUI.escHtml(issue.title || issue.issue_id || "Unknown");
    html += '<div class="issue-card" data-issue-id="' + issue.issue_id + '">';
    html += '<div class="issue-card-header"><span class="issue-card-title">' + title + '</span></div>';
    html += '<div class="issue-card-meta"><span class="' + pc + '">' + pl.label + '</span><span>' + students.length + ' students</span></div>';
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
        if (bodyEl) bodyEl.innerHTML = '<div style="padding:40px;text-align:center">Issue not found or expired.</div>';
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

  if (titleEl) titleEl.textContent = issue.title || issue.issue_id || "Unknown";

  var html = '<div class="drawer-detail">';
  html += '<div class="detail-row"><span class="label">Priority</span><span class="badge-priority-' + pl.level + '">' + pl.label + '</span></div>';
  html += '<div class="detail-row"><span class="label">Confidence</span><span>' + ((issue.confidence || 0) * 100).toFixed(0) + '%</span></div>';
  html += '<div class="detail-row"><span class="label">Severity</span><span>' + ((issue.severity || 0) * 100).toFixed(0) + '%</span></div>';
  html += '<div class="detail-row"><span class="label">Primary Ability</span><span>' + ability + '</span></div>';
  html += '<div class="detail-row"><span class="label">Affected Students</span><span>' + students.length + '</span></div>';

  if (students.length > 0) {
    html += '<div class="detail-row"><span class="label">Students</span><span>';
    for (var i = 0; i < Math.min(students.length, 5); i++) {
      var sid = String(students[i]);
      html += '<button class="student-chip" data-student="' + sid + '">' + TeacherUI.escHtml(sid) + '</button> ';
    }
    if (students.length > 5) html += '... ' + students.length + ' total';
    html += '</span></div>';
  }

  html += '<div style="margin-top:16px;display:flex;gap:8px">';
  html += '<button class="btn-primary" onclick="TeacherUI.generateCandidates()">Generate Intervention Candidates</button>';
  html += '</div>';
  html += '</div>';

  if (bodyEl) {
    bodyEl.innerHTML = html;
    // Bind student chip clicks
    bodyEl.querySelectorAll(".student-chip").forEach(function(btn) {
      btn.addEventListener("click", function() {
        TeacherUI.switchTab("students");
        setTimeout(function() { TeacherUI.lookupStudent(btn.dataset.student); }, 300);
      });
    });
  }
};

TeacherUI.generateCandidates = function() {
  var drawer = document.getElementById("issueDetailDrawer");
  var bodyEl = drawer ? (drawer.querySelector(".issue-drawer-body") || drawer.querySelector(".issue-drawer-content")) : null;
  if (bodyEl) bodyEl.innerHTML = '<div style="padding:20px">Generating candidates...</div>';

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

  TeacherUI.fetchAuth("/api/v2/teacher/issues/candidates", "POST", {
    issue_id: issueId, student_ids: students.slice(0, 10)
  }).then(function(data) {
    var candidates = data.candidates || data || [];
    var html = '<div class="drawer-detail"><h3 style="margin:0 0 12px;color:#e2e8f0">Intervention Candidates (' + candidates.length + ')</h3>';
    if (!candidates.length) {
      html += '<div style="padding:20px;text-align:center">No candidates available.</div>';
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
    if (bodyEl) bodyEl.innerHTML = '<div style="padding:20px;color:#f87171">Failed to generate candidates</div>';
  });
};

// ============================================================
// Tab: Insights
// ============================================================
TeacherUI.loadInsights = function() {
  var c = document.getElementById("tw-insights");
  if (!c) return;
  c.innerHTML = '<div class="muted" style="padding:20px">Loading insights...</div>';
  var insightUrl = "/api/graph/job";
  if (TeacherUI.currentClassId) insightUrl += (insightUrl.includes("?") ? "&" : "?") + "class_id=" + TeacherUI.currentClassId;
  TeacherUI.fetchAuth(insightUrl, "GET").then(function(data) {
    var nodes = data.nodes || [];
    c.innerHTML = '<div style="padding:16px"><h3 style="color:#e2e8f0;margin:0 0 4px">Job Ability Graph</h3><p style="color:#94a3b8;margin:0">' + nodes.length + ' ability nodes</p><div id="teacherJobGraphDiagram" style="width:100%;height:300px"></div></div>';
    if (typeof renderGraphDiagram === "function" && nodes.length) {
      setTimeout(function() { renderGraphDiagram(data, "teacherJobGraphDiagram"); }, 200);
    }
  }).catch(function() {
    c.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">No insight data available.</div>';
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
  listPane.innerHTML = '<div class="muted" style="padding:20px">Loading student list...</div>';

  TeacherUI.fetchAuth("/api/teacher/students", "POST", {}).then(function(data) {
    var students = data.students || data || [];
    if (!Array.isArray(students)) students = [];
    if (!students.length) {
      listPane.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">No student data.</div>';
      return;
    }
    var html = '<div class="student-list" style="overflow-y:auto;max-height:calc(100vh - 200px)">';
    students.forEach(function(s) {
      var sid = String(s.student_id || s.id || s.username || "");
      var name = TeacherUI.escHtml(String(s.nickname || s.name || sid));
      var weak = (s.weak_abilities || []).slice(0, 2).join(", ");
      html += '<div class="student-card" data-student-id="' + sid + '" style="padding:12px;border-bottom:1px solid #1e293b;cursor:pointer">';
      html += '<div style="font-weight:600;color:#e2e8f0">' + name + ' (' + sid + ')</div>';
      if (weak) html += '<div style="font-size:0.85em;color:#94a3b8">Weak: ' + TeacherUI.escHtml(weak) + '</div>';
      html += '</div>';
    });
    html += '</div>';
    listPane.innerHTML = html;
    listPane.querySelectorAll(".student-card").forEach(function(card) {
      card.addEventListener("click", function() { TeacherUI.lookupStudent(card.dataset.studentId); });
    });
  }).catch(function(e) {
    listPane.innerHTML = '<div style="padding:20px;color:#f87171">Failed to load students.</div>';
  });
};

TeacherUI.lookupStudent = function(studentId) {
  var detailPane = document.getElementById("teacherStudentDetailPane");
  if (!detailPane) {
    var old = document.getElementById("studentDetailContent");
    if (old) old.innerHTML = '<div style="padding:20px">Loading student ' + studentId + ' ...</div>';
    if (typeof fetchStudentDetail === "function") { fetchStudentDetail(studentId); return; }
    if (typeof loadStudentDetail === "function") { loadStudentDetail(studentId); return; }
    return;
  }
  detailPane.style.display = "block";
  detailPane.innerHTML = '<div style="padding:20px">Loading student detail...</div>';
  var jobId = localStorage.getItem("mcp_job_id") || "";
  TeacherUI.fetchAuth("/api/teacher/students/detail", "POST", {
    student_id: studentId, job_role: jobId
  }).then(function(data) {
    if (data.error) {
      detailPane.innerHTML = '<div style="padding:20px;color:#f87171">No data for student ' + studentId + '</div>';
      return;
    }
    var name = TeacherUI.escHtml(String(data.nickname || studentId));
    var weak = (data.weak_abilities || []).slice(0, 5);
    var strong = (data.strong_abilities || []).slice(0, 5);
    var html = '<div class="student-detail"><h3>' + name + ' (' + studentId + ')</h3>';
    if (data.status) html += '<div class="detail-row"><span>Status: ' + data.status + '</span></div>';
    if (data.assess_score !== undefined) html += '<div class="detail-row"><span>Assessment Score: ' + data.assess_score + '</span></div>';
    if (weak.length) html += '<div class="detail-row"><span>Weak: ' + weak.join(", ") + '</span></div>';
    if (strong.length) html += '<div class="detail-row"><span>Strong: ' + strong.join(", ") + '</span></div>';
    html += '</div>';
    detailPane.innerHTML = html;
  }).catch(function(e) {
    detailPane.innerHTML = '<div style="padding:20px;color:#f87171">Failed to load student detail</div>';
  });
};

// ============================================================
// Tab: Feedback
// ============================================================
TeacherUI.loadFeedback = function() {
  var c = document.getElementById("tw-feedback");
  if (!c) return;
  c.innerHTML = '<div class="muted" style="padding:20px">Loading feedback...</div>';
  TeacherUI.fetchAuth("/api/teacher/comments", "GET").then(function(data) {
    var stats = data.stats || {};
    var html = '<div style="padding:16px"><h3 style="color:#e2e8f0;margin:0 0 12px">Teaching Feedback</h3>';
    html += '<div style="display:flex;gap:12px;margin-bottom:12px">';
    html += '<span class="badge">Draft: ' + (stats.draft || 0) + '</span>';
    html += '<span class="badge">Reviewed: ' + (stats.reviewed || 0) + '</span>';
    html += '<span class="badge">Published: ' + (stats.published || 0) + '</span>';
    html += '</div>';
    html += '</div>';
    c.innerHTML = html;
  }).catch(function() {
    c.innerHTML = '<div style="padding:20px;color:rgba(255,255,255,0.4)">No feedback data.</div>';
  });
};

// ============================================================
// Tab: Standards
// ============================================================
TeacherUI.loadStandards = function() {
  var c = document.getElementById("tw-standards");
  if (!c) return;
  c.innerHTML = '<div class="muted" style="padding:20px">Loading standards...</div>';
  var jobId = localStorage.getItem("mcp_job_id") || "";
  TeacherUI.fetchAuth("/api/graph/job" + (jobId ? "?job_role=" + encodeURIComponent(jobId) : ""), "GET").then(function(data) {
    var nodes = data.nodes || [];
    var proposals = data.pending_proposals || [];
    var html = '<div style="padding:16px"><h3 style="color:#e2e8f0;margin:0 0 8px">Job Standards</h3>';
    html += '<p style="color:#94a3b8;margin:0 0 8px">Current job: ' + (data.job_role || jobId) + ' | ' + nodes.length + ' nodes</p>';
    if (proposals.length > 0) html += '<p style="color:#fbbf24;margin:0 0 8px">Pending proposals: ' + proposals.length + '</p>';
    html += '<div id="teacherJobGraphDiagram" style="width:100%;height:300px"></div>';
    html += '</div>';
    c.innerHTML = html;
    if (typeof renderGraphDiagram === "function" && nodes.length) {
      setTimeout(function() { renderGraphDiagram(data, "teacherJobGraphDiagram"); }, 200);
    }
  }).catch(function() {
    c.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">No standards data.</div>';
  });
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
  TeacherUI.messages.push({ role: "loading", content: "Analyzing..." });
  TeacherUI.renderMessages();

  var token = localStorage.getItem("mcp_auth_token") || "";
  var jobRole = localStorage.getItem("mcp_job_id") || "";
  fetch("/api/teacher/assistant/message", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
    body: JSON.stringify({ message: msg, job_role: jobRole })
  }).then(function(r) { return r.json(); })
  .then(function(data) {
    TeacherUI.messages.pop();
    TeacherUI.messages.push({ role: "assistant", content: data.answer || data.reply || data.message || "Response received" });
    TeacherUI.renderMessages();
  }).catch(function(e) {
    TeacherUI.messages.pop();
    TeacherUI.messages.push({ role: "error", content: "Error: " + (e.message || "Network error") });
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
