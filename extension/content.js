(() => {
  if (window.top !== window || document.getElementById("thinkspace-bubble-host")) return;

  const host = document.createElement("div");
  host.id = "thinkspace-bubble-host";
  const shadow = host.attachShadow({ mode: "open" });
  const stylesheet = document.createElement("link");
  stylesheet.rel = "stylesheet";
  stylesheet.href = chrome.runtime.getURL("content.css");
  shadow.appendChild(stylesheet);

  const root = document.createElement("div");
  root.innerHTML = `
    <div class="ts-recall" hidden aria-label="旧泡泡提醒">
      <button class="ts-recall-open" type="button" aria-controls="ts-bubble-panel"></button>
      <button class="ts-recall-dismiss" type="button" aria-label="收起旧泡泡提醒">×</button>
    </div>
    <button class="ts-launcher" type="button" aria-label="打开 ThinkSpace 灵感泡泡">
      <span class="ts-dot"></span><span>想法</span><span class="ts-count" hidden>0</span>
    </button>
    <section id="ts-bubble-panel" class="ts-panel" hidden aria-label="ThinkSpace 灵感泡泡">
      <header class="ts-header"><span class="ts-brand">THINKSPACE · 灵感泡泡</span><button class="ts-close" type="button" aria-label="关闭">×</button></header>
      <div class="ts-body">
        <div class="ts-source"><strong></strong><span></span></div>
        <label class="ts-label">文章里触动你的内容</label>
        <blockquote class="ts-quote" hidden></blockquote>
        <button class="ts-quote-button" type="button">使用当前选中文字</button>
        <label class="ts-label" for="ts-body-text">你的想法</label>
        <textarea id="ts-body-text" class="ts-textarea" placeholder="记录一个疑问、猜想、反例，或暂时不成熟的判断……" maxlength="4000"></textarea>
        <button class="ts-save" type="button">保存泡泡</button>
        <p class="ts-status" role="status"></p>
        <section class="ts-related" hidden><h3>相关旧泡泡</h3><div class="ts-notes"></div></section>
        <a class="ts-web" href="http://localhost:5173" target="_blank" rel="noreferrer">在 ThinkSpace 中查看全部 →</a>
      </div>
    </section>`;
  shadow.appendChild(root);
  document.documentElement.appendChild(host);

  const launcher = root.querySelector(".ts-launcher");
  const count = root.querySelector(".ts-count");
  const panel = root.querySelector(".ts-panel");
  const close = root.querySelector(".ts-close");
  const sourceTitle = root.querySelector(".ts-source strong");
  const sourceMeta = root.querySelector(".ts-source span");
  const quote = root.querySelector(".ts-quote");
  const quoteButton = root.querySelector(".ts-quote-button");
  const body = root.querySelector(".ts-textarea");
  const save = root.querySelector(".ts-save");
  const status = root.querySelector(".ts-status");
  const related = root.querySelector(".ts-related");
  const notes = root.querySelector(".ts-notes");
  const recall = root.querySelector(".ts-recall");
  const recallOpen = root.querySelector(".ts-recall-open");
  const recallDismiss = root.querySelector(".ts-recall-dismiss");

  let lastUrl = "", lastRequest = "", selectedText = "";
  let requestVersion = 0, dismissed = false;

  function send(message) {
    return chrome.runtime.sendMessage(message).then((response) => {
      if (!response?.ok) throw new Error(response?.error || "无法连接 ThinkSpace。请点击扩展图标完成配对。");
      return response.data;
    });
  }

  function text(selectors) {
    for (const selector of selectors) {
      const element = document.querySelector(selector);
      const value = (element?.getAttribute("content") || element?.textContent)?.trim();
      if (value) return value;
    }
    return "";
  }

  function cleanUrl() {
    const url = new URL(location.href);
    url.search = "";
    url.hash = "";
    return url.toString().replace(/\/$/, "");
  }

  function isReadingUrl(value) {
    const url = new URL(value);
    if (url.origin === "https://zhuanlan.zhihu.com") return /^\/p\/\d+$/.test(url.pathname);
    return url.origin === "https://www.zhihu.com"
      && /^\/(?:question\/\d+\/answer\/\d+|pin\/\d+|zvideo\/\d+)$/.test(url.pathname);
  }

  function sourceInfo() {
    const title = text([
      "h1.Post-Title",
      ".QuestionHeader-title",
      "h1",
      'meta[property="og:title"]',
    ]) || document.title.replace(/ - 知乎$/, "").trim();
    const author = text([
      ".AuthorInfo-name",
      ".AuthorInfo-content .UserLink-link",
      ".Post-Author .UserLink-link",
      'meta[name="author"]',
    ]);
    return { source_url: cleanUrl(), title, author_name: author };
  }

  function selectionText() {
    return String(window.getSelection()?.toString() || "").trim().slice(0, 4000);
  }

  function setQuote(value = selectionText()) {
    quote.hidden = !value;
    quote.textContent = value;
  }

  function setStatus(message, isError = false) {
    status.textContent = message;
    status.classList.toggle("error", isError);
  }

  function renderNotes(items) {
    count.hidden = items.length === 0;
    count.textContent = String(items.length);
    related.hidden = items.length === 0;
    notes.replaceChildren();
    recall.hidden = dismissed || !panel.hidden || items.length === 0;
    recallOpen.textContent = `找到了 ${items.length} 条旧泡泡`;
    items.forEach((item) => {
      const note = document.createElement("div");
      note.className = "ts-note";
      const match = document.createElement("strong");
      match.textContent = item.match === "same_article" ? "同一篇文章" : "相关记录";
      const summary = document.createElement("p");
      summary.textContent = item.body;
      const link = document.createElement("a");
      link.href = `http://localhost:5173/thought-bubbles?note=${encodeURIComponent(item.id)}`;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "在 ThinkSpace 查看泡泡";
      const time = document.createElement("time");
      time.textContent = new Date(item.created_at * 1000).toLocaleString("zh-CN");
      note.append(match, summary, link, time);
      notes.appendChild(note);
    });
  }

  async function refreshContext(force = false) {
    const url = cleanUrl();
    if (url !== lastUrl) {
      lastUrl = url;
      requestVersion++;
      lastRequest = "";
      selectedText = "";
      dismissed = false;
      setStatus("");
      setQuote("");
      renderNotes([]);
    }
    const supported = isReadingUrl(url);
    launcher.hidden = !supported;
    if (!supported) { panel.hidden = true; return; }

    const source = sourceInfo();
    const payload = { source_url: url, title: source.title.slice(0, 240), selection: selectedText };
    const signature = JSON.stringify(payload);
    if (!force && signature === lastRequest) return;
    lastRequest = signature;
    const version = ++requestVersion;
    sourceTitle.textContent = source.title || "当前知乎内容";
    sourceMeta.textContent = `${source.author_name || "未识别作者"} · ${source.source_url}`;
    try {
      const result = await send({ type: "recallBubbles", payload });
      if (version === requestVersion && cleanUrl() === url) renderNotes(result.items || []);
    } catch (error) {
      if (version !== requestVersion || cleanUrl() !== url) return;
      renderNotes([]);
      if (!panel.hidden) setStatus(error.message, true);
    }
  }

  function togglePanel(open, fromRecall = false) {
    panel.hidden = !open;
    if (!panel.hidden) {
      recall.hidden = true;
      setQuote();
      if (fromRecall && !related.hidden) {
        related.scrollIntoView({ block: "nearest" });
        notes.querySelector("a")?.focus({ preventScroll: true });
      } else {
        body.focus();
      }
      void refreshContext(!fromRecall);
    }
  }
  launcher.addEventListener("click", () => togglePanel(panel.hidden));
  recallOpen.addEventListener("click", () => { dismissed = true; togglePanel(true, true); });
  recallDismiss.addEventListener("click", () => { dismissed = true; recall.hidden = true; });
  close.addEventListener("click", () => { togglePanel(false); launcher.focus(); });
  quoteButton.addEventListener("click", () => setQuote());
  function selectExcerpt(event) {
    if (event.composedPath().includes(host) || !isReadingUrl(cleanUrl())) return;
    const selection = window.getSelection();
    if (selection?.anchorNode?.getRootNode() !== document || selection.focusNode?.getRootNode() !== document) return;
    const excerpt = selectionText();
    if (!excerpt) return;
    if (!panel.hidden) setQuote(excerpt);
    const next = excerpt.slice(0, 400);
    if (next !== selectedText && cleanUrl() === lastUrl) {
      selectedText = next;
      void refreshContext();
    }
  }
  document.addEventListener("mouseup", selectExcerpt);
  document.addEventListener("keyup", event => { if (event.shiftKey) selectExcerpt(event); });

  save.addEventListener("click", async () => {
    const value = body.value.trim();
    if (!value) {
      setStatus("先写下一点想法再保存。", true);
      return;
    }
    save.disabled = true;
    setStatus("正在保存…");
    try {
      const source = sourceInfo();
      await send({
        type: "saveBubble",
        payload: { ...source, body: value, quote: quote.hidden ? "" : quote.textContent },
      });
      if (cleanUrl() !== source.source_url) return;
      body.value = "";
      setStatus("已保存，并已关联到这篇文章。");
      await refreshContext(true);
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      save.disabled = false;
    }
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local" || !changes.extensionToken) return;
    requestVersion++;
    lastRequest = "";
    renderNotes([]);
    if (changes.extensionToken.newValue) void refreshContext();
  });
  window.setInterval(() => { void refreshContext(); }, 1200);
  void refreshContext();
})();
