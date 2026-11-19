import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const code = ts.transpileModule(readFileSync(new URL("../src/api.ts", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { api, ApiError } = await import("data:text/javascript;base64," + Buffer.from(code).toString("base64"));

test("API preserves session credentials, cancellation and JSON body headers", async t => {
  const controller = new AbortController(); let sent;
  t.mock.method(globalThis, "fetch", async (url, options) => { sent = { url, ...options }; return Response.json({ ok: true }); });
  assert.deepEqual(await api("/bubbles", { method: "POST", body: "{}", signal: controller.signal }), { ok: true });
  assert.equal(sent.url, "/api/bubbles"); assert.equal(sent.credentials, "include"); assert.equal(sent.signal, controller.signal); assert.equal(sent.headers.get("Content-Type"), "application/json");
});

test("successful empty delete response is accepted", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 204 }));
  assert.equal(await api("/bubbles/id", { method: "DELETE" }), undefined);
});

test("HTML fallback or unavailable backend is an actionable error, not an empty successful object", async t => {
  const stub = t.mock.method(globalThis, "fetch", async () => new Response("<html>app fallback</html>"));
  await assert.rejects(api("/auth/status"), error => error instanceof ApiError && error.code === "INVALID_API_RESPONSE");
  stub.mock.mockImplementation(async () => new Response("backend unavailable", { status: 502 }));
  await assert.rejects(api("/auth/status"), error => error.code === "API_UNAVAILABLE" && error.status === 502);
});

test("backend structured errors retain their code and readable message", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: { code: "AUTH_REQUIRED", message: "请先登录" } }, { status: 401 }));
  await assert.rejects(api("/articles"), error => error instanceof ApiError && error.code === "AUTH_REQUIRED" && error.message === "请先登录");
});
