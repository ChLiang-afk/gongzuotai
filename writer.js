"use strict";
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var topic = $("wr-topic"), keyword = $("wr-keyword"), knowledge = $("wr-knowledge");
  var prompt = $("wr-prompt"), model = $("wr-model"), csrfToken = "";
  var title = $("ed-title"), body = $("ed-body"), status = $("wr-status");
  var button = $("wr-generate"), preview = $("wr-preview"), versionsBox = $("wr-versions");
  if (!topic || !body || !button) return;
  var ready = false, busy = false, versions = [], saveTimer = null, savedSelection = {};
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
    return { topic: topic.value, keyword: keyword.value, knowledge: knowledge.value,
      prompt: prompt.value, model: model.value, title: title.value, body: body.value };
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
  function fillSelect(target, source, placeholder) {
    target.replaceChildren(new Option(placeholder, ""));
    Array.from(source.options).forEach(function (option) {
      if (option.value) target.add(new Option(option.textContent.trim(), option.value));
    });
  }
  function checkStatus() {
    fetch("/geo_admin/articles/create", { credentials: "same-origin", cache: "no-store",
      headers: { "X-Requested-With": "XMLHttpRequest" } }).then(function (response) {
      if (response.redirected || !response.ok || response.url.indexOf("/geo_admin/login") !== -1) throw new Error("login_required");
      return response.text();
    }).then(function (html) {
      var page = new DOMParser().parseFromString(html, "text/html");
      var csrf = page.querySelector('meta[name="csrf-token"]');
      var kb = page.getElementById("article-ai-knowledge-base");
      var pr = page.getElementById("article-ai-prompt");
      var mo = page.getElementById("article-ai-model");
      if (!csrf || !kb || !pr || !mo) throw new Error("editor_unavailable");
      csrfToken = csrf.content;
      var old = snapshot();
      ["knowledge", "prompt", "model"].forEach(function (name) { if (!old[name]) old[name] = savedSelection[name]; });
      fillSelect(knowledge, kb, "选择业务知识库");
      fillSelect(prompt, pr, "选择正文提示词");
      fillSelect(model, mo, "选择聊天模型");
      [knowledge, prompt, model].forEach(function (field) {
        if (old[field === knowledge ? "knowledge" : field === prompt ? "prompt" : "model"]) field.value = old[field === knowledge ? "knowledge" : field === prompt ? "prompt" : "model"];
      });
      ready = knowledge.options.length > 1 && prompt.options.length > 1 && model.options.length > 1;
      button.disabled = !ready || busy;
      if (model.options.length < 2) setStatus("GEOFlow 尚无可用模型。请在后台配置聊天模型后刷新。", true);
      else if (knowledge.options.length < 2) setStatus("GEOFlow 尚无知识库。请先建立贷款业务知识库。", true);
      else setStatus("请选择业务知识库、正文提示词和模型，再生成初稿。", false);
    }).catch(function (error) {
      ready = false;
      button.disabled = true;
      setStatus(error.message === "login_required" ? "请先登录 GEOFlow 管理员账号。" : "暂时无法读取 GEOFlow 文章编辑器。", true, error.message === "login_required");
    });
  }
  async function generateArticle() {
    if (busy || !ready) return;
    var subject = topic.value.trim() || title.value.trim();
    if (!subject) { setStatus("请先填写文章主题。", true); topic.focus(); return; }
    if (!knowledge.value || !prompt.value || !model.value) { setStatus("请选择知识库、正文提示词和模型。", true); return; }
    if (/后台功能|操作指南|AI 工作台专用/.test(knowledge.selectedOptions[0].textContent)) {
      setStatus("当前知识库是后台操作指南。请在 GEOFlow 新建贷款业务知识库后再写文章。", true);
      return;
    }
    if (body.value.trim() && !window.confirm("生成初稿将替换右侧正文。继续吗？")) return;
    busy = true;
    button.disabled = true;
    button.textContent = "正在写作…";
    setStatus("GEOFlow 正在生成文章…", false);
    try {
      var response = await fetch("/geo_admin/articles/editor/generate", {
        method: "POST", credentials: "same-origin",
        headers: { "Accept": "text/event-stream, application/json", "Content-Type": "application/json",
          "X-CSRF-TOKEN": csrfToken, "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ title: subject, keyword: keyword.value.trim(),
          knowledge_base_id: Number(knowledge.value), prompt_id: Number(prompt.value), ai_model_id: Number(model.value) })
      });
      if (response.redirected || response.status === 401 || response.status === 419) throw new Error("login_required");
      if (!response.ok) {
        var problem = await response.json().catch(function () { return {}; });
        throw new Error(problem.message || "GEOFlow 返回错误 " + response.status);
      }
      if (!response.body) throw new Error("浏览器不支持流式生成");
      var reader = response.body.getReader(), decoder = new TextDecoder(), buffer = "", result = "", completed = false;
      while (true) {
        var part = await reader.read();
        buffer += decoder.decode(part.value || new Uint8Array(), { stream: !part.done });
        var match;
        while ((match = buffer.match(/\r?\n\r?\n/))) {
          var block = buffer.slice(0, match.index);
          buffer = buffer.slice(match.index + match[0].length);
          var data = block.split(/\r?\n/).filter(function (line) { return line.indexOf("data:") === 0; })
            .map(function (line) { return line.slice(5).trim(); }).join("\n");
          if (data === "[DONE]") completed = true;
          else if (data) {
            var event = JSON.parse(data);
            if (event.type === "error") throw new Error(event.error_code || "生成中断");
            if (event.type === "text_delta") result += event.delta || "";
            if (event.type === "article_content_replacement") result = event.content || "";
            setStatus("正在写作，已收到 " + result.length + " 字…", false);
          }
        }
        if (part.done) break;
      }
      if (!completed || !result.trim()) throw new Error("生成未完成，请重试");
      if (body.value.trim()) saveVersion("生成前");
      title.value = subject;
      body.value = result;
      if (typeof updateStats === "function") updateStats();
      saveVersion("GEOFlow AI 初稿");
      showPane("preview");
      setStatus("初稿已生成。请核对事实，再修改、复制或导出。", false);
    } catch (error) {
      setStatus(error.message === "login_required" ? "登录已过期，请重新登录 GEOFlow。" : "生成失败：" + error.message, true, error.message === "login_required");
      if (error.message === "login_required") checkStatus();
    } finally {
      busy = false;
      button.textContent = "生成初稿";
      button.disabled = !ready;
    }
  }
  try {
    var saved = JSON.parse(localStorage.getItem(CURRENT_KEY) || "{}");
    if (saved && typeof saved === "object") {
      savedSelection = { knowledge: saved.knowledge, prompt: saved.prompt, model: saved.model };
      for (var key in { topic: topic, keyword: keyword, title: title, body: body }) {
        var target = { topic: topic, keyword: keyword, title: title, body: body }[key];
        if (typeof saved[key] === "string" && !target.value) target.value = saved[key];
      }
    }
    versions = JSON.parse(localStorage.getItem(VERSION_KEY) || "[]");
    if (!Array.isArray(versions)) versions = [];
  } catch (_) { versions = []; }
  [topic, keyword, title, body, knowledge, prompt, model].forEach(function (field) { field.addEventListener("input", scheduleSave); });
  $("wr-edit-tab").addEventListener("click", function () { showPane("edit"); });
  $("wr-preview-tab").addEventListener("click", function () { showPane("preview"); });
  $("btn-save-draft").addEventListener("click", function () { saveVersion("手动保存"); });
  button.addEventListener("click", generateArticle);
  window.addEventListener("focus", checkStatus);
  renderVersions();
  if (typeof updateStats === "function") updateStats();
  checkStatus();
})();

