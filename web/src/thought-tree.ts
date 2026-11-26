export type BranchType = "analysis" | "association" | "hypothesis" | "counterexample" | "projection";

export type BranchCandidate = {
  title: string;
  content: string;
  relation: string;
  type: BranchType;
};

export type TreeNode = {
  id: string;
  parent_id: string | null;
  title: string;
  content: string;
  annotation: string;
  relation: string;
  type: BranchType | null;
};

export type TreeSummary = { id: string; title: string; source_id: string | null; updated_at: number };
export type ThoughtTree = TreeSummary & { version: number; nodes: TreeNode[]; links: Record<string, string> };

export const treeNodeLimit = 96;

export function nodeTitle(content: string) {
  return Array.from(content.trim().split(/\r?\n/, 1)[0]).slice(0, 42).join("");
}

export function nodePath(nodes: TreeNode[], nodeId: string) {
  const byId = new Map(nodes.map(node => [node.id, node]));
  const path: TreeNode[] = [];
  let node = byId.get(nodeId);
  while (node) {
    path.unshift(node);
    node = node.parent_id ? byId.get(node.parent_id) : undefined;
  }
  return path;
}

export function removeSubtree(nodes: TreeNode[], rootId: string): TreeNode[] {
  const removed = new Set([rootId]);
  return nodes.filter(node => {
    if (node.parent_id && removed.has(node.parent_id)) removed.add(node.id);
    return !removed.has(node.id);
  });
}
