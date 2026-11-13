"use strict";
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var topic = $("wr-topic"), audience = $("wr-audience"), facts = $("wr-facts");
  var length = $("wr-length"), instruction = $("wr-instruction"), revise = $("wr-revise");
  var title = $("ed-title"), body = $("ed-body"), status = $("wr-status");
  var button = $("wr-generate"), preview = $("wr-preview"), versionsBox = $("wr-versions");
  if (!topic || !body || !button) return;
  var ready = false, busy = false, versions = [], saveTimer = null;
  var CURRENT_KEY = "gongzuotai-writer-current-v1", VERSION_KEY = "gongzuotai-writer-versions-v1";

  function setStatus(message, error, loginLink) {
    status.textContent = message;
    status.classList.toggle("error", !!error);
    if (loginLink) {
      var a = document.createElement("a");
      a.href = "/geo_admin/login";
      a.textContent = "打开管理员登录页 ↗";
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      status.appendChild(document.createTextNode(" "));
      status.appendChild(a);
    }
  }
  function snapshot() {
    return { topic: topic.value, audience: audience.value, facts: facts.value,
      length: length.value, instruction: instruction.value, title: title.value, body: body.value };
  }
  function saveCurrent() {
    try { localStorage.setItem(CURRENT_KEY, JSON.stringify(snapshot())); } catch (_) {}
  }
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveCurrent, 350);
  }
  function saveVersion(label) {
    if (!title.value.trim() && !body.value.trim()) return;
    versions.unshift({ at: new Date().toISOString(), label: label, title: title.value, body: body.value });
    versions = versions.slice(0, 20);
    try { localStorage.setItem(VERSION_KEY, JSON.stringify(versions)); } catch (_) {}
    renderVersions();
    saveCurrent();
  }
  function renderVersions() {
    versionsBox.replaceChildren();
    if (!versions.length) {
      versionsBox.textContent = "尚无版本。生成或保存后会留在本设备浏览器。";
      return;
    }
    versions.forEach(function (version, index) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = new Date(version.at).toLocaleString("zh-CN") + " · " + version.label + " · " + (version.title || "未命名文章");
      b.addEventListener("click", function () {
        if (title.value !== version.title || body.value !== version.body) saveVersion("切换前自动保存");
        title.value = version.title;
        body.value = version.body;
        if (typeof updateStats === "function") updateStats();
        showPane("edit");
        saveCurrent();
        setStatus("已打开历史版本，可以继续修改。", false);
      });
      versionsBox.appendChild(b);
    });
  }
  function paragraph(text) {
    var p = document.createElement("p");
    p.textContent = text;
    return p;
  }
  function renderPreview() {
    preview.replaceChildren();
    if (title.value.trim()) {
      var h1 = document.createElement("h2");
      h1.textContent = title.value.trim();
      preview.appendChild(h1);
    }
    if (!body.value.trim()) {
      var empty = document.createElement("div");
      empty.className = "empty-note";
      empty.textContent = "正文完成后，这里会显示排版预览。";
      preview.appendChild(empty);
      return;
    }
    body.value.split(/\n\s*\n/).forEach(function (block) {
      var line = block.trim();
      if (!line) return;
      if (/^#{1,3}\s/.test(line)) {
        var h = document.createElement("h2");
        h.textContent = line.replace(/^#{1,3}\s*/, "");
        preview.appendChild(h);
      } else preview.appendChild(paragraph(line.replace(/^[-*]\s/gm, "• ")));
    });
  }
  function showPane(pane) {
    var isPreview = pane === "preview";
    $("wr-edit-tab").classList.toggle("active", !isPreview);
    $("wr-edit-tab").setAttribute("aria-selected", String(!isPreview));
    $("wr-preview-tab").classList.toggle("active", isPreview);
    $("wr-preview-tab").setAttribute("aria-selected", String(isPreview));
    body.hidden = isPreview;
    preview.hidden = !isPreview;
    if (isPreview) renderPreview();
  }
  function checkStatus() {
    fetch("api/status", { credentials: "same-origin", cache: "no-store" }).then(function (response) {
      if (!response.ok) throw new Error("status_unavailable");
      return response.json();
    }).then(function (state) {
      ready = !!(state.authorized && state.configured);
      button.disabled = !ready || busy;
      if (!state.authorized) setStatus("生成文章需要先登录 GEOFlow 管理员账号。手写、预览和导出仍可使用。", true, true);
      else if (!state.configured) setStatus("管理员已登录；写作模型尚未配置。配置后刷新页面即可生成。", true);
      else setStatus("写作模型已就绪。输入主题后可生成初稿，或勾选改写现有正文。", false);
    }).catch(function () {
      ready = false;
      button.disabled = true;
      setStatus("写作服务暂不可用。手写、预览和导出仍可使用。", true);
    });
  }
  function generateArticle() {
    if (busy || !ready) return;
    var subject = topic.value.trim() || title.value.trim();
    if (!subject) { setStatus("请先填写文章主题。", true); topic.focus(); return; }
    var oldBody = revise.checked ? body.value.trim() : "";
    if (revise.checked && !oldBody) { setStatus("勾选改写时，右侧正文不能是空的。", true); return; }
    busy = true;
    button.disabled = true;
    button.textContent = "正在写作…";
    setStatus(revise.checked ? "正在改写全文，请稍候…" : "正在生成初稿，请稍候…", false);
    fetch("api/generate", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: subject, audience: audience.value.trim(), facts: facts.value.trim(),
        length: Number(length.value) || 1000, instruction: instruction.value.trim(), existing: oldBody })
    }).then(function (response) {
      return response.json().then(function (data) { if (!response.ok) throw new Error(data.error || "request_failed"); return data; });
    }).then(function (article) {
      if (!article.body) throw new Error("invalid_model_response");
      if (oldBody) saveVersion("改写前");
      title.value = article.title || subject;
      body.value = article.body;
      topic.value = subject;
      if (typeof updateStats === "function") updateStats();
      saveVersion(oldBody ? "AI 改写" : "AI 初稿");
      showPane("preview");
      setStatus("文章已生成。请核对事实和【待核实】标记，再修改、复制或导出。", false);
    }).catch(function (error) {
      var messages = { login_required: "登录已过期，请重新登录管理员账号。", model_not_configured: "写作模型尚未配置。", daily_or_hourly_limit: "生成次数已达限额，请稍后再试。", model_unavailable: "模型服务暂不可用，请检查服务器配置。", invalid_model_response: "模型返回了无效文章，请稍后重试。" };
      setStatus(messages[error.message] || "生成失败，请稍后重试。", true, error.message === "login_required");
      if (error.message === "login_required" || error.message === "model_not_configured") checkStatus();
    }).finally(function () {
      busy = false;
      button.textContent = revise.checked ? "改写全文" : "生成初稿";
      button.disabled = !ready;
    });
  }
  try {
    var saved = JSON.parse(localStorage.getItem(CURRENT_KEY) || "{}");
    if (saved && typeof saved === "object") {
      for (var key in { topic: topic, audience: audience, facts: facts, length: length,
                        instruction: instruction, title: title, body: body }) {
        var target = { topic: topic, audience: audience, facts: facts, length: length,
                       instruction: instruction, title: title, body: body }[key];
        if (typeof saved[key] === "string" && !target.value) target.value = saved[key];
      }
    }
    versions = JSON.parse(localStorage.getItem(VERSION_KEY) || "[]");
    if (!Array.isArray(versions)) versions = [];
  } catch (_) { versions = []; }
  [topic, audience, facts, length, instruction, title, body].forEach(function (field) { field.addEventListener("input", scheduleSave); });
  $("wr-edit-tab").addEventListener("click", function () { showPane("edit"); });
  $("wr-preview-tab").addEventListener("click", function () { showPane("preview"); });
  revise.addEventListener("change", function () { button.textContent = revise.checked ? "改写全文" : "生成初稿"; });
  $("btn-save-draft").addEventListener("click", function () { saveVersion("手动保存"); });
  button.addEventListener("click", generateArticle);
  window.addEventListener("focus", checkStatus);
  renderVersions();
  if (typeof updateStats === "function") updateStats();
  checkStatus();
})();
