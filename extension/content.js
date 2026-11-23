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
    <button class="ts-launcher" type="button" aria-label="打开 ThinkSpace 灵感泡泡">
      <span class="ts-dot"></span><span>想法</span><span class="ts-count" hidden>0</span>
    </button>
    <section class="ts-panel" hidden aria-label="ThinkSpace 灵感泡泡">
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
        <section class="ts-related" hidden><h3>这篇文章已有的泡泡</h3><div class="ts-notes"></div></section>
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

  let lastUrl = "";
  let knownCount = 0;

  function send(message) {
    return chrome.runtime.sendMessage(message).then((response) => {
      if (!response?.ok) throw new Error(response?.error || "无法连接 ThinkSpace。请点击扩展图标完成配对。");
      return response.data;
    });
  }

  function text(selectors) {
    for (const selector of selectors) {
      const value = document.querySelector(selector)?.textContent?.trim();
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
    knownCount = items.length;
    count.hidden = items.length === 0;
    count.textContent = String(items.length);
    related.hidden = items.length === 0;
    notes.replaceChildren();
    items.slice(0, 3).forEach((item) => {
      const note = document.createElement("div");
      note.className = "ts-note";
      note.textContent = item.body;
      const time = document.createElement("time");
      time.textContent = new Date(item.created_at * 1000).toLocaleString("zh-CN");
      note.appendChild(time);
      notes.appendChild(note);
    });
  }

  async function refreshContext() {
    const source = sourceInfo();
    if (source.source_url === lastUrl) return;
    lastUrl = source.source_url;
    sourceTitle.textContent = source.title || "当前知乎内容";
    sourceMeta.textContent = `${source.author_name || "未识别作者"} · ${source.source_url}`;
    setQuote();
    try {
      const result = await send({ type: "getBubbles", sourceUrl: source.source_url });
      renderNotes(result.items || []);
    } catch (error) {
      knownCount = 0;
      count.hidden = true;
      related.hidden = true;
      if (!panel.hidden) setStatus(error.message, true);
    }
  }

  launcher.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) {
      refreshContext().then(() => body.focus());
      setQuote();
    }
  });
  close.addEventListener("click", () => { panel.hidden = true; });
  quoteButton.addEventListener("click", () => setQuote());
  document.addEventListener("mouseup", () => {
    if (!panel.hidden && selectionText()) setQuote();
  });

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
      body.value = "";
      setStatus("已保存，并已关联到这篇文章。");
      const previous = lastUrl;
      lastUrl = "";
      await refreshContext();
      lastUrl = previous;
      const result = await send({ type: "getBubbles", sourceUrl: source.source_url });
      renderNotes(result.items || []);
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      save.disabled = false;
    }
  });

  window.setInterval(() => {
    if (location.href.split("#")[0] !== lastUrl.split("#")[0]) void refreshContext();
  }, 1200);
  void refreshContext();
})();
