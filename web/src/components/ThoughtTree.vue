<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from "vue";
import { api, ApiError } from "../api";
import { RequestScope } from "../request-scope";
import { thoughtLink } from "../thought-library";
import { nodePath, nodeTitle, removeSubtree, treeNodeLimit } from "../thought-tree";
import type { BranchCandidate, ThoughtTree, TreeNode, TreeSummary } from "../thought-tree";
import type { ThoughtRecord } from "../types";
import BranchIcon from "./BranchIcon.vue";
import ThoughtTreeCanvas from "./ThoughtTreeCanvas.vue";
import "../thought-branches.css";
import "../thought-tree.css";

const props = defineProps<{ sourceId?: string; authenticated: boolean }>();
const initial = new URLSearchParams(location.search);
const trees = ref<TreeSummary[]>([]);
const tree = shallowRef<ThoughtTree>();
const selectedId = ref(""), rootText = ref("");
const busy = ref(false), loading = ref(false), generating = ref(false);
const error = ref(""), generationError = ref(""), notice = ref("");
const conflict = ref(false);
const request = new RequestScope(), generation = new RequestScope();
const candidates = ref<BranchCandidate[]>([]), references = ref(""), noCandidates = ref(false);
const selected = computed(() => tree.value?.nodes.find(node => node.id === selectedId.value));
const path = computed(() => tree.value ? nodePath(tree.value.nodes, selectedId.value) : []);
const children = computed(() => tree.value?.nodes.filter(node => node.parent_id === selectedId.value) || []);
const linkedId = computed(() => selected.value && tree.value
  ? tree.value.links[selected.value.id] || (!selected.value.parent_id ? tree.value.source_id : null) : null);
const full = computed(() => (tree.value?.nodes.length || 0) >= treeNodeLimit);
const history = shallowRef<{ nodes: TreeNode[]; selectedId: string }[]>([]);
const editor = ref<HTMLDialogElement>(), confirmDelete = ref<HTMLDialogElement>();
const editorKind = ref<"branch" | "annotation" | "candidate">("branch");
const draftTitle = ref(""), draftContent = ref(""), draftRelation = ref("");
const editingCandidate = ref<BranchCandidate>();
const editorError = ref("");
let rootRequestId = "";

function post<T>(url: string, data: object, signal?: AbortSignal) {
  return api<T>(url, { method: "POST", body: JSON.stringify(data), signal });
}
function message(reason: unknown) { return reason instanceof ApiError ? reason.message : "请求失败，请稍后重试。"; }
function report(reason: unknown) {
  conflict.value = reason instanceof ApiError && reason.status === 409;
  error.value = message(reason);
}
function syncUrl() {
  const url = new URL(location.href);
  if (tree.value) {
    url.searchParams.set("tree", tree.value.id);
    url.searchParams.set("node", selectedId.value);
    url.searchParams.delete("thought");
  } else {
    url.searchParams.delete("tree");
    url.searchParams.delete("node");
    url.searchParams.delete("thought");
  }
  window.history.replaceState(window.history.state, "", url);
}
function clearCandidates() {
  generation.invalidate();
  candidates.value = []; references.value = ""; generating.value = false;
  generationError.value = ""; noCandidates.value = false;
}
function rememberTree(next: ThoughtTree) {
  const { id, title, source_id, updated_at } = next;
  trees.value = [{ id, title, source_id, updated_at }, ...trees.value.filter(item => item.id !== id)];
}
function showTree(next: ThoughtTree, target?: string) {
  tree.value = next;
  selectedId.value = next.nodes.find(node => node.id === target)?.id || next.nodes[0].id;
  history.value = []; clearCandidates(); syncUrl();
}
function selectNode(id: string) {
  if (busy.value || id === selectedId.value) return;
  selectedId.value = id; clearCandidates(); syncUrl();
}
async function loadTree(id: string, target?: string) {
  if (busy.value) return;
  const task = request.begin();
  loading.value = true; error.value = ""; conflict.value = false; notice.value = ""; clearCandidates();
  try {
    const next = await api<ThoughtTree>("/thought-trees/" + id, { signal: task.signal });
    if (task.isCurrent()) showTree(next, target);
  } catch (reason) { if (task.isCurrent()) report(reason); }
  finally { if (task.isCurrent()) loading.value = false; }
}
async function openWorkspace() {
  if (!props.authenticated) return;
  const task = request.begin();
  loading.value = true; error.value = "";
  try {
    const result = await api<{ items: TreeSummary[] }>("/thought-trees", { signal: task.signal });
    if (!task.isCurrent()) return;
    trees.value = result.items;
    if (props.sourceId) {
      const next = await post<ThoughtTree>("/thought-trees", { source_id: props.sourceId, request_id: crypto.randomUUID() }, task.signal);
      if (task.isCurrent()) { rememberTree(next); showTree(next); }
      return;
    }
    const id = initial.get("tree");
    const next = result.items.find(item => item.id === id) || result.items[0];
    if (next) await loadTree(next.id, id === next.id ? initial.get("node") || "" : undefined);
  } catch (reason) { if (task.isCurrent()) report(reason); }
  finally { if (task.isCurrent()) loading.value = false; }
}
function newTree() {
  request.invalidate();
  tree.value = undefined; history.value = []; loading.value = false; error.value = ""; conflict.value = false;
  notice.value = ""; rootText.value = ""; rootRequestId = ""; clearCandidates(); syncUrl();
}
async function createRoot() {
  if (!rootText.value.trim() || busy.value || loading.value) return;
  const task = request.begin();
  busy.value = true; error.value = "";
  rootRequestId ||= crypto.randomUUID();
  try {
    const item = await post<ThoughtTree>("/thought-trees", { content: rootText.value, request_id: rootRequestId }, task.signal);
    if (task.isCurrent()) { rememberTree(item); showTree(item); notice.value = "已保存思想树"; }
  } catch (reason) { if (task.isCurrent()) report(reason); }
  finally { if (task.isCurrent()) busy.value = false; }
}

async function saveNodes(nodes: TreeNode[], nextSelection: string, undo = false) {
  const previous = tree.value;
  if (!previous || busy.value || loading.value || conflict.value) return false;
  const sameParent = selectedId.value === nextSelection;
  const task = request.begin();
  generation.invalidate(); generating.value = false;
  busy.value = true; error.value = ""; notice.value = ""; editorError.value = "";
  try {
    const next = await post<ThoughtTree>("/thought-trees/" + previous.id, { version: previous.version, nodes }, task.signal);
    if (!task.isCurrent()) return false;
    const past = { nodes: previous.nodes, selectedId: selectedId.value };
    history.value = undo ? history.value.slice(0, -1) : [...history.value.slice(-19), past];
    tree.value = next; rememberTree(next); selectedId.value = nextSelection;
    if (!sameParent || undo) clearCandidates();
    syncUrl(); notice.value = undo ? "已撤销并保存" : "已保存";
    return true;
  } catch (reason) {
    if (task.isCurrent()) { report(reason); editorError.value = error.value; }
    return false;
  } finally { if (task.isCurrent()) busy.value = false; }
}

function startEditor(kind: typeof editorKind.value, candidate?: BranchCandidate) {
  if (!selected.value || busy.value || conflict.value) return;
  editorKind.value = kind; editorError.value = ""; editingCandidate.value = candidate;
  draftTitle.value = candidate?.title || "";
  draftContent.value = candidate?.content || (kind === "annotation" ? selected.value.annotation : "");
  draftRelation.value = candidate?.relation || "";
  editor.value?.showModal();
}
async function commitEditor() {
  const current = selected.value, document = tree.value;
  if (!current || !document) return;
  if (editorKind.value === "annotation") {
    const nodes = document.nodes.map(node => node.id === current.id ? { ...node, annotation: draftContent.value.trim() } : node);
    if (await saveNodes(nodes, current.id)) { clearCandidates(); editor.value?.close(); }
    return;
  }
  const content = draftContent.value.trim();
  if (full.value || !content) return;
  const candidate = editorKind.value === "candidate" ? editingCandidate.value : undefined;
  const child: TreeNode = {
    id: crypto.randomUUID().replace(/-/g, ""), parent_id: current.id, content, annotation: "",
    title: draftTitle.value.trim() || nodeTitle(content),
    relation: draftRelation.value.trim(), type: candidate?.type || null,
  };
  if (await saveNodes([...document.nodes, child], candidate ? current.id : child.id)) {
    if (candidate) candidates.value = candidates.value.filter(item => item !== candidate);
    editor.value?.close();
  }
}
async function deleteBranch() {
  const current = selected.value;
  if (!tree.value || !current?.parent_id) return;
  if (await saveNodes(removeSubtree(tree.value.nodes, current.id), current.parent_id)) confirmDelete.value?.close();
}
function undo() {
  const last = history.value.at(-1);
  if (last) void saveNodes(last.nodes, last.selectedId, true);
}
async function exportNode() {
  const current = selected.value, document = tree.value;
  if (!current || !document || busy.value || conflict.value) return;
  const task = request.begin();
  busy.value = true; error.value = ""; notice.value = "";
  try {
    const saved = await post<ThoughtRecord>("/thought-trees/" + document.id + "/nodes/" + current.id + "/thought", { version: document.version }, task.signal);
    if (!task.isCurrent()) return;
    tree.value = { ...document, links: { ...document.links, [current.id]: saved.id } };
    notice.value = "已保存到资料库";
  } catch (reason) { if (task.isCurrent()) report(reason); }
  finally { if (task.isCurrent()) busy.value = false; }
}
async function generate() {
  const current = selected.value, document = tree.value;
  if (!current || !document || generating.value || busy.value || full.value || conflict.value) return;
  const task = generation.begin();
  generating.value = true; generationError.value = ""; noCandidates.value = false; candidates.value = [];
  try {
    const result = await post<{ branches: BranchCandidate[] }>(
      "/thought-trees/" + document.id + "/nodes/" + current.id + "/candidates",
      { version: document.version, references: references.value }, task.signal,
    );
    if (task.isCurrent()) { candidates.value = result.branches; noCandidates.value = !result.branches.length; }
  } catch (reason) {
    if (task.isCurrent()) {
      if (reason instanceof ApiError && reason.status === 409) report(reason);
      else generationError.value = message(reason);
    }
  } finally { if (task.isCurrent()) generating.value = false; }
}
function rejectCandidate(index: number) { candidates.value = candidates.value.filter((_, position) => position !== index); }
function chooseCandidate(index: number) {
  const candidate = candidates.value[index];
  if (candidate) startEditor("candidate", candidate);
}
function changeTree(event: Event) {
  const id = (event.target as HTMLSelectElement).value;
  if (id && id !== tree.value?.id) void loadTree(id);
}
function preventClose(event: Event) { if (busy.value) event.preventDefault(); }

onMounted(() => void openWorkspace());
onBeforeUnmount(() => { request.invalidate(); generation.invalidate(); });
</script>

<template>
  <main class="shell free-tree">
    <header class="free-tree-header">
      <div><a class="hub-back" href="/space">思考空间</a><h1>思想树</h1></div>
      <div class="free-tree-nav">
        <a class="hub-back" href="/thought-branches?mode=experiment">控制变量实验</a>
        <button v-if="authenticated && tree" class="hub-action quiet" :disabled="busy || loading" @click="newTree">
          <BranchIcon name="plus" /> 新建思想树
        </button>
      </div>
    </header>

    <div v-if="!authenticated" class="panel free-tree-start">
      <h2>从一条想法开始</h2>
      <p>登录后可保存思想树，在别处继续探索。</p>
      <a class="hub-action primary" href="/account">去登录</a>
    </div>
    <template v-else>
      <div v-if="trees.length" class="free-tree-switch">
        <label for="thought-tree-history">我的思想树</label>
        <select id="thought-tree-history" :value="tree?.id || ''" :disabled="busy || loading" @change="changeTree">
          <option value="" disabled>选择思想树</option>
          <option v-for="item in trees" :key="item.id" :value="item.id">{{ item.title }}</option>
        </select>
      </div>
      <p v-if="loading" role="status">正在读取思想树…</p>
      <div v-if="error" class="error-banner" role="alert">
        <span>{{ error }}</span>
        <button v-if="conflict && tree" @click="loadTree(tree.id, selectedId)">重新载入</button>
        <button v-else-if="!tree && !busy" @click="openWorkspace">重试</button>
      </div>
      <form v-if="!tree && !loading" class="panel free-tree-start" @submit.prevent="createRoot">
        <label for="new-tree-thought"><strong>从一条想法开始</strong></label>
        <textarea id="new-tree-thought" v-model="rootText" rows="4" maxlength="4000" required placeholder="一个问题、一个观点，或者刚冒出来的想法…" @input="rootRequestId = ''"></textarea>
        <button type="submit" class="hub-action primary" :disabled="!rootText.trim() || busy">{{ busy ? "保存中…" : "创建思想树" }}</button>
      </form>

      <template v-if="tree && selected">
        <ThoughtTreeCanvas :key="tree.id" :nodes="tree.nodes" :selected-id="selectedId" :candidates="candidates"
          :disabled="busy || loading" @select="selectNode" @candidate="chooseCandidate"/>
        <section class="panel free-tree-detail" aria-labelledby="free-tree-title">
          <nav v-if="path.length > 1" class="free-tree-trail" aria-label="祖先路径">
            <button v-for="node in path.slice(0, -1)" :key="node.id" type="button"
              :disabled="busy || loading" @click="selectNode(node.id)">{{ node.title }} ›</button>
          </nav>
          <h2 id="free-tree-title">{{ selected.title }}</h2>
          <p v-if="selected.content !== selected.title" class="free-tree-prose">{{ selected.content }}</p>
          <p v-if="selected.relation" class="free-tree-relation">{{ selected.relation }}</p>
          <blockquote v-if="selected.annotation" class="free-tree-prose">{{ selected.annotation }}</blockquote>
          <div v-if="children.length" class="free-tree-children" aria-label="继续已保存分支">
            <button v-for="node in children" :key="node.id" type="button" :disabled="busy || loading" @click="selectNode(node.id)">{{ node.title }} ↗</button>
          </div>
          <div class="free-tree-actions">
            <button class="hub-action primary" :disabled="generating || busy || loading || full || conflict" title="将当前思绪和思考路径发送给知乎直答" @click="generate">{{ generating ? '正在生成…' : 'AI 生成分支' }}</button>
            <button class="hub-action quiet" :disabled="busy || loading || full || conflict" @click="startEditor('branch')">手动添加</button>
            <button class="hub-action quiet" :disabled="busy || loading || conflict" @click="startEditor('annotation')">补充想法</button>
            <button class="hub-action quiet" :disabled="busy || loading || conflict" @click="exportNode">存为独立思绪</button>
          </div>
          <p v-if="full" class="free-tree-relation">已达到 {{ treeNodeLimit }} 个节点，可先保存或删除分支。</p>
          <details :key="selectedId" class="free-tree-references">
            <summary>给 AI 补充参考资料</summary>
            <textarea v-model="references" rows="2" maxlength="2000" :disabled="generating" aria-label="参考资料" placeholder="粘贴愿意发送给知乎直答的内容"></textarea>
          </details>
          <p v-if="generationError" class="warning" role="alert">{{ generationError }}</p>
          <p v-if="noCandidates" role="status">这次没有新的候选方向。</p>
          <section v-if="candidates.length" class="free-tree-candidates" aria-label="AI 候选分支">
            <article v-for="(candidate, index) in candidates" :key="candidate.title" class="free-tree-suggestion">
              <h3>{{ candidate.title }}</h3>
              <p class="free-tree-prose">{{ candidate.content }}</p>
              <p class="free-tree-relation">{{ candidate.relation }}</p>
              <div class="free-tree-actions">
                <button class="hub-action quiet" :disabled="busy || full || conflict" @click="chooseCandidate(index)">修改并采用</button>
                <button class="text-button" :disabled="busy" @click="rejectCandidate(index)">略过</button>
              </div>
            </article>
          </section>
          <footer class="free-tree-footer">
            <p role="status">{{ busy ? '保存中…' : notice || (conflict ? '需要重新载入' : error ? '操作失败' : '已保存') }}</p>
            <div v-if="linkedId" class="free-tree-actions">
              <a class="hub-back" :href="thoughtLink('/library', linkedId)">在资料库查看</a>
              <a class="hub-back" :href="thoughtLink('/thought-bubbles', linkedId)">在思维泡泡查看</a>
            </div>
            <button class="text-button" :disabled="!history.length || busy || loading || conflict" @click="undo">撤销</button>
            <button v-if="selected.parent_id" class="text-button danger" :disabled="busy || conflict" @click="confirmDelete?.showModal()">删除分支</button>
          </footer>
        </section>
      </template>
    </template>

    <dialog ref="editor" class="free-tree-dialog" aria-labelledby="tree-editor-title" @cancel="preventClose">
      <form @submit.prevent="commitEditor">
        <h2 id="tree-editor-title">{{ editorKind === 'annotation' ? '补充想法' : editorKind === 'candidate' ? '编辑候选分支' : '手动添加分支' }}</h2>
        <label v-if="editorKind === 'candidate'">标题<input v-model="draftTitle" maxlength="180" :disabled="busy" /></label>
        <label>内容<textarea v-model="draftContent" rows="6" :maxlength="editorKind === 'annotation' ? 2000 : 4000"
          :required="editorKind !== 'annotation'" :disabled="busy" /></label>
        <label v-if="editorKind === 'candidate'">与父节点的联系<input v-model="draftRelation" maxlength="240" :disabled="busy" /></label>
        <p v-if="editorError" role="alert">{{ editorError }}</p>
        <div class="free-tree-actions">
          <button type="button" class="hub-action quiet" :disabled="busy" @click="editor?.close()">取消</button>
          <button type="submit" class="hub-action primary" :disabled="busy || conflict || (editorKind !== 'annotation' && !draftContent.trim())">{{ editorKind === 'candidate' ? '确认采用' : '保存' }}</button>
        </div>
      </form>
    </dialog>

    <dialog ref="confirmDelete" class="free-tree-dialog" aria-labelledby="tree-delete-title" @cancel="preventClose">
      <form @submit.prevent="deleteBranch">
        <h2 id="tree-delete-title">删除这个分支？</h2>
        <p>将移除这个节点及其下的分支。已存入资料库的思绪会保留。</p>
        <p v-if="error" role="alert">{{ error }}</p>
        <div class="free-tree-actions">
          <button type="button" class="hub-action quiet" :disabled="busy" @click="confirmDelete?.close()">取消</button>
          <button type="submit" class="hub-action primary" :disabled="busy || conflict">确认删除</button>
        </div>
      </form>
    </dialog>
  </main>
</template>
