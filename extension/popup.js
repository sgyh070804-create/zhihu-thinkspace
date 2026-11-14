const apiBaseInput = document.querySelector("#api-base");
const pairCodeInput = document.querySelector("#pair-code");
const statusElement = document.querySelector("#status");

function send(message) {
  return chrome.runtime.sendMessage(message).then((response) => {
    if (!response?.ok) throw new Error(response?.error || "扩展连接失败。");
    return response.data;
  });
}

async function refresh() {
  const config = await send({ type: "status" });
  apiBaseInput.value = config.apiBase;
  statusElement.textContent = config.connected ? "已连接，可以在知乎阅读页使用泡泡。" : "尚未连接";
}

document.querySelector("#connect").addEventListener("click", async () => {
  const code = pairCodeInput.value.trim();
  const apiBase = apiBaseInput.value.trim().replace(/\/$/, "");
  if (!code) {
    statusElement.textContent = "请先粘贴配对码。";
    return;
  }
  try {
    new URL(apiBase);
    statusElement.textContent = "正在连接…";
    await send({ type: "pair", code, apiBase });
    pairCodeInput.value = "";
    statusElement.textContent = "连接成功，可以开始记录泡泡。";
  } catch (error) {
    statusElement.textContent = error.message;
  }
});

refresh().catch((error) => {
  statusElement.textContent = error.message;
});
