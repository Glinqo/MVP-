// === teacher-ui.js - Teacher Decision Workspace Components ===
// TF-3: Teacher Information Architecture

var TeacherUI = { currentTab: "today", currentIssueId: null };

TeacherUI.initNav = function() {
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
  if (tabId === "today") TeacherUI.loadTodayTeaching();
};

TeacherUI.loadTodayTeaching = function() {
  var container = document.getElementById("todayTeachingContent");
  if (!container) return;
  container.innerHTML = '<div class="muted" style="padding:20px">\u52a0\u8f7d\u6559\u5b66\u95ee\u9898\u4e2d...</div>';
  var token = localStorage.getItem("mcp_auth_token") || "";
  fetch("/api/v2/teacher/issues", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
    body: JSON.stringify({})
  }).then(function(r) { return r.json(); })
  .then(function(data) {
    var issues = data.issues || [];
    if (!issues.length) {
      container.innerHTML = '<div style="padding:40px;text-align:center;color:rgba(255,255,255,0.4)">\u6682\u65e0\u6559\u5b66\u95ee\u9898</div>';
      return;
    }
    TeacherUI.renderIssueList(issues, container);
  }).catch(function(e) {
    container.innerHTML = '<div style="padding:20px">\u52a0\u8f7d\u5931\u8d25</div>';
  });
};

TeacherUI.renderIssueList = function(issues, container) {
  var html = '<div class="issue-list">';
  issues.forEach(function(issue) {
    var pc = issue.priority === "high" ? "badge-priority-high" : (issue.priority === "medium" ? "badge-priority-medium" : "badge-priority-low");
    var students = issue.affected_students || [];
    var iid = issue.issue_id || "";
    html += '<div class="issue-card" onclick="TeacherUI.openIssueDetail(\'' + iid + '\')">';
    html += '<div class="issue-card-header"><span class="issue-card-title">' + (issue.title || "\u672a\u77e5") + '</span></div>';
    html += '<div class="issue-card-meta"><span class="' + pc + '">' + (issue.priority || "") + '</span><span>' + students.length + '\u4eba</span></div>';
    html += '<div class="issue-card-actions" style="margin-top:8px"><button onclick="event.stopPropagation();TeacherUI.openIssueDetail(\'' + iid + '\')">\u67e5\u770b</button></div>';
    html += '</div>';
  });
  html += '</div>';
  container.innerHTML = html;
};

TeacherUI.openIssueDetail = function(issueId) {
  var drawer = document.getElementById("issueDetailDrawer");
  if (!drawer) return;
  drawer.classList.add("open");
  drawer.querySelector(".issue-drawer-title").textContent = "\u52a0\u8f7d\u4e2d...";
  var closeBtn = drawer.querySelector(".issue-drawer-close");
  if (closeBtn && !closeBtn._bound) {
    closeBtn._bound = true;
    closeBtn.addEventListener("click", function() { drawer.classList.remove("open"); });
  }
};

TeacherUI.escHtml = function(text) {
  var d = document.createElement("div");
  d.textContent = text || "";
  return d.innerHTML;
};