export class ApiError extends Error {
  code: string;
  status: number;

  constructor(message: string, status: number, code = "API_ERROR") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (response.status === 204) {
    return undefined as T;
  }
  let payload;
  try { payload = await response.json(); }
  catch (reason) {
    if (options.signal?.aborted) throw reason;
    if (!response.ok) throw new ApiError("服务暂时不可用，请确认后端已启动或稍后重试。", response.status, "API_UNAVAILABLE");
    throw new ApiError("服务返回了无法识别的内容，请检查 API 地址或稍后重试。", response.status, "INVALID_API_RESPONSE");
  }
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === "string" ? detail : detail?.message || "请求失败，请稍后重试。";
    const code = typeof detail === "object" ? detail?.code : "API_ERROR";
    throw new ApiError(message, response.status, code);
  }
  return payload as T;
}
