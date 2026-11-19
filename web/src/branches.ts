export type Condition = { key: string; label: string; value: string };
export type BranchNode = {
  id: string; parentId: string | null; title: string; question: string;
  conditions: Condition[];
  change: { key: string; label: string; before: string; after: string } | null;
  judgment: string; stance: string; confirmed: boolean; origin: "sample" | "user";
};
export type Exploration = { id: string; topic: string; nodes: BranchNode[]; selectedId: string };
export type BranchDraft = { version: 1; activeId: string; explorations: Exploration[] };
export const STORAGE_KEY = "thinkspace:thought-branches:v1";
export const MAX_NODES = 64;
export const STANCES = ["尚未判断", "倾向接受", "倾向不接受", "视条件而定", "保留疑问"];
export const initialConditions: Condition[] = [
  { key: "scope", label: "影响范围", value: "只影响自己" },
  { key: "reversal", label: "可撤回性", value: "决定可以撤回" },
  { key: "control", label: "人工否决", value: "保留人工否决权" },
];

export function createExploration(topic: string, conditions = initialConditions): Exploration {
  if (!topic.trim() || topic.trim().length > 180) throw new Error("请填写 1–180 字的问题。");
  if (conditions.length !== 3 || new Set(conditions.map(c => c.key)).size !== 3 || new Set(conditions.map(c => c.label.trim())).size !== 3 || conditions.some(c => !c.label.trim() || c.label.length > 24 || !c.value.trim() || c.value.length > 120)) throw new Error("请填写三个不同的起始条件，名称最多 24 字，内容最多 120 字。");
  const id = crypto.randomUUID(), rootId = crypto.randomUUID();
  return { id, topic: topic.trim(), selectedId: rootId, nodes: [{
    id: rootId, parentId: null, title: "起始情境", question: topic.trim(),
    conditions: conditions.map(c => ({ ...c, label: c.label.trim(), value: c.value.trim() })), change: null,
    judgment: "", stance: STANCES[0], confirmed: false, origin: "user",
  }] };
}

export function addBranch(exploration: Exploration, parentId: string, key: string, after: string, question: string): BranchNode {
  const parent = exploration.nodes.find(n => n.id === parentId);
  if (!parent) throw new Error("找不到分叉的起点。");
  if (exploration.nodes.length >= MAX_NODES) throw new Error("当前探索已达到 64 个情境，请新建探索。");
  const condition = parent.conditions.find(c => c.key === key);
  if (!condition) throw new Error("请选择已有的一个条件。");
  if (!after.trim() || after.trim().length > 120 || after.trim() === condition.value) throw new Error("请填写与原条件不同的新条件，最多 120 字。");
  if (!question.trim() || question.trim().length > 180) throw new Error("请填写 1–180 字的分支问题。");
  const node: BranchNode = {
    id: crypto.randomUUID(), parentId, title: after.trim(), question: question.trim(),
    conditions: parent.conditions.map(c => ({ ...c, value: c.key === key ? after.trim() : c.value })),
    change: { key, label: condition.label, before: condition.value, after: after.trim() },
    judgment: "", stance: STANCES[0], confirmed: false, origin: "user",
  };
  exploration.nodes.push(node);
  exploration.selectedId = node.id;
  return node;
}

export function createSampleDraft(): BranchDraft {
  const exploration = createExploration("AI 可以替我做决定吗？");
  const root = exploration.nodes[0];
  const irreversible = addBranch(exploration, root.id, "reversal", "决定无法撤回", "如果决定无法撤回，你还愿意让 AI 代为决定吗？");
  addBranch(exploration, root.id, "scope", "也会影响他人", "当决定也影响他人时，你的判断会改变吗？");
  const control = addBranch(exploration, root.id, "control", "无法人工否决", "如果你无法否决 AI 的决定，你还能接受吗？");
  addBranch(exploration, control.id, "reversal", "决定无法撤回", "既不能否决、也无法撤回时，你会怎样判断？");
  exploration.nodes.forEach(n => { n.origin = "sample"; });
  exploration.selectedId = irreversible.id;
  return { version: 1, activeId: exploration.id, explorations: [exploration] };
}

export function ancestry(nodes: BranchNode[], id: string): BranchNode[] {
  const result: BranchNode[] = [], visited = new Set<string>();
  let node = nodes.find(n => n.id === id);
  while (node) {
    if (visited.has(node.id)) throw new Error("情境路径存在循环。");
    visited.add(node.id); result.unshift(node);
    if (node.parentId === null) break;
    node = nodes.find(n => n.id === node!.parentId);
    if (!node) throw new Error("情境路径缺少父节点。");
  }
  return result;
}

export function layoutTree(nodes: BranchNode[], collapsed: Set<string>) {
  const positions: { node: BranchNode; x: number; y: number }[] = [];
  let leaf = 0;
  const place = (node: BranchNode, depth: number): number => {
    const children = collapsed.has(node.id) ? [] : nodes.filter(n => n.parentId === node.id);
    const ys = children.map(n => place(n, depth + 1));
    const y = ys.length ? (ys[0] + ys[ys.length - 1]) / 2 : 16 + leaf++ * 78;
    positions.push({ node, x: 36 + depth * 320, y });
    return y;
  };
  const root = nodes.find(n => n.parentId === null);
  if (root) place(root, 0);
  return { positions, width: Math.max(600, ...positions.map(p => p.x + 285)), height: Math.max(180, ...positions.map(p => p.y + 82)) };
}

// Treat browser storage as untrusted: a broken or older draft must not silently replace saved work.
export function parseDraft(raw: string): BranchDraft {
  const draft = JSON.parse(raw);
  const validText = (s: unknown, max: number) => typeof s === "string" && s.length <= max;
  if (draft.version !== 1 || !Array.isArray(draft.explorations) || !draft.explorations.length || draft.explorations.length > 30) throw new Error("草稿版本或结构不支持。");
  const ids = new Set<string>();
  for (const exploration of draft.explorations as Exploration[]) {
    if (!validText(exploration.id, 80) || ids.has(exploration.id) || !validText(exploration.topic, 180) || !exploration.topic.trim()) throw new Error("探索信息损坏。");
    ids.add(exploration.id);
    if (!Array.isArray(exploration.nodes) || !exploration.nodes.length || exploration.nodes.length > MAX_NODES) throw new Error("情境数量不支持。");
    const nodeIds = new Set<string>();
    for (const node of exploration.nodes) {
      if (!validText(node.id, 80) || nodeIds.has(node.id) || !validText(node.title, 180) || !validText(node.question, 180) || !node.question.trim() || !validText(node.judgment, 4000) || !STANCES.includes(node.stance) || typeof node.confirmed !== "boolean" || !["sample", "user"].includes(node.origin)) throw new Error("情境信息损坏。");
      nodeIds.add(node.id);
      if (!Array.isArray(node.conditions) || node.conditions.length !== 3 || new Set(node.conditions.map(c => c.key)).size !== 3 || node.conditions.some(c => !validText(c.key, 80) || !validText(c.label, 24) || !c.label.trim() || !validText(c.value, 120) || !c.value.trim())) throw new Error("情境条件损坏。");
    }
    if (exploration.nodes.filter(n => n.parentId === null).length !== 1 || !nodeIds.has(exploration.selectedId)) throw new Error("起点或选中情境损坏。");
    for (const node of exploration.nodes) {
      ancestry(exploration.nodes, node.id);
      if (node.parentId === null) { if (node.change !== null) throw new Error("起始条件损坏。"); continue; }
      const parent = exploration.nodes.find(n => n.id === node.parentId)!;
      if (node.conditions.some((c, i) => c.key !== parent.conditions[i].key || c.label !== parent.conditions[i].label)) throw new Error("分支不能改变条件的定义。");
      const differences = node.conditions.filter((c, i) => c.value !== parent.conditions[i].value);
      const change = node.change;
      if (differences.length !== 1 || !change || change.key !== differences[0].key || change.label !== differences[0].label || change.after !== differences[0].value || change.before !== parent.conditions.find(c => c.key === change.key)?.value) throw new Error("分支必须只改变一个条件。");
    }
  }
  if (!ids.has(draft.activeId)) throw new Error("当前探索损坏。");
  return draft as BranchDraft;
}

export function exportPath(exploration: Exploration, nodeId: string): string {
  return [`# ${exploration.topic}`, "", "本机思考草稿；情境由示例或用户填写，未调用 AI。", "", ...ancestry(exploration.nodes, nodeId).flatMap((node, i) => [
    `## ${i === 0 ? "起始情境" : node.title}`, node.question, "",
    ...node.conditions.map(c => `- ${c.label}：${c.value}`), "",
    `判断：${node.stance}（${node.confirmed ? "已确认" : "待确认"}）`, node.judgment || "尚未记录理由。", "",
  ])].join("\n");
}
