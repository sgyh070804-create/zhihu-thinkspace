import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/branches.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { createExploration, createSampleDraft, addBranch, ancestry, layoutTree, parseDraft, exportPath, MAX_NODES, suggestConditions, suggestBranchChanges } = await import("data:text/javascript;base64," + Buffer.from(compiled).toString("base64"));

test("condition suggestions use the question first and fall back to linked context", () => {
  assert.equal(suggestConditions("读研还是就业？", "阅读策略")[0].label, "资金条件");
  assert.equal(suggestConditions("如何取舍？", "阅读策略")[0].label, "阅读目标");
  assert.equal(suggestConditions("如何取舍？")[0].label, "适用对象");
});

test("a branch suggestion fills one editable condition without modifying the parent", () => {
  const topic = "围绕阅读".repeat(45);
  const exploration = createExploration(topic, suggestConditions(topic));
  const root = exploration.nodes[0], original = structuredClone(root);
  const suggestion = suggestBranchChanges(root)[1];
  assert.equal(suggestion.value, "阅读时间有限");
  assert.ok(suggestion.question.length <= 180);
  assert.deepEqual(root, original);
  const child = addBranch(exploration, root.id, suggestion.key, suggestion.value, suggestion.question);
  assert.equal(child.conditions.filter((condition, i) => condition.value !== root.conditions[i].value).length, 1);
});

test("a branch changes exactly one condition and never mutates its parent", () => {
  const exploration = createExploration("是否交给 AI 决定？"), root = exploration.nodes[0];
  const before = structuredClone(root);
  const branch = addBranch(exploration, root.id, "reversal", "无法撤回", "无法撤回时呢？");
  assert.deepEqual(root, before);
  assert.equal(branch.conditions.filter((c, i) => c.value !== root.conditions[i].value).length, 1);
  assert.deepEqual(branch.change, { key: "reversal", label: "可撤回性", before: "决定可以撤回", after: "无法撤回" });
  assert.throws(() => addBranch(exploration, root.id, "scope", "只影响自己", "未改变条件"));
  assert.equal(exploration.nodes.length, 2);
});

test("a descendant inherits only its own ancestry, preserving sibling judgments", () => {
  const exploration = createExploration("决策问题"), root = exploration.nodes[0];
  const a = addBranch(exploration, root.id, "reversal", "不能撤回", "情境 A");
  a.judgment = "这一步的独立判断"; a.confirmed = true;
  const b = addBranch(exploration, root.id, "scope", "影响他人", "情境 B");
  const child = addBranch(exploration, b.id, "control", "无法否决", "情境 B 的继续");
  assert.equal(child.conditions.find(c => c.key === "reversal").value, "决定可以撤回");
  assert.equal(child.conditions.find(c => c.key === "scope").value, "影响他人");
  assert.deepEqual(ancestry(exploration.nodes, child.id).map(n => n.id), [root.id, b.id, child.id]);
  assert.equal(a.judgment, "这一步的独立判断"); assert.equal(a.confirmed, true);
});

test("saved explorations round-trip custom conditions and reject corrupt paths", () => {
  const draft = createSampleDraft();
  const custom = createExploration("读研还是就业？", [{ key: "a", label: "经济条件", value: "有奖学金" }, { key: "b", label: "研究兴趣", value: "兴趣明确" }, { key: "c", label: "就业机会", value: "已有录用" }]);
  addBranch(custom, custom.nodes[0].id, "a", "没有奖学金", "经济条件改变后呢？");
  draft.explorations.push(custom); draft.activeId = custom.id;
  assert.deepEqual(parseDraft(JSON.stringify(draft)), draft);
  const cycle = structuredClone(draft); cycle.explorations[0].nodes[0].parentId = cycle.explorations[0].nodes[1].id;
  assert.throws(() => parseDraft(JSON.stringify(cycle)));
  const mixed = structuredClone(draft); mixed.explorations[0].nodes[1].conditions[0].value = "同时改变另一个条件";
  assert.throws(() => parseDraft(JSON.stringify(mixed)));
  const renamed = structuredClone(draft); renamed.explorations[0].nodes[1].conditions[0].label = "偷偷换了定义";
  assert.throws(() => parseDraft(JSON.stringify(renamed)));
  assert.throws(() => parseDraft('{"version":2}'));
});

test("collapsing a branch hides descendants without deleting saved work", () => {
  const exploration = createSampleDraft().explorations[0];
  const parent = exploration.nodes.find(n => n.conditions.find(c => c.key === "control").value === "无法人工否决" && n.change?.key === "control");
  const saved = JSON.stringify(exploration.nodes);
  const expanded = layoutTree(exploration.nodes, new Set());
  const collapsed = layoutTree(exploration.nodes, new Set([parent.id]));
  assert.equal(expanded.positions.length, 5); assert.equal(collapsed.positions.length, 4);
  assert.equal(JSON.stringify(exploration.nodes), saved);
  assert.ok(collapsed.positions.every(p => Number.isFinite(p.x) && Number.isFinite(p.y)));
});

test("path export contains confirmed user reasoning and excludes unrelated branches", () => {
  const exploration = createSampleDraft().explorations[0], selected = exploration.nodes.find(n => n.id === exploration.selectedId);
  selected.judgment = "需要先由我确认。\n仍有疑问。"; selected.stance = "视条件而定"; selected.confirmed = true;
  const output = exportPath(exploration, selected.id);
  assert.match(output, /视条件而定（已确认）/); assert.match(output, /需要先由我确认。\n仍有疑问。/);
  assert.doesNotMatch(output, /当决定也影响他人时/); assert.match(output, /未调用 AI/);
});

test("node limit rejects a new branch without damaging earlier work", () => {
  const exploration = createExploration("问题"), root = exploration.nodes[0];
  while (exploration.nodes.length < MAX_NODES) addBranch(exploration, root.id, "scope", `影响情境 ${exploration.nodes.length}`, "条件变化后怎么想？");
  const before = JSON.stringify(exploration);
  assert.throws(() => addBranch(exploration, root.id, "scope", "新的情境", "问题"), /64/);
  assert.equal(JSON.stringify(exploration), before);
});
