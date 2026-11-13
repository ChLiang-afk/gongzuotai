"use strict";
(function () {
  var data = [];
  var source = "全部";
  var mode = "articles";
  var search = "";
  var list = document.getElementById("lf-list");
  var meta = document.getElementById("lf-meta");
  if (!list || !meta) return;

  function validLink(url) {
    try {
      var parsed = new URL(url);
      return parsed.protocol === "https:" && /(^|\.)(weixin\.sogou\.com|toutiao\.com)$/.test(parsed.hostname) ? parsed.href : "";
    } catch (_) { return ""; }
  }
  function validImage(url) {
    try {
      var parsed = new URL(url);
      return parsed.protocol === "https:" && /(^|\.)(sogoucdn\.com|toutiaoimg\.com|qpic\.cn)$/.test(parsed.hostname) ? parsed.href : "";
    } catch (_) { return ""; }
  }
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  function renderSources() {
    var row = document.getElementById("lf-sources");
    row.replaceChildren();
    ["全部", "微信搜索", "今日头条"].forEach(function (name) {
      var count = name === "全部" ? data.length : data.filter(function (item) { return item.source === name; }).length;
      var button = el("button", "chip-btn" + (name === source ? " active" : ""), name + " " + count);
      button.type = "button";
      button.addEventListener("click", function () { source = name; renderSources(); render(); });
      row.appendChild(button);
    });
  }
  function render() {
    list.replaceChildren();
    var matches = data.filter(function (item) {
      if (source !== "全部" && item.source !== source) return false;
      if (mode === "images" && !validImage(item.image)) return false;
      return !search || (item.title + " " + item.author + " " + item.keyword).toLowerCase().includes(search);
    });
    if (!matches.length) {
      list.appendChild(el("div", "lf-empty", mode === "images" ? "当前筛选没有可用封面，试试切换来源或关键词。" : "当前筛选没有文章，试试其他关键词。"));
      return;
    }
    matches.forEach(function (item) {
      var card = el("article", "lf-card");
      var link = validLink(item.url);
      var image = validImage(item.image);
      if (image) {
        var img = el("img");
        img.src = image;
        img.alt = "《" + item.title + "》的来源配图";
        img.loading = "lazy";
        img.referrerPolicy = "no-referrer";
        card.appendChild(img);
      }
      var body = el("div", "lf-card-body");
      body.appendChild(el("span", "lf-badge", item.source + " · 粉丝数未验证"));
      var heading = el("h3");
      if (link) {
        var anchor = el("a", "", item.title);
        anchor.href = link;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        heading.appendChild(anchor);
      } else heading.textContent = item.title;
      body.appendChild(heading);
      var details = item.author + " · " + item.published_at;
      if (Number.isFinite(item.read_count) && item.source === "今日头条") details += " · 阅读 " + item.read_count.toLocaleString("zh-CN");
      body.appendChild(el("p", "", details));
      if (mode === "articles" && item.summary) body.appendChild(el("p", "", item.summary));
      if (mode === "articles") {
        var use = el("button", "btn small", "用这个选题创作");
        use.type = "button";
        use.addEventListener("click", function () {
          document.getElementById("wr-topic").value = item.title;
          document.getElementById("ed-title").value = item.title;
          document.getElementById("ed-body").value = "";
          if (typeof updateStats === "function") updateStats();
          if (typeof gotoView === "function") gotoView("write");
        });
        body.appendChild(use);
      }
      card.appendChild(body);
      list.appendChild(card);
    });
  }
  function setMode(next) {
    mode = next;
    document.getElementById("lf-articles").classList.toggle("active", next === "articles");
    document.getElementById("lf-images").classList.toggle("active", next === "images");
    render();
  }
  document.getElementById("lf-articles").addEventListener("click", function () { setMode("articles"); });
  document.getElementById("lf-images").addEventListener("click", function () { setMode("images"); });
  document.getElementById("lf-search").addEventListener("input", function () { search = this.value.trim().toLowerCase(); render(); });
  fetch("lowfan.json", { cache: "no-store" }).then(function (response) {
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  }).then(function (snapshot) {
    if (!Array.isArray(snapshot.articles)) throw new Error("快照格式错误");
    data = snapshot.articles.filter(function (item) {
      return item && typeof item.title === "string" && typeof item.author === "string" && typeof item.published_at === "string";
    });
    var sourceStatus = snapshot.source_success || {};
    var staleSources = ["微信搜索", "今日头条"].filter(function (name) { return sourceStatus[name] === 0; });
    meta.textContent = "快照生成于 " + new Date(snapshot.generated_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" }) + " · " + data.length + " 篇文章 · " + data.filter(function (item) { return !!validImage(item.image); }).length + " 张配图" + (staleSources.length ? " · " + staleSources.join("、") + "本次受限，沿用近 14 天已抓内容" : "");
    renderSources();
    render();
  }).catch(function () {
    meta.textContent = "文章快照暂不可用";
    list.replaceChildren(el("div", "lf-empty", "采集暂未成功，请稍后再试。"));
  });
})();
