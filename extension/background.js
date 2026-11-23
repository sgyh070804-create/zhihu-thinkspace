const DEFAULT_API_BASE = "http://localhost:8000";

async function settings() {
  const data = await chrome.storage.local.get(["apiBase", "extensionToken"]);
  return {
    apiBase: (data.apiBase || DEFAULT_API_BASE).replace(/\/$/, ""),
    extensionToken: data.extensionToken || "",
  };
}

async function request(path, options = {}, authenticated = true) {
  const config = await settings();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (authenticated) {
    if (!config.extensionToken) {
      throw new Error("尚未连接 ThinkSpace，请点击扩展图标完成配对。");
    }
    headers.Authorization = `Bearer ${config.extensionToken}`;
  }
  const response = await fetch(`${config.apiBase}/api${path}`, {
    ...options,
    headers,
  });
  const payload = response.status === 204 ? {} : await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && authenticated) {
      await chrome.storage.local.remove("extensionToken");
    }
    const detail = payload.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message || "ThinkSpace 请求失败。");
  }
  return payload;
}

async function handle(message) {
  if (message.type === "pair") {
    await chrome.storage.local.set({ apiBase: message.apiBase || DEFAULT_API_BASE });
    const result = await request(
      "/extension/exchange",
      { method: "POST", body: JSON.stringify({ code: message.code }) },
      false,
    );
    await chrome.storage.local.set({ extensionToken: result.extension_token });
    return { ok: true };
  }
  if (message.type === "status") {
    const config = await settings();
    return { connected: Boolean(config.extensionToken), apiBase: config.apiBase };
  }
  if (message.type === "saveBubble") {
    return request("/bubbles", { method: "POST", body: JSON.stringify(message.payload) });
  }
  if (message.type === "getBubbles") {
    return request(`/bubbles?source_url=${encodeURIComponent(message.sourceUrl)}`);
  }
  throw new Error("未知扩展请求。");
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  handle(message)
    .then((data) => sendResponse({ ok: true, data }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});
