/* herdr-web floating spaces/agents sidebar.
 *
 * Additive to the existing terminal: a separate /api WebSocket renders a native
 * DOM drawer (workspaces + agents) from session.snapshot, stays live via
 * events.subscribe, and drives herdr (workspace/tab/pane focus, create, split,
 * rename, close, worktree). Toggled by a floating top-right hamburger. The PTY
 * terminal (#term, /ws) is untouched — focusing here just moves herdr, and the
 * streamed TUI follows. All ids are hz-* to avoid clashing with the terminal. */
(function () {
  "use strict";

  var proto = location.protocol === "https:" ? "wss" : "ws";
  var GLOBAL_EVENTS = [
    "workspace.created", "workspace.updated", "workspace.metadata_updated",
    "workspace.renamed", "workspace.moved", "workspace.closed", "workspace.focused",
    "worktree.created", "worktree.opened", "worktree.removed",
    "tab.created", "tab.closed", "tab.focused", "tab.renamed", "tab.moved",
    "pane.created", "pane.closed", "pane.updated", "pane.focused", "pane.moved",
    "pane.exited", "pane.agent_detected", "layout.updated"
  ];

  var app = document.getElementById("hz-app");
  var wsList = document.getElementById("hz-ws");
  var agentList = document.getElementById("hz-agent");
  var connDot = document.getElementById("hz-conn");

  /* ---- drawer toggle ---- */
  function open() { app.classList.add("open"); }
  function close() { app.classList.remove("open"); }
  document.getElementById("hz-menu").addEventListener("click", open);
  document.getElementById("hz-scrim").addEventListener("click", close);

  /* ---- /api client ---- */
  var api = null, apiTimer = null, apiBackoff = 0, reqSeq = 0;
  var snap = null, resyncTimer = null;

  function send(obj) { if (api && api.readyState === WebSocket.OPEN) api.send(JSON.stringify(obj)); }
  function cmd(method, params) { send({ id: "c" + (++reqSeq), method: method, params: params || {} }); scheduleResync(); }
  function requestSnapshot() { send({ id: "snap", method: "session.snapshot", params: {} }); }
  function scheduleResync() {
    if (resyncTimer) return;
    resyncTimer = setTimeout(function () { resyncTimer = null; requestSnapshot(); }, 120);
  }

  function connect() {
    if (api && (api.readyState === WebSocket.CONNECTING || api.readyState === WebSocket.OPEN)) return;
    if (apiTimer) { clearTimeout(apiTimer); apiTimer = null; }
    api = new WebSocket(proto + "://" + location.host + "/api");
    api.onopen = function () {
      apiBackoff = 0; connDot.classList.add("up");
      send({ id: "sub", method: "events.subscribe",
        params: { subscriptions: GLOBAL_EVENTS.map(function (t) { return { type: t }; }) } });
      requestSnapshot();
    };
    api.onmessage = function (ev) {
      var m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m.event) { scheduleResync(); return; }
      if (m.id === "snap" && m.result) { snap = m.result.snapshot; render(); }
    };
    api.onclose = function () {
      connDot.classList.remove("up");
      apiBackoff = Math.min(apiBackoff ? apiBackoff * 2 : 1000, 5000);
      apiTimer = setTimeout(connect, apiBackoff);
    };
    api.onerror = function () { try { api.close(); } catch (e) {} };
  }

  /* ---- render ---- */
  var STATUS = { working: "working", idle: "idle", blocked: "blocked" };
  function statusClass(s) { return STATUS[s] || "unknown"; }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function dot(status) { return el("span", "hz-dot " + statusClass(status)); }
  function actionBtn(cmdName, id, glyph, title) {
    var b = el("button", null, glyph);
    b.dataset.cmd = cmdName; if (id) b.dataset.id = id; b.title = title;
    return b;
  }

  function render() {
    if (!snap) return;
    var fWs = snap.focused_workspace_id, fTab = snap.focused_tab_id, fPane = snap.focused_pane_id;
    var tabsByWs = {};
    (snap.tabs || []).forEach(function (t) { (tabsByWs[t.workspace_id] = tabsByWs[t.workspace_id] || []).push(t); });

    wsList.textContent = "";
    (snap.workspaces || []).forEach(function (w) {
      var row = el("li", "hz-row ws" + (w.workspace_id === fWs ? " focused" : ""));
      row.dataset.cmd = "focus-workspace"; row.dataset.id = w.workspace_id;
      row.appendChild(dot(w.agent_status));
      row.appendChild(el("span", "hz-label", w.label || ("ws" + w.number)));
      row.appendChild(el("span", "hz-meta", (w.tab_count || 0) + "t"));
      var acts = el("span", "hz-actions");
      acts.appendChild(actionBtn("rename-workspace", w.workspace_id, "✎", "Rename"));
      acts.appendChild(actionBtn("close-workspace", w.workspace_id, "✕", "Close"));
      row.appendChild(acts);
      wsList.appendChild(row);

      if (w.workspace_id === fWs) {
        (tabsByWs[w.workspace_id] || []).forEach(function (t) {
          var tr = el("li", "hz-row tab" + (t.tab_id === fTab ? " focused" : ""));
          tr.dataset.cmd = "focus-tab"; tr.dataset.id = t.tab_id;
          tr.appendChild(el("span", "hz-num", t.number != null ? String(t.number) : ""));
          tr.appendChild(dot(t.agent_status));
          tr.appendChild(el("span", "hz-label", t.label || ("tab" + t.number)));
          var ta = el("span", "hz-actions");
          ta.appendChild(actionBtn("rename-tab", t.tab_id, "✎", "Rename"));
          ta.appendChild(actionBtn("close-tab", t.tab_id, "✕", "Close"));
          tr.appendChild(ta);
          wsList.appendChild(tr);
        });
        var tools = el("div", "hz-tools");
        tools.appendChild(actionBtn("new-tab", w.workspace_id, "＋ tab", "New tab"));
        tools.appendChild(actionBtn("split-right", null, "⇥ split", "Split right"));
        tools.appendChild(actionBtn("split-down", null, "⤓ split", "Split down"));
        tools.appendChild(actionBtn("worktree", null, "⑂ tree", "New worktree"));
        wsList.appendChild(tools);
      }
    });

    var wsLabel = {}, tabLabel = {};
    (snap.workspaces || []).forEach(function (w) { wsLabel[w.workspace_id] = w.label; });
    (snap.tabs || []).forEach(function (t) { tabLabel[t.tab_id] = t.label; });
    agentList.textContent = "";
    (snap.agents || []).forEach(function (a) {
      var row = el("li", "hz-row agent" + (a.pane_id === fPane ? " focused" : ""));
      row.dataset.cmd = "focus-agent"; row.dataset.pane = a.pane_id;
      row.dataset.ws = a.workspace_id; row.dataset.tab = a.tab_id;
      row.appendChild(dot(a.agent_status));
      row.appendChild(el("span", "hz-label", a.terminal_title_stripped || a.agent || "agent"));
      // herdr's own agent name (`herdr agent rename`), straight off the snapshot —
      // the titles plugin mirrors the same value into $name for the TUI sidebar,
      // which has no built-in token for it, but here we read it at the source.
      // Unnamed agents get no span rather than an empty one.
      if (a.name) row.appendChild(el("span", "hz-meta", a.name));
      var where = (wsLabel[a.workspace_id] || "") + (tabLabel[a.tab_id] ? " / " + tabLabel[a.tab_id] : "");
      row.appendChild(el("div", "hz-sub", where + " · " + (a.agent || "")));
      agentList.appendChild(row);
    });
  }

  /* ---- command dispatch ---- */
  function onClick(e) {
    var t = e.target.closest("[data-cmd]");
    if (!t) return;
    var c = t.dataset.cmd, id = t.dataset.id, label;
    switch (c) {
      case "focus-workspace": cmd("workspace.focus", { workspace_id: id }); close(); break;
      case "focus-tab": cmd("tab.focus", { tab_id: id }); close(); break;
      case "focus-agent":
        if (t.dataset.ws) cmd("workspace.focus", { workspace_id: t.dataset.ws });
        if (t.dataset.tab) cmd("tab.focus", { tab_id: t.dataset.tab });
        cmd("pane.focus", { pane_id: t.dataset.pane }); close(); break;
      case "new-workspace":
        label = prompt("New workspace name (blank = auto):");
        if (label !== null) cmd("workspace.create", { label: label || null, focus: true });
        break;
      case "rename-workspace":
        label = prompt("Rename workspace:"); if (label) cmd("workspace.rename", { workspace_id: id, label: label }); break;
      case "close-workspace":
        if (confirm("Close this workspace and all its tabs?")) cmd("workspace.close", { workspace_id: id }); break;
      case "new-tab": cmd("tab.create", { workspace_id: id, focus: true }); break;
      case "rename-tab":
        label = prompt("Rename tab:"); if (label) cmd("tab.rename", { tab_id: id, label: label }); break;
      case "close-tab":
        if (confirm("Close this tab?")) cmd("tab.close", { tab_id: id }); break;
      case "split-right": cmd("pane.split", { direction: "right", focus: true }); break;
      case "split-down": cmd("pane.split", { direction: "down", focus: true }); break;
      case "worktree":
        label = prompt("Worktree branch (blank = new branch):");
        if (label !== null) cmd("worktree.create", { branch: label || null, focus: true }); break;
    }
  }
  document.getElementById("hz-sidebar").addEventListener("click", onClick);
  document.getElementById("hz-new-ws").addEventListener("click", function () {
    var label = prompt("New workspace name (blank = auto):");
    if (label !== null) cmd("workspace.create", { label: label || null, focus: true });
  });

  /* ---- reconnect + boot ---- */
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible") connect(); });
  window.addEventListener("online", connect);
  window.addEventListener("focus", connect);
  window.addEventListener("pageshow", connect);
  connect();
})();
