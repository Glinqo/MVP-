/*
 * Chat History Sidebar
 */

var _sidebar_ready = false;
var _sidebar_switching = false;

function initSidebar() {
  if (_sidebar_ready) return;
  _sidebar_ready = true;
  refreshSidebar();
  window.addEventListener("resize", function() {
    var sb = document.getElementById("historySidebar");
    if (!sb) return;
    if (window.innerWidth > 768) {
      sb.classList.remove("mobile-open");
      document.getElementById("sidebarOverlay").classList.remove("active");
    }
  });
}

var _origBoot = window.boot;
window.boot = function() {
  if (_origBoot) _origBoot.apply(this, arguments);
  initSidebar();
};

function toggleSidebar() {
  // Hover handles desktop; mobile uses this
  var sb = document.getElementById("historySidebar");
  var ov = document.getElementById("sidebarOverlay");
  if (!sb) return;
  if (window.innerWidth <= 768) {
    if (sb.classList.contains("mobile-open")) {
      sb.classList.remove("mobile-open");
      ov.classList.remove("active");
    } else {
      sb.classList.add("mobile-open");
      ov.classList.add("active");
    }
  }
}

function refreshSidebar() {
  var list = document.getElementById("historyList");
  if (!list) return;
  list.innerHTML = '<div class="sidebar-loading">加载中</div>';
  var jobRole = (typeof state !== "undefined" && state.jobProfile) ? (state.jobProfile.id || state.jobProfile.role_name || "") : (localStorage.getItem("mcp_job_id") || "");
  fetch("/api/conversations?job_role=" + encodeURIComponent(jobRole)).then(function(r) { return r.json(); }).then(function(sessions) {
    if (!sessions || !sessions.length) {
      list.innerHTML = '<div class="sidebar-empty">暂无历史对话</div>';
      return;
    }
    list.innerHTML = sessions.map(function(s) {
      var active = s.session_id === state.sessionId ? " active" : "";
      var sid = s.session_id.replace(/'/g, "").replace(/"/g, "");
      var title = escapeHtml(s.title || sid.substring(0, 12));
      var count = s.message_count || 0;
      return '<div class="history-item' + active + '" data-sid="' + sid + '">' +
        '<div class="history-item-title" ondblclick="startRename(this, \'' + sid + '\')" title="双击重命名">' + title + '</div>' +
        '<div class="history-item-meta">' + count + ' 条消息</div>' +
        '<button class="history-item-delete" title="删除" onclick="deleteChat(event, \'' + sid + '\')">X</button>' +
        '</div>';
    }).join("");
    list.querySelectorAll(".history-item").forEach(function(item) {
      item.addEventListener("click", function(e) {
        if (e.target.classList.contains("history-item-delete")) return;
        switchToChat(item.dataset.sid);
      });
    });
  }).catch(function() {
    list.innerHTML = '<div class="sidebar-error">加载失败</div>';
  });
}

function switchToChat(sessionId) {
  if (_sidebar_switching) return;
  if (sessionId === state.sessionId) return;
  _sidebar_switching = true;
  fetch("/api/conversation/" + encodeURIComponent(sessionId)).then(function(r) { return r.json(); }).then(function(data) {
    state.sessionId = sessionId;
    state.messages = (data.messages || []).map(function(m) {
      return { role: m.role, content: m.content, meta: m.meta || {} };
    });
    persistSession();
    renderMessages();
    refreshSidebar();
    if (window.innerWidth <= 768) toggleSidebar();
    _sidebar_switching = false;
  }).catch(function(e) {
    addMessage("assistant", "加载失败: " + e.message);
    _sidebar_switching = false;
  });
}

function deleteChat(event, sessionId) {
  event.stopPropagation();
  if (!confirm("确定删除此对话吗?")) return;
  fetch("/api/conversation/" + encodeURIComponent(sessionId) + "?action=delete", { method: "POST" }).then(function(r) { return r.json(); }).then(function() {
    if (sessionId === state.sessionId) { createNewChat(); } else { refreshSidebar(); }
  }).catch(function(e) {
    addMessage("assistant", "删除失败: " + e.message);
  });
}

function startRename(el, sessionId) {
  var oldTitle = el.textContent;
  var input = document.createElement("input");
  input.type = "text";
  input.className = "history-item-rename";
  input.value = oldTitle;
  input.maxLength = 60;
  function finish() {
    var newTitle = input.value.trim() || oldTitle;
    el.textContent = newTitle;
    el.style.display = "";
    input.remove();
    if (newTitle !== oldTitle) {
      fetch("/api/conversation/" + encodeURIComponent(sessionId) + "?action=rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle })
      }).catch(function(){});
    }
  }
  input.addEventListener("blur", finish);
  input.addEventListener("keydown", function(e) {
    if (e.key === "Enter") input.blur();
    if (e.key === "Escape") { input.value = oldTitle; input.blur(); }
  });
  el.style.display = "none";
  el.parentNode.insertBefore(input, el.nextSibling);
  input.focus();
  input.select();
}
