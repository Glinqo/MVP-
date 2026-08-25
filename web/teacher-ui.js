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

TeacherUI.showToast = function(message, type) {
  var toastRoot = document.getElementById("teacherToastRoot");
  if (!toastRoot) {
    toastRoot = document.createElement("div");
    toastRoot.id = "teacherToastRoot";
    document.body.appendChild(toastRoot);
  }
  var toast = document.createElement("div");
  toast.className = "teacher-toast teacher-toast-" + (type || "info");
  toast.textContent = message || "";
  toastRoot.appendChild(toast);
  setTimeout(function() { toast.classList.add("show"); }, 20);
  setTimeout(function() {
    toast.classList.remove("show");
    setTimeout(function() { toast.remove(); }, 250);
  }, 2600);
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
  if (isNaN(p)) return { level: "low", label: "一般关注", score: null };
  if (p >= 0.7) return { level: "high", label: "优先处理", score: p };
  if (p >= 0.4) return { level: "medium", label: "建议关注", score: p };
  return { level: "low", label: "一般关注", score: p };
};

TeacherUI.abilityLabel = function(id) {
  if (!id) return "";
  var labels = {
    sn_type_identify: "传感器类型识别",
    sn_wiring_rules: "传感器接线规则",
    sn_signal_acq: "传感器信号采集",
    sn_fault_diag: "传感器故障诊断",
    pl_program_monitor: "PLC 程序监控",
    pl_io_mapping: "PLC I/O 映射",
    pl_logic_control: "PLC 逻辑控制",
    pl_fault_diag: "PLC 故障诊断",
    electrical_safety_check: "电气安全检查",
    power_isolation_confirmation: "断电隔离确认",
    sensor_output_logic: "传感器输出逻辑",
    plc_input_common_terminal: "PLC 输入公共端",
    plc_input_grouping: "PLC 输入分组",
    input_led_compare: "输入灯对照",
    io_mapping_table_build: "I/O 映射表建立",
    no_response_power_path_check: "无响应电源路径检查",
    no_response_sensor_side_check: "无响应传感器侧检查",
    no_response_common_terminal_check: "无响应公共端检查",
    no_response_address_mapping_check: "无响应地址映射检查",
    ir_01: "机器人基本操作",
    ir_02: "示教器点动",
    ir_03: "坐标系认知",
    ir_04: "安全围栏",
    ir_05: "急停确认",
    ir_06: "机器人 I/O 通信基础",
    ir_07: "机器人 I/O 映射",
    ir_08: "输入输出监控",
    ir_09: "通信状态判断",
    ir_10: "总线诊断",
    ir_11: "工作站安全",
    ir_12: "安全门联锁",
    ir_13: "安全回路",
    ir_14: "手眼标定",
    ir_15: "标定安全",
    ir_16: "机器人零点校准",
    ir_17: "转数计数器",
    ir_18: "TCP 标定",
    ir_19: "工具坐标",
    ir_20: "弧焊断丝检测",
  };
  if (labels[id]) return labels[id];
  var node = null;
  var jobGraph = (window.state && window.state.graphs && window.state.graphs.job) || {};
  (jobGraph.nodes || []).forEach(function(item) {
    if (item.id === id) node = item;
  });
  if (!node && window.state && window.state.graphs && window.state.graphs.student) {
    (window.state.graphs.student.nodes || []).forEach(function(item) {
      if (item.id === id) node = item;
    });
  }
  return (node && (node.label || node.name || node.ability_name)) || id;
};

TeacherUI.humanizeIssueTitle = function(issue) {
  var text = issue ? (issue.title || issue.issue_id || "") : "";
  if (!text) return text;
  var ids = [];
  if (issue.primary_ability_id) ids.push(issue.primary_ability_id);
  if (Array.isArray(issue.ability_ids)) ids = ids.concat(issue.ability_ids);
  ids.forEach(function(id) {
    if (!id) return;
    text = text.split(String(id)).join(TeacherUI.abilityLabel(id));
  });
  return text;
};

TeacherUI.jobRoleLabel = function(id) {
  if (!id) return "";
  var labels = {
    automation_line_commissioning_maintenance_newcomer: "自动化生产线装调与运维技术员",
    industrial_robot_maintenance: "工业机器人系统运维员",
    mechanical_electrical_maintenance_worker: "机电设备维护工"
  };
  if (labels[id]) return labels[id];
  return id;
};

TeacherUI.commentStatusLabel = function(status) {
  return {
    draft: "草稿",
    reviewed: "待发布",
    published: "已发布"
  }[status] || "草稿";
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
    TeacherUI.setCurrentClass(selected, false);
    TeacherUI.renderClassDropdown();
    TeacherUI.switchTab(TeacherUI.currentTab || "today");
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

TeacherUI.syncJobGraphRole = function() {
  var input = document.getElementById("jobAdminRole");
  if (!input) return;
  var roleId = TeacherUI.currentClass ? (TeacherUI.currentClass.job_role || "") : "";
  if (!roleId && typeof window !== "undefined" && typeof window.DEFAULT_JOB_ROLE_ID !== "undefined") {
    roleId = window.DEFAULT_JOB_ROLE_ID;
  }
  input.value = TeacherUI.jobRoleLabel(roleId);
  input.dataset.jobRoleId = roleId;
};

TeacherUI.setCurrentClass = function(cls, shouldRender) {
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
  if (scopeEl) scopeEl.textContent = cls ? "当前范围：" + cls.name + (cls.job_role ? " · " + TeacherUI.jobRoleLabel(cls.job_role) : "") : "未选择班级";
  var labelEl = document.getElementById("teacherClassLabel");
  var metaEl = document.getElementById("teacherClassMeta");
  var manageBtn = document.getElementById("manageClassBtn");
  if (cls) {
    if (labelEl) { labelEl.textContent = cls.name; labelEl.style.cursor = "pointer"; labelEl.onclick = function() { TeacherUI.toggleClassDropdown(); }; }
    if (metaEl) metaEl.textContent = (cls.student_count || 0) + " 人" + (cls.job_role ? " · " + TeacherUI.jobRoleLabel(cls.job_role) : "");
    if (manageBtn) manageBtn.style.display = "";
    localStorage.setItem("mcp_teacher_class_id", String(cls.id));
  } else {
    if (labelEl) labelEl.textContent = "未选择班级";
    if (metaEl) metaEl.textContent = "";
    if (manageBtn) manageBtn.style.display = "none";
  }
  TeacherUI.syncJobGraphRole();
  if (shouldRender !== false && TeacherUI.currentTab) TeacherUI.switchTab(TeacherUI.currentTab);
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
    html += '<span class="class-dropdown-meta">' + (cls.student_count || 0) + ' 人' + (cls.job_role ? " · " + TeacherUI.escHtml(TeacherUI.jobRoleLabel(cls.job_role)) : "") + '</span>';
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
  var rows = [];
  TeacherUI._allStudents.forEach(function(s) {
    var sid = String(s.username || "");
    var name = TeacherUI.escHtml(String(s.nickname || sid));
    var checked = selectedSet.has(sid) ? " checked" : "";
    if (s.in_current_class) inClass++;
    var row = '<label class="student-manage-row">';
    row += '<input type="checkbox" class="student-manage-check" data-username="' + sid + '"' + checked + '>';
    row += '<span class="student-manage-name">' + name + ' (' + sid + ')</span>';
    if (s.in_current_class) row += '<span class="badge badge-in-class">已在本班</span>';
    row += '</label>';
    rows.push({ row: row, inClass: Boolean(s.in_current_class) });
  });
  if (!TeacherUI._allStudents.length) {
    html = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">未找到学生。</div>';
  } else {
    var inClassRows = rows.filter(function(r) { return r.inClass; });
    var availableRows = rows.filter(function(r) { return !r.inClass; });
    if (inClassRows.length) {
      html += '<div class="student-manage-group-title">本班学生 <span>' + inClassRows.length + '</span></div>';
      html += inClassRows.map(function(r) { return r.row; }).join("");
    }
    if (availableRows.length) {
      html += '<div class="student-manage-group-title">可加入学生 <span>' + availableRows.length + '</span></div>';
      html += availableRows.map(function(r) { return r.row; }).join("");
    }
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
  var selectedSet = new Set(TeacherUI._selectedStudents);
  var inClassSelected = 0;
  TeacherUI._allStudents.forEach(function(s) {
    if (selectedSet.has(String(s.username || "")) && s.in_current_class) inClassSelected++;
  });
  var availableSelected = TeacherUI._selectedStudents.length - inClassSelected;
  var removeBtn = document.getElementById("removeSelectedStudentsBtn");
  var addBtn = document.getElementById("addSelectedStudentsBtn");
  if (removeBtn && addBtn) {
    removeBtn.classList.toggle("btn-primary", inClassSelected > 0 && availableSelected === 0);
    removeBtn.classList.toggle("btn-danger", !(inClassSelected > 0 && availableSelected === 0));
    addBtn.classList.toggle("btn-primary", availableSelected > 0 && inClassSelected === 0);
    addBtn.classList.toggle("btn-secondary", !(availableSelected > 0 && inClassSelected === 0));
  }
};

TeacherUI.addSelectedStudents = function() {
  if (!TeacherUI._selectedStudents.length) return;
  TeacherUI.fetchAuth("/api/teacher/classes/" + TeacherUI.currentClassId + "/students", "POST", {
    student_usernames: TeacherUI._selectedStudents.slice()
  }).then(function(data) {
    if (data.ok) {
      TeacherUI.showToast("已加入 " + data.added.length + " 名学生", "success");
      TeacherUI._selectedStudents = [];
      TeacherUI.loadAvailableStudents();
      TeacherUI.loadClasses();
    }
  }).catch(function(e) {
    TeacherUI.showToast("加入失败，请重试", "error");
  });
};

TeacherUI.removeSelectedStudents = function() {
  if (!TeacherUI._selectedStudents.length) return;
  TeacherUI.fetchAuth("/api/teacher/classes/" + TeacherUI.currentClassId + "/students/remove", "POST", {
    student_usernames: TeacherUI._selectedStudents.slice()
  }).then(function(data) {
    if (data.ok) {
      TeacherUI.showToast("已移除 " + data.removed.length + " 名学生", "success");
      TeacherUI._selectedStudents = [];
      TeacherUI.loadAvailableStudents();
      TeacherUI.loadClasses();
    }
  }).catch(function(e) {
    TeacherUI.showToast("移除失败，请重试", "error");
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
  var html = '<div><strong>解析结果</strong></div>';
  html += '<div>已识别 ' + found.length + ' 名学生</div>';
  if (notFound.length) html += '<div style="color:#f87171">未找到： ' + notFound.join(", ") + '</div>';
  if (found.length) html += '<div style="margin-top:8px"><button class="btn-primary" onclick="TeacherUI.addBatchStudents()">加入 ' + found.length + ' 名学生</button></div>';
  resultEl.innerHTML = html;
};

TeacherUI.addBatchStudents = function() {
  if (!TeacherUI._batchParsedStudents.length) return;
  TeacherUI.fetchAuth("/api/teacher/classes/" + TeacherUI.currentClassId + "/students", "POST", {
    student_usernames: TeacherUI._batchParsedStudents.slice()
  }).then(function(data) {
    if (data.ok) {
      TeacherUI.showToast("已加入 " + data.added.length + " 名学生", "success");
      TeacherUI._batchParsedStudents = [];
      document.getElementById("batchInputArea").style.display = "none";
      TeacherUI.loadAvailableStudents();
      TeacherUI.loadClasses();
    }
  }).catch(function(e) {
    TeacherUI.showToast("加入失败，请重试", "error");
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
  c.innerHTML = '<div class="teacher-empty-state">正在加载教学问题…</div>';
  var payload = {};
  if (TeacherUI.currentClassId) payload.class_id = TeacherUI.currentClassId;
  TeacherUI.fetchAuth("/api/v2/teacher/issues", "POST", payload).then(function(data) {
    var issues = data.issues || data || [];
    if (!issues.length) {
      c.innerHTML = '<div class="teacher-empty-state"><strong>暂无需要处理的教学问题</strong><div>学生产生更多学习记录后，这里会自动汇总。</div></div>';
      return;
    }
    TeacherUI._issuesCache = issues;
    TeacherUI.renderIssueList(issues, c);
    TeacherUI.renderTodaySuggestion(issues);
  }).catch(function(e) {
    c.innerHTML = '<div class="teacher-error-state">加载失败，请重试 <button class="btn-secondary" onclick="TeacherUI.loadToday()">重新加载</button></div>';
  });
};

TeacherUI.renderIssueList = function(issues, container) {
  var html = '<div class="issue-list">';
  issues.forEach(function(issue) {
    var pl = TeacherUI.priorityLevel(issue.priority);
    var pc = "badge-priority-" + pl.level;
    var students = issue.affected_students || [];
    var title = TeacherUI.escHtml(TeacherUI.humanizeIssueTitle(issue));
    var ability = TeacherUI.abilityLabel(issue.primary_ability_id || "");
    html += '<div class="issue-card" data-issue-id="' + issue.issue_id + '">';
    html += '<div class="issue-card-header"><span class="' + pc + '">' + pl.label + '</span><span class="issue-card-arrow">查看详情 →</span></div>';
    html += '<div class="issue-card-title">' + title + '</div>';
    html += '<div class="issue-card-meta"><span>' + students.length + ' 名学生受到影响</span>';
    if (ability) html += '<span>主要能力：' + TeacherUI.escHtml(ability) + '</span>';
    html += '</div>';
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
  if (titleEl) titleEl.textContent = "正在加载…";
  if (bodyEl) bodyEl.innerHTML = '<div class="teacher-empty-state">正在加载教学问题详情…</div>';

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
        if (titleEl) titleEl.textContent = "未找到";
        if (bodyEl) bodyEl.innerHTML = '<div class="teacher-empty-state">未找到该教学问题。</div>';
      }
    }).catch(function() {
      if (titleEl) titleEl.textContent = "加载失败";
      if (bodyEl) bodyEl.innerHTML = '<div class="teacher-error-state">加载失败，请重试</div>';
    });
  }
};

TeacherUI.renderIssueDetail = function(issue, drawer) {
  var titleEl = drawer.querySelector(".issue-drawer-title");
  var bodyEl = drawer.querySelector(".issue-drawer-body") || drawer.querySelector(".issue-drawer-content");
  var pl = TeacherUI.priorityLevel(issue.priority);
  var students = issue.affected_students || [];
  var ability = TeacherUI.escHtml(TeacherUI.abilityLabel(issue.primary_ability_id || ""));
  TeacherUI.updateAIContext({
    current_issue_id: issue.issue_id || TeacherUI.currentIssueId || "",
    current_issue_title: issue.title || issue.issue_id || "",
    current_student_ids: (issue.affected_students || []).slice(),
    current_ability_id: issue.primary_ability_id || null
  });

  if (titleEl) titleEl.textContent = TeacherUI.humanizeIssueTitle(issue);

  var html = '<div class="drawer-detail">';
  html += '<div class="issue-summary">' + TeacherUI.escHtml(TeacherUI.humanizeIssueTitle(issue)) + '</div>';
  html += '<div class="detail-row"><span class="label">问题结论</span><span>学生在“' + ability + '”上存在共性薄弱，建议优先干预。</span></div>';
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
  if (topPatterns.length) {
    html += '<div class="detail-row" style="margin-top:8px"><strong>学生具体错在哪里</strong></div>';
    topPatterns.forEach(function(p) {
      html += '<div class="detail-row" style="color:#fbbf24">- ' + TeacherUI.escHtml(p.label || "unknown") + ' x' + p.count + ' · ' + p.student_count + ' 人</div>';
    });
  } else {
    html += '<div class="detail-row" style="color:#94a3b8">暂无更细的重复过程证据。</div>';
  }
  html += '<details class="analysis-details"><summary>为什么系统这么判断</summary>';
  html += '<div class="detail-row"><span class="label">为什么系统这么判断</span><span>' + TeacherUI.escHtml(evidence.student_count || students.length || 0) + ' 名学生出现相关证据，共 ' + TeacherUI.escHtml(evidence.event_count || 0) + ' 条学习事件。</span></div>';
  html += '<div class="detail-row"><span class="label">优先级</span><span class="badge-priority-' + pl.level + '">' + pl.label + (pl.score !== null ? ' ' + pl.score.toFixed(2) : '') + '</span></div>';
  html += '<div class="detail-row"><span class="label">置信度</span><span>' + ((issue.confidence || 0) * 100).toFixed(0) + '%</span></div>';
  html += '<div class="detail-row"><span class="label">严重程度</span><span>' + ((issue.severity || 0) * 100).toFixed(0) + '%</span></div>';
  if (issue.primary_ability_id) html += '<div class="detail-row"><span class="label">原始能力ID</span><span>' + TeacherUI.escHtml(issue.primary_ability_id) + '</span></div>';
  html += '</details>';
  html += '<div style="margin-top:16px;display:flex;gap:8px">';
  html += '<button class="btn-secondary" onclick="TeacherUI.askIssueWhy()">AI 分析原因</button>';
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
  var title = TeacherUI.humanizeIssueTitle(top);
  var topIssueId = top.issue_id || "";
  var students = (top.affected_students || []).length;
  var buttons = [
    { label: "查看问题", type: "detail" },
    { label: "AI 分析原因", type: "ask", question: "为什么？" },
    { label: "生成今日教学建议", type: "ask", question: "生成教学方案" }
  ];
  sq.innerHTML = '<div class="suggestion-label">' + TeacherUI.escHtml(title) + '，影响 ' + students + ' 人</div>' +
    buttons.map(function(q) {
      return '<button type="button" data-teacher-suggestion-type="' + TeacherUI.escHtml(q.type) + '" data-teacher-suggestion="' + TeacherUI.escHtml(q.question || "") + '" data-issue-id="' + TeacherUI.escHtml(topIssueId) + '">' + TeacherUI.escHtml(q.label) + '</button>';
    }).join("");
  sq.querySelectorAll("[data-teacher-suggestion]").forEach(function(btn) {
    btn.addEventListener("click", function() {
      if (btn.dataset.teacherSuggestionType === "detail") {
        TeacherUI.openIssueDetail(btn.dataset.issueId);
        return;
      }
      var input = document.getElementById("chatInput");
      if (input) input.value = btn.dataset.teacherSuggestion || "";
      if (typeof sendChat === "function") sendChat(btn.dataset.teacherSuggestion || "");
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
    if (typeof sendChat === "function") sendChat("为什么？");
  }
};

TeacherUI.generateCandidates = function() {
  var drawer = document.getElementById("issueDetailDrawer");
  var bodyEl = drawer ? (drawer.querySelector(".issue-drawer-body") || drawer.querySelector(".issue-drawer-content")) : null;
  if (bodyEl) bodyEl.innerHTML = '<div class="teacher-empty-state">正在生成教学方案…</div>';

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
      html += '<div class="teacher-empty-state">暂无可用教学方案。</div>';
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
            input.value = "我想调整这个方案，例如修改时长、教学方式或重点学生。";
            input.focus();
          }
        });
      }
    });
  }).catch(function(e) {
    if (bodyEl) bodyEl.innerHTML = '<div class="teacher-error-state">加载失败，请重试</div>';
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
    objective: "强化当前教学问题对应的能力。",
    method: "教师示范 + 学生实操 + 分组检查",
    target_students: targetStudents.slice(),
    focus_students: [],
    ability_ids: abilityIds.slice(),
    resources: ["根据当前课程与实训设备准备"],
    steps: ["5分钟：教师示范并说明判断依据", "10分钟：学生独立实操", "5分钟：分组检查并纠错"],
    verification: "学生独立完成一次对应能力操作或判断。",
    why: c.description || "该方案直接针对当前问题对应的能力，适合短时间课堂干预。",
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
  html += '<div class="candidate-actions"><button type="button" class="btn-primary candidate-adopt" data-candidate-id="' + cid + '">查看方案</button>';
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
  html += '<button type="button" class="btn-primary" onclick="TeacherUI.confirmIntervention()">采用此方案</button>';
  html += '<button type="button" class="btn-secondary" onclick="TeacherUI.modifyInterventionFromPreview()">让 AI 调整</button>';
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
    input.value = "我想调整这个方案，例如修改时长、教学方式或重点学生。";
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
  var pending = TeacherUI._pendingIntervention || {};
  var plan = pending.plan || TeacherUI.aiContext.current_intervention_draft || {};
  var studentIds = pending.student_ids || plan.target_students || [];
  var duration = plan.duration_minutes || 20;
  if (titleEl) titleEl.textContent = "方案已保存";
  var html = '<div class="intervention-created">';
  html += '<div class="intervention-created-title">' + TeacherUI.escHtml(plan.title || "教学干预方案") + '</div>';
  html += '<div class="teacher-metric-row">' + studentIds.length + ' 名学生 · ' + duration + ' 分钟</div>';
  html += '<div class="intervention-flow" aria-label="方案状态流程">';
  html += '<span class="intervention-flow-step active">方案草稿</span><span class="intervention-flow-sep">○</span><span class="intervention-flow-step">待执行</span><span class="intervention-flow-sep">○</span><span class="intervention-flow-step">已完成</span><span class="intervention-flow-sep">○</span><span class="intervention-flow-step">已评估</span>';
  html += '</div>';
  html += '<div class="detail-row"><span class="label">当前状态</span><span>方案草稿</span></div>';
  html += '<div class="detail-row"><span class="label">适用学生</span><span>' + TeacherUI.escHtml(studentIds.join("、") || "无") + '</span></div>';
  html += '<div class="detail-row"><span class="label">说明</span><span>方案已保存，教师确认后即可用于教学。</span></div>';
  html += '<div style="margin-top:16px;display:flex;gap:8px">';
  html += '<button type="button" class="btn-primary" onclick="TeacherUI.confirmInterventionStatus()">确认用于教学</button>';
  html += '<button type="button" class="btn-secondary" onclick="TeacherUI.openInterventionDetail(\'' + TeacherUI.escHtml(data.intervention_id) + '\')">查看技术信息</button>';
  html += '</div></div>';
  if (bodyEl) bodyEl.innerHTML = html;
};

TeacherUI.confirmInterventionStatus = function() {
  var interventionId = TeacherUI.aiContext.current_intervention_id;
  if (!interventionId) return;
  TeacherUI.fetchAuth("/api/v2/teacher/interventions/" + encodeURIComponent(interventionId) + "/confirm", "POST", {}).then(function(data) {
    if (!data.ok) throw new Error(data.error || "确认失败");
    TeacherUI.showToast("方案已确认", "success");
    TeacherUI.renderInterventionStatus({ intervention_id: interventionId, status: "planned", plan_snapshot: TeacherUI.aiContext.current_intervention_draft || {} });
  }).catch(function(e) {
    TeacherUI.showToast("确认失败，请重试", "error");
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
  var label = { draft: "方案草稿", planned: "已确认 · 待执行", reviewed: "待发布", assigned: "已分配", in_progress: "执行中", completed: "已完成", evaluated: "已评估" }[status] || status;
  if (titleEl) titleEl.textContent = "方案状态";
  var plan = data.plan_snapshot || TeacherUI.aiContext.current_intervention_draft || {};
  var html = '<div class="intervention-status">';
  html += '<div class="detail-row"><span class="label">方案名称</span><span>' + TeacherUI.escHtml(plan.title || "教学干预方案") + '</span></div>';
  html += '<div class="detail-row"><span class="label">状态</span><span class="teacher-status-badge">' + TeacherUI.escHtml(label) + '</span></div>';
  html += '<div class="detail-row"><span class="label">建议用时</span><span>' + TeacherUI.escHtml(String(plan.duration_minutes || 20)) + ' 分钟</span></div>';
  html += '<div class="detail-row"><span class="label">适用学生</span><span>' + TeacherUI.escHtml((plan.target_students || []).join("、") || "无") + '</span></div>';
  html += '<details class="analysis-details"><summary>查看技术信息</summary>';
  html += '<div class="detail-row"><span class="label">Intervention ID</span><span>' + TeacherUI.escHtml(data.intervention_id || "") + '</span></div>';
  html += '<div class="detail-row"><span class="label">Candidate ID</span><span>' + TeacherUI.escHtml(plan.candidate_id || "") + '</span></div>';
  html += '<div class="detail-row"><span class="label">Issue ID</span><span>' + TeacherUI.escHtml(plan.issue_id || "") + '</span></div>';
  html += '</details>';
  if (status === "draft") {
    html += '<div style="margin-top:16px;display:flex;gap:8px"><button class="btn-primary" onclick="TeacherUI.confirmInterventionStatus()">确认用于教学</button></div>';
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
    c.innerHTML = '<div class="teacher-empty-state">当前班级暂无学生，先添加学生后即可查看班级学情。</div>';
    return;
  }
  c.innerHTML = '<div class="teacher-empty-state">正在加载班级洞察…</div>';
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
    var risk = overview.risk_distribution || {};
    var attention = Number(risk.high || 0) + Number(risk.attention || 0);
    var html = '<div class="teacher-section">';
    html += '<div class="teacher-section-title">班级整体情况</div>';
    html += '<div class="teacher-summary-card">' + TeacherUI.escHtml(String(overview.total_students || 0)) + ' 名学生中，' + attention + ' 人当前需要重点关注</div>';
    html += '<div class="teacher-metric-row">证据覆盖 ' + Math.round((overview.evidence_coverage || 0) * 100) + '% · 共性问题 ' + issueList.length + ' 个</div>';
    var weakest = overview.weakest_abilities || [];
    if (weakest.length) {
      html += '<div class="teacher-section-title">最需要补强的能力</div>';
      weakest.forEach(function(w, idx) {
        var masteryPct = Math.round((w.mean_mastery || 0) * 100);
        var ratioPct = Math.round((w.weak_ratio || 0) * 100);
        var abilityId = w.ability_id || w.id || "";
        var label = TeacherUI.abilityLabel(abilityId) || w.label || w.ability_id;
        html += '<div class="insight-ability-row teacher-list-card" data-ability-id="' + TeacherUI.escHtml(abilityId) + '">';
        html += '<div class="teacher-list-card-head">';
        html += '<strong>' + TeacherUI.escHtml(label) + '</strong>';
        html += '<span class="teacher-risk-text">' + (w.weak_student_count || 0) + '人薄弱 · ' + ratioPct + '%</span>';
        html += '</div>';
        html += '<div class="teacher-metric-row">薄弱比例 <strong class="teacher-risk-text">' + ratioPct + '%</strong></div>';
        html += '<div class="teacher-progress teacher-progress-risk"><div class="teacher-progress-fill-risk" style="width:' + ratioPct + '%"></div></div>';
        html += '<div class="teacher-metric-row">平均掌握度 ' + masteryPct + '%</div>';
        html += '<div class="teacher-progress"><div class="teacher-progress-fill" style="width:' + masteryPct + '%"></div></div>';
        html += '<div class="teacher-action-row"><button type="button" class="btn-secondary btn-small" data-ability-action="detail">查看详情</button></div>';
        html += '</div>';
      });
    } else {
      html += '<div class="teacher-empty-state">暂无足够能力数据。</div>';
    }
    html += '<div id="teacherClassGraphDiagram" style="width:100%;height:300px"></div>';
    html += '<div id="teacherInsightAbilityDetail"></div>';
    html += '</div>';
    c.innerHTML = html;
    c.querySelectorAll(".insight-ability-row").forEach(function(row) {
      row.addEventListener("click", function(ev) {
        if (ev.target.closest("button")) return;
        TeacherUI.openInsightAbility(row.dataset.abilityId || "");
      });
    });
    c.querySelectorAll("[data-ability-action]").forEach(function(btn) {
      btn.addEventListener("click", function() {
        TeacherUI.openInsightAbility(btn.closest(".insight-ability-row")?.dataset.abilityId || "");
      });
    });
    if (typeof renderGraphDiagram === "function" && (graph.nodes || []).length) {
      setTimeout(function() { renderGraphDiagram(graph, "teacherClassGraphDiagram"); }, 200);
    }
  }).catch(function() {
    c.innerHTML = '<div class="teacher-error-state">加载失败，请重试 <button class="btn-secondary" onclick="TeacherUI.loadInsights()">重新加载</button></div>';
  });
};

TeacherUI.openInsightAbility = function(abilityId) {
  if (!abilityId) return;
  TeacherUI.updateAIContext({ current_ability_id: abilityId });
  var detail = document.getElementById("teacherInsightAbilityDetail");
  if (!detail) return;
  var label = TeacherUI.abilityLabel(abilityId);
  detail.innerHTML = '<div class="teacher-detail-group"><div class="teacher-section-title">' + TeacherUI.escHtml(label) + '</div>' +
    '<div class="teacher-action-row">' +
    '<button class="btn-secondary" onclick="TeacherUI.askAbility(\'解释这个能力为什么薄弱\')">AI 分析原因</button>' +
    '<button class="btn-secondary" onclick="TeacherUI.askAbility(\'查看受影响学生\')">查看学生</button>' +
    '<button class="btn-secondary" onclick="TeacherUI.askAbility(\'生成分组教学\')">生成分组教学</button>' +
    '</div></div>';
};

// ============================================================
// Tab: Students
// ============================================================
TeacherUI.loadStudents = function() {
  var c = document.getElementById("tw-students");
  if (!c) return;
  c.innerHTML = '<div class="teacher-students-layout"><div id="teacherStudentListPane" style="flex:1;overflow-y:auto"></div><div id="teacherStudentDetailPane" style="flex:1;overflow-y:auto;border-left:1px solid #334155;padding:16px;display:none"></div></div>';
  var listPane = document.getElementById("teacherStudentListPane");
  listPane.innerHTML = '<div class="teacher-empty-state">正在加载学生…</div>';

  if (!TeacherUI.currentClassId) {
    listPane.innerHTML = '<div class="teacher-empty-state">请先选择班级。</div>';
    return;
  }
  TeacherUI.fetchAuth("/api/teacher/classes/" + TeacherUI.currentClassId + "/students", "GET").then(function(data) {
    var students = data.students || [];
    if (!Array.isArray(students)) students = [];
    if (!students.length) {
      listPane.innerHTML = '<div class="teacher-empty-state"><strong>当前班级暂无学生</strong><div>先添加学生后即可查看班级学情。</div></div>';
      return;
    }
    var html = '<div class="student-list" style="overflow-y:auto;max-height:calc(100vh - 200px)">';
    students.forEach(function(s) {
      var sid = String(s.student_id || s.id || s.username || "");
      var name = TeacherUI.escHtml(String(s.nickname || s.name || sid));
      var weak = (s.weak_abilities || []).slice(0, 2).map(TeacherUI.abilityLabel).join(", ");
      html += '<div class="student-card teacher-list-card" data-student-id="' + sid + '">';
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
    listPane.innerHTML = '<div class="teacher-error-state">加载失败，请重试 <button class="btn-secondary" onclick="TeacherUI.loadStudents()">重新加载</button></div>';
  });
};

TeacherUI.lookupStudent = function(studentId) {
  TeacherUI.updateAIContext({ current_student_id: String(studentId || "") });
  document.querySelectorAll(".student-card").forEach(function(card) {
    card.classList.toggle("active", card.dataset.studentId === String(studentId));
  });
  var detailPane = document.getElementById("teacherStudentDetailPane");
  if (!detailPane) {
    var old = document.getElementById("studentDetailContent");
    if (old) old.innerHTML = '<div style="padding:20px">正在加载学生详情…</div>';
    if (typeof fetchStudentDetail === "function") { fetchStudentDetail(studentId); return; }
    if (typeof loadStudentDetail === "function") { loadStudentDetail(studentId); return; }
    return;
  }
  detailPane.style.display = "block";
  detailPane.innerHTML = '<div class="teacher-empty-state">正在加载学生详情…</div>';
  var jobId = TeacherUI.currentClass ? TeacherUI.currentClass.job_role : "";
  var detailUrl = "/api/teacher/students/" + studentId;
  if (TeacherUI.currentClassId) detailUrl += "?class_id=" + TeacherUI.currentClassId;
  TeacherUI.fetchAuth(detailUrl, "GET").then(function(data) {
    if (data.error) {
      detailPane.innerHTML = '<div class="teacher-empty-state">暂无该学生数据。</div>';
      return;
    }
    var name = TeacherUI.escHtml(String(data.nickname || studentId));
    var weak = (data.weak_abilities || []).slice(0, 5);
    var strong = (data.strong_abilities || []).slice(0, 5);
    var patterns = data.diagnostic_patterns || [];
    var recentEvents = data.recent_events || [];
    var html = '<div class="student-detail teacher-section"><h3>' + name + ' (' + TeacherUI.escHtml(studentId) + ')</h3>';
    html += '<div class="teacher-status-badge' + (weak.length ? "" : " teacher-status-normal") + '">' + (weak.length ? "需要关注" : "暂未发现薄弱") + '</div>';
    html += '<div class="teacher-section-title">主要薄弱</div>';
    html += '<div class="teacher-detail-group">' + (weak.length ? weak.map(TeacherUI.abilityLabel).map(TeacherUI.escHtml).join("、") : "暂无明确薄弱项") + '</div>';
    if (patterns.length) {
      html += '<div class="teacher-section-title">最近表现</div>';
      var firstPattern = typeof patterns[0] === "string" ? patterns[0] : (patterns[0].pattern_name || patterns[0].name || patterns[0].type || "存在共性问题");
      html += '<div class="teacher-detail-group">' + TeacherUI.escHtml(firstPattern) + '</div>';
    }
    html += '<div class="teacher-section-title">能力情况</div>';
    html += '<div class="teacher-metric-row">强项：' + (strong.length ? strong.map(TeacherUI.abilityLabel).map(TeacherUI.escHtml).join("、") : "暂无") + '</div>';
    html += '<div class="teacher-metric-row">薄弱：' + (weak.length ? weak.map(TeacherUI.abilityLabel).map(TeacherUI.escHtml).join("、") : "暂无") + '</div>';
    html += '<div class="teacher-section-title">学习依据</div>';
    if (data.overall_score !== undefined) html += '<div class="teacher-metric-row">测评分：<strong>' + TeacherUI.escHtml(String(data.overall_score)) + '</strong></div>';
    if (data.evidence_coverage) html += '<div class="teacher-metric-row">证据覆盖 ' + Math.round(data.evidence_coverage * 100) + '%</div>';
    if (recentEvents.length) {
      html += '<div class="teacher-metric-row">最近学习记录</div>';
      html += '<div class="teacher-detail-group">' + recentEvents.slice(0, 5).map(function(ev) {
        var desc = typeof ev === "string" ? ev : (ev.event_type || ev.type || ev.action || "学习记录");
        return '<div>- ' + TeacherUI.escHtml(desc) + '</div>';
      }).join("") + '</div>';
    }
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0">';
    html += '<button class="btn-secondary" onclick="TeacherUI.askStudent(\'总结该生\')">让 AI 分析该生</button>';
    html += '<button class="btn-secondary" onclick="TeacherUI.askStudent(\'为什么他最近表现不好？\')">为什么薄弱</button>';
    html += '<button class="btn-secondary" onclick="TeacherUI.askStudent(\'生成针对性任务\')">生成针对性任务</button>';
    html += '</div>';
    html += '</div>';
    detailPane.innerHTML = html;
  }).catch(function(e) {
    detailPane.innerHTML = '<div class="teacher-error-state">加载失败，请重试 <button class="btn-secondary" onclick="TeacherUI.lookupStudent(\'' + TeacherUI.escHtml(studentId) + '\')">重新加载</button></div>';
  });
};

TeacherUI.askStudent = function(prompt) {
  if (typeof closeWorkspace === "function") closeWorkspace();
  var input = document.getElementById("chatInput");
  if (input) {
    input.value = prompt || "总结该生";
    input.focus();
  }
  if (typeof sendChat === "function") sendChat(prompt || "总结该生");
};

TeacherUI.askAbility = function(prompt) {
  if (typeof closeWorkspace === "function") closeWorkspace();
  var input = document.getElementById("chatInput");
  if (input) {
    input.value = prompt || "解释这个能力为什么薄弱";
    input.focus();
  }
  if (typeof sendChat === "function") sendChat(prompt || "解释这个能力为什么薄弱");
};

// ============================================================
// Tab: Feedback
// ============================================================
TeacherUI._commentFilter = "all";

TeacherUI.loadFeedback = function() {
  var c = document.getElementById("tw-feedback");
  if (!c) return;
  if (!TeacherUI.currentClassId) {
    c.innerHTML = '<div class="teacher-empty-state">请先选择班级。</div>';
    return;
  }
  c.innerHTML = '<div class="teacher-empty-state">正在加载教学反馈…</div>';
  var url = "/api/teacher/comments?class_id=" + TeacherUI.currentClassId;
  if (TeacherUI._commentFilter !== "all") url += "&status=" + TeacherUI._commentFilter;
  TeacherUI.fetchAuth(url, "GET").then(function(data) {
    var stats = data.stats || {};
    var comments = data.comments || [];
    var html = '<div class="teacher-section"><div class="teacher-section-title">教学反馈</div>';
    html += '<div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">';
    var filters = [["all", "全部"], ["draft", "草稿"], ["reviewed", "待发布"], ["published", "已发布"]];
    filters.forEach(function(f) {
      var active = TeacherUI._commentFilter === f[0] ? "background:#14b8a6;color:#fff" : "background:rgba(255,255,255,0.08)";
      var count = stats[f[0]] !== undefined ? stats[f[0]] : 0;
      html += '<button style="padding:6px 12px;border-radius:6px;border:none;cursor:pointer;' + active + '" onclick="TeacherUI.setCommentFilter(\'' + f[0] + '\')">' + f[1] + ' (' + count + ')</button>';
    });
    html += '</div>';
    if (!comments.length) {
      html += '<div class="teacher-empty-state">暂无教学反馈。</div>';
    } else {
      comments.forEach(function(cm) {
        var sid = TeacherUI.escHtml(String(cm.student_id || ""));
        var status = TeacherUI.commentStatusLabel(cm.status || "draft");
        var studentName = TeacherUI.escHtml(String(cm.student_name || cm.nickname || ""));
        var content = TeacherUI.escHtml(String(cm.content || cm.ai_draft || "").slice(0, 80));
        var evidenceCount = 0;
        evidenceCount = (cm.evidence || []).length;
        html += '<div class="comment-card teacher-list-card" onclick="TeacherUI.openCommentDetail(' + cm.id + ')">';
        html += '<div style="font-weight:600;color:#e2e8f0">' + (studentName ? studentName + ' · ' + sid : '学生 ' + sid) + ' <span class="teacher-status-badge">' + TeacherUI.escHtml(status) + '</span></div>';
        html += '<div style="color:#94a3b8;margin-top:4px">' + content + '</div>';
        html += '<div style="color:#64748b;font-size:0.8rem;margin-top:4px">' + evidenceCount + ' 条学习依据</div>';
        html += '</div>';
      });
    }
    html += '</div>';
    c.innerHTML = html;
  }).catch(function() {
    c.innerHTML = '<div class="teacher-error-state">加载失败，请重试 <button class="btn-secondary" onclick="TeacherUI.loadFeedback()">重新加载</button></div>';
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
    var html = '<div class="teacher-section"><button class="btn-secondary" style="margin-bottom:8px" onclick="TeacherUI.loadFeedback()">返回列表</button>';
    html += '<div class="teacher-section-title">教学反馈详情</div>';
    html += '<div class="detail-row"><span>学生： ' + TeacherUI.escHtml(String(cm.student_id || "")) + '</span></div>';
    html += '<div class="detail-row"><span>状态： <strong>' + TeacherUI.escHtml(TeacherUI.commentStatusLabel(cm.status || "draft")) + '</strong></span></div>';
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
    c.innerHTML = '<div class="teacher-error-state">加载失败，请重试 <button class="btn-secondary" onclick="TeacherUI.openCommentDetail(' + commentId + ')">重新加载</button></div>';
  });
};

TeacherUI.reviewComment = function(commentId) {
  TeacherUI.fetchAuth("/api/teacher/comments/" + commentId + "/review", "POST", {}).then(function() {
    TeacherUI.openCommentDetail(commentId);
  }).catch(function(e) {
    TeacherUI.showToast("审核失败，请重试", "error");
  });
};

TeacherUI.publishComment = function(commentId) {
  TeacherUI.fetchAuth("/api/teacher/comments/" + commentId + "/publish", "POST", {}).then(function() {
    TeacherUI.openCommentDetail(commentId);
  }).catch(function(e) {
    TeacherUI.showToast("发布失败，请重试", "error");
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
