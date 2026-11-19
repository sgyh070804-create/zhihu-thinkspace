import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const compiled = ts.transpileModule(readFileSync(new URL("../src/request-scope.ts", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { RequestScope } = await import("data:text/javascript;base64," + Buffer.from(compiled).toString("base64"));

test("slow old response cannot replace the last selected article even if abort is ignored", async () => {
  const scope = new RequestScope(); let displayed = "", complete;
  const old = scope.begin();
  const delayed = new Promise(resolve => { complete = resolve; }).then(() => { if (old.isCurrent()) displayed = "old article"; });
  const latest = scope.begin(); assert.equal(old.signal.aborted, true);
  if (latest.isCurrent()) displayed = "selected article";
  complete(); await delayed;
  assert.equal(displayed, "selected article");
});

test("logout/unmount invalidation blocks late private data and obsolete error handlers", async () => {
  const scope = new RequestScope(), request = scope.begin(); let privateData = null, error = null;
  scope.invalidate();
  await Promise.resolve().then(() => { if (request.isCurrent()) privateData = "previous user data"; }).catch(reason => { if (request.isCurrent()) error = reason; });
  assert.equal(privateData, null); assert.equal(error, null); assert.equal(request.signal.aborted, true);
  const nextUser = scope.begin(); assert.equal(nextUser.isCurrent(), true); assert.equal(request.isCurrent(), false);
});
