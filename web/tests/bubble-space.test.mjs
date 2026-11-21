import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/bubble-space.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { sampleNotes, fromSavedBubble, safeSourceUrl, filterNotes, sceneItems, connectionDraft } = await import("data:text/javascript;base64," + Buffer.from(compiled).toString("base64"));

test("saved bubbles retain user text, quote and source without creating demo records", () => {
  const bubble = { id: "saved", body: "真实手记\n第二行", title: "文章", quote: "选中引用", source_url: "https://www.zhihu.com/question/1/answer/2", created_at: 100 };
  assert.deepEqual(fromSavedBubble(bubble), { id: "saved", text: bubble.body, source: "文章", quote: "选中引用", url: bubble.source_url, createdAt: 100 });
  assert.equal(fromSavedBubble({ ...bubble, title: "" }).source, "阅读手记");
  assert.deepEqual(filterNotes([], "", false, new Set()), []);
});

test("source links accept HTTPS Zhihu pages and reject executable or misleading URLs", () => {
  for (const value of ["javascript:alert(1)", "http://zhihu.com/question/1", "https://zhihu.com.attacker.test", "https://evilzhihu.com", "not a URL"]) assert.equal(safeSourceUrl(value), undefined);
  assert.equal(safeSourceUrl("https://zhuanlan.zhihu.com/p/1"), "https://zhuanlan.zhihu.com/p/1");
});

test("search and draft filters preserve hidden parents for undo without mutating records", () => {
  const notes = [...structuredClone(sampleNotes), connectionDraft(sampleNotes[0], sampleNotes[1], "新的连接", "child")];
  const before = JSON.stringify(notes), folded = new Set([sampleNotes[0].id, sampleNotes[1].id]);
  assert.equal(filterNotes(notes, "", false, folded).length, 5);
  assert.deepEqual(filterNotes(notes, " 新的连接 ", true, folded).map(n => n.id), ["child"]);
  assert.equal(filterNotes(notes, "关于阅读", false, folded).length, 0);
  assert.equal(filterNotes(notes, "知识的价值", false, new Set()).length, 1);
  assert.equal(JSON.stringify(notes), before);
});

test("connections require authored text and keep their original parents intact", () => {
  const [a, b] = structuredClone(sampleNotes), before = JSON.stringify([a, b]);
  const draft = connectionDraft(a, b, "  自己写的新观点  ", "new");
  assert.deepEqual(draft.parents, [a.id, b.id]); assert.equal(draft.text, "自己写的新观点");
  assert.equal(draft.generated, true); assert.equal(JSON.stringify([a, b]), before);
  assert.throws(() => connectionDraft(a, b, " ", "new"));
  assert.throws(() => connectionDraft(a, b, "a".repeat(4001), "new"));
  assert.throws(() => connectionDraft(a, a, "观点", "new"));
});

test("a scene bounds the GPU workload and scales its radii to narrow viewports", () => {
  const notes = Array.from({ length: 30 }, (_, i) => ({ id: String(i), text: "文本", source: "来源" }));
  assert.equal(sceneItems(notes).length, 6);
  const mobile = sceneItems(notes.slice(0, 4), 340, 500), desktop = sceneItems(notes.slice(0, 6), 1000, 650);
  assert.ok(mobile.every(n => n.radius < 70)); assert.ok(desktop.every(n => n.radius >= 99));
  assert.ok(mobile.every(n => n.x > 0 && n.x < 1 && n.y > 0 && n.y < 1));
  assert.equal(notes[0].radius, undefined);
});
