<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import BranchIcon from "./BranchIcon.vue";
import { addBranch, ancestry, createExploration, createSampleDraft, exportPath, initialConditions, layoutTree, parseDraft, STANCES, STORAGE_KEY } from "../branches";
import type { BranchDraft, BranchNode } from "../branches";
import type { ThoughtRecord } from "../types";
import ThoughtResultForm from "./ThoughtResultForm.vue";

const props = defineProps<{ thought?: ThoughtRecord }>();
const linkedExploration = props.thought ? createExploration(
  (props.thought.body.length <= 180 ? props.thought.body : props.thought.title).trim() || "这条思绪",
  [
    { key: "subject", label: "适用对象", value: "沿用原问题的对象" },
    { key: "period", label: "时间范围", value: "沿用原问题的时间范围" },
    { key: "context", label: "外部条件", value: "沿用原问题的外部条件" },
  ],
) : undefined;
const draft = ref<BranchDraft>(linkedExploration
  ? { version: 1, activeId: linkedExploration.id, explorations: [linkedExploration] }
  : createSampleDraft());
const storageError = ref(""), notice = ref(""), storageBlocked = ref(false);
try {
  const saved = props.thought ? null : localStorage.getItem(STORAGE_KEY);
  if (saved) draft.value = parseDraft(saved);
} catch {
  storageBlocked.value = true;
  storageError.value = "本机草稿暂时无法读取，已保留原数据。当前可继续探索并导出，暂不覆盖本机草稿。";
}
const current = computed(() => draft.value.explorations.find(e => e.id === draft.value.activeId)!);
const selected = computed(() => current.value.nodes.find(n => n.id === current.value.selectedId)!);
const path = computed(() => ancestry(current.value.nodes, selected.value.id));
const collapsed = ref(new Set<string>()), comparison = ref<string[]>([]);
const layout = computed(() => layoutTree(current.value.nodes, collapsed.value));
const selectedPathIds = computed(() => new Set(path.value.map(n => n.id)));
const comparisonNodes = computed(() => current.value.nodes.filter(n => comparison.value.includes(n.id)));
const connections = computed(() => layout.value.positions.flatMap(position => {
  const parent = layout.value.positions.find(p => p.node.id === position.node.parentId);
  if (!parent) return [];
  const x = parent.x + 252, y = parent.y + 32, endX = position.x, endY = position.y + 32;
  return [{ id: position.node.id, active: selectedPathIds.value.has(position.node.id), d: `M${x},${y} C${x + 40},${y} ${endX - 40},${endY} ${endX},${endY}` }];
}));
const canvas = ref<HTMLElement | null>(null), zoom = ref(1), pan = ref({ x: 0, y: 0 });
const dragging = ref(false);
let drag: { id: number; x: number; y: number; startX: number; startY: number } | null = null;
let resizeObserver: ResizeObserver | undefined, saveTimer: ReturnType<typeof setTimeout> | undefined;

function persist() {
  if (props.thought || storageBlocked.value) return;
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(draft.value)); storageError.value = ""; }
  catch { storageError.value = "本机空间不足或存储不可用，当前修改尚未保存。请先导出备份。"; }
}
watch(draft, () => { clearTimeout(saveTimer); saveTimer = setTimeout(persist, 180); }, { deep: true });

function fit() {
  if (!canvas.value) return;
  const { clientWidth: width, clientHeight: height } = canvas.value;
  const scale = Math.min((width - 48) / layout.value.width, (height - 38) / layout.value.height, 1);
  zoom.value = Math.max(0.3, scale);
  pan.value = { x: (width - layout.value.width * zoom.value) / 2, y: (height - layout.value.height * zoom.value) / 2 };
  if (width < 600 && zoom.value < .7) {
    zoom.value = .7;
    const position = layout.value.positions.find(p => p.node.id === selected.value.id)!;
    pan.value = { x: width / 2 - (position.x + 126) * .7, y: height / 2 - (position.y + 32) * .7 };
  }
}
function zoomBy(amount: number) {
  const width = canvas.value?.clientWidth || 800, height = canvas.value?.clientHeight || 400;
  const old = zoom.value, value = Math.min(1.6, Math.max(0.3, old + amount));
  pan.value = { x: width / 2 - (width / 2 - pan.value.x) * value / old, y: height / 2 - (height / 2 - pan.value.y) * value / old };
  zoom.value = value;
}
function startPan(event: PointerEvent) {
  if (event.button !== 0 || (event.target as Element).closest("button")) return;
  drag = { id: event.pointerId, x: event.clientX, y: event.clientY, startX: pan.value.x, startY: pan.value.y };
  canvas.value?.setPointerCapture(event.pointerId); dragging.value = true;
}
function movePan(event: PointerEvent) {
  if (drag?.id !== event.pointerId) return;
  pan.value = { x: drag.startX + event.clientX - drag.x, y: drag.startY + event.clientY - drag.y };
}
function stopPan() { drag = null; dragging.value = false; }
function panWithKeyboard(event: KeyboardEvent) {
  if (event.target !== canvas.value) return;
  const offsets: Record<string, [number, number]> = { ArrowLeft: [40, 0], ArrowRight: [-40, 0], ArrowUp: [0, 40], ArrowDown: [0, -40] };
  const offset = offsets[event.key];
  if (offset) { event.preventDefault(); pan.value = { x: pan.value.x + offset[0], y: pan.value.y + offset[1] }; }
  if (event.key === "Home") { event.preventDefault(); fit(); }
}
function selectNode(node: BranchNode) { current.value.selectedId = node.id; notice.value = ""; }
function switchExploration(id: string) {
  draft.value.activeId = id; collapsed.value = new Set(); comparison.value = []; notice.value = "";
  void nextTick(fit);
}
function toggleCollapsed(node: BranchNode) {
  const next = new Set(collapsed.value);
  if (next.has(node.id)) next.delete(node.id);
  else { next.add(node.id); if (path.value.some(n => n.id === node.id)) current.value.selectedId = node.id; }
  collapsed.value = next; void nextTick(fit);
}
function childCount(id: string) { return current.value.nodes.filter(n => n.parentId === id).length; }
function editJudgment(event: Event) { selected.value.judgment = (event.target as HTMLTextAreaElement).value; selected.value.confirmed = false; notice.value = ""; }
function editStance(event: Event) { selected.value.stance = (event.target as HTMLSelectElement).value; selected.value.confirmed = false; }
function confirmJudgment() {
  selected.value.confirmed = true; persist();
  notice.value = storageError.value ? "已在当前页面确认判断，请导出备份。" : "已记录这一步的判断，可以继续分叉，也可以先停在这里。";
}
function toggleComparison() {
  const id = selected.value.id;
  if (comparison.value.includes(id)) comparison.value = comparison.value.filter(x => x !== id);
  else if (comparison.value.length < 2) comparison.value.push(id);
  else notice.value = "已选两个情境。请先打开分支对照，或移除一个已选情境。";
}

const editor = ref<HTMLDialogElement | null>(null), compareDialog = ref<HTMLDialogElement | null>(null);
const mode = ref<"branch" | "root">("branch"), conditionKey = ref(""), afterValue = ref(""), question = ref(""), formError = ref("");
const rootConditions = ref(initialConditions.map(c => ({ ...c })));
const changingCondition = computed(() => selected.value.conditions.find(c => c.key === conditionKey.value));
function openEditor(nextMode: "branch" | "root") {
  mode.value = nextMode; conditionKey.value = selected.value.conditions[0].key;
  afterValue.value = ""; question.value = ""; formError.value = ""; editor.value?.showModal();
  rootConditions.value = initialConditions.map(c => ({ ...c }));
}
function submitEditor() {
  try {
    if (mode.value === "root") {
      if (draft.value.explorations.length >= 30) throw new Error("本机已保存 30 个探索，请先导出备份。");
      const exploration = createExploration(question.value, rootConditions.value);
      draft.value.explorations.push(exploration); switchExploration(exploration.id);
    } else {
      const parentId = selected.value.id;
      addBranch(current.value, parentId, conditionKey.value, afterValue.value, question.value);
      const next = new Set(collapsed.value); next.delete(parentId); collapsed.value = next;
      void nextTick(fit);
    }
    persist(); editor.value?.close(); notice.value = "";
  } catch (error) { formError.value = error instanceof Error ? error.message : "暂时无法创建情境。"; }
}
function download(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportDraft() { download("thinkspace-branches.json", JSON.stringify(draft.value, null, 2), "application/json;charset=utf-8"); }
function exportCurrentPath() { download("thinkspace-thought-path.md", exportPath(current.value, selected.value.id), "text/markdown;charset=utf-8"); }
onMounted(() => {
  document.title = "思想分叉 · ThinkSpace";
  if (canvas.value) { resizeObserver = new ResizeObserver(fit); resizeObserver.observe(canvas.value); }
  fit();
  window.addEventListener("pagehide", persist);
});
onBeforeUnmount(() => { clearTimeout(saveTimer); persist(); resizeObserver?.disconnect(); window.removeEventListener("pagehide", persist); });
</script>

<template>
  <div class="thought-workspace">
    <aside class="thought-sidebar">
      <div class="exploration-heading"><span>我的探索</span><span>{{ draft.explorations.length }}</span></div>
      <div class="exploration-list">
        <button v-for="exploration in draft.explorations" :key="exploration.id" :class="{ active: exploration.id === draft.activeId }" @click="switchExploration(exploration.id)"><BranchIcon name="thought" /><span>{{ exploration.topic }}</span></button>
      </div>
      <button v-if="!thought" class="new-exploration" @click="openEditor('root')"><BranchIcon name="plus" />新建探索</button>
    </aside>

    <main class="thought-main">
      <header class="thought-topbar"><div><a href="/space">思考空间</a></div><button class="thought-button quiet" @click="exportDraft"><BranchIcon name="download" />导出探索</button></header>
      <section class="thought-intro"><h1>思想分叉</h1><span class="thought-local">{{ thought ? "本次探索" : "本机草稿" }}</span></section>
      <p v-if="storageError" class="thought-error" role="alert">{{ storageError }}</p>
      <section class="thought-tree" aria-labelledby="tree-heading">
        <div class="tree-toolbar"><div><BranchIcon name="branch" /><h2 id="tree-heading">思考路径</h2><span>{{ current.nodes.length }} 个情境</span></div><div><button class="thought-button quiet compare-toggle" :disabled="comparison.length !== 2" @click="compareDialog?.showModal()"><BranchIcon name="compare" />分支对照<span v-if="comparison.length">{{ comparison.length }}/2</span></button><span class="toolbar-divider"></span><button class="icon-button" aria-label="缩小画布" @click="zoomBy(-.1)"><BranchIcon name="minus" /></button><span class="zoom-label">{{ Math.round(zoom * 100) }}%</span><button class="icon-button" aria-label="放大画布" @click="zoomBy(.1)"><BranchIcon name="plus" /></button><button class="icon-button" aria-label="适应画布" @click="fit"><BranchIcon name="fit" /></button></div></div>
        <div ref="canvas" class="tree-canvas" :class="{ dragging }" tabindex="0" role="region" aria-label="思想分叉画布，拖动空白区域或使用方向键平移" @keydown="panWithKeyboard" @pointerdown="startPan" @pointermove="movePan" @pointerup="stopPan" @pointercancel="stopPan" @lostpointercapture="stopPan">
          <div class="tree-world" :style="{ width: layout.width + 'px', height: layout.height + 'px', transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }">
            <svg class="tree-connections" :width="layout.width" :height="layout.height" aria-hidden="true"><path v-for="connection in connections" :key="connection.id" :d="connection.d" :class="{ active: connection.active }" /></svg>
            <div v-for="position in layout.positions" :key="position.node.id" class="branch-card" :class="{ selected: selected.id === position.node.id, ancestor: selectedPathIds.has(position.node.id), compared: comparison.includes(position.node.id) }" :style="{ left: position.x + 'px', top: position.y + 'px' }">
              <button class="branch-node" :aria-label="'查看情境：' + position.node.title" :aria-pressed="selected.id === position.node.id" @click="selectNode(position.node)">
                <span class="node-type"><BranchIcon :name="position.node.parentId ? 'branch' : 'thought'" />{{ position.node.change?.label || '起始情境' }}<span v-if="position.node.confirmed" class="node-confirmed"><BranchIcon name="check" />已确认</span><span v-if="comparison.includes(position.node.id)" class="comparison-mark">已选对照</span></span>
                <strong>{{ position.node.parentId ? position.node.title : current.topic }}</strong>
                <span class="node-state"><BranchIcon v-if="position.node.confirmed" name="check" />{{ position.node.confirmed ? position.node.stance : position.node.judgment ? '判断草稿' : '等待你的判断' }}</span>
              </button>
              <button v-if="childCount(position.node.id)" class="collapse-branch" :aria-label="(collapsed.has(position.node.id) ? '展开' : '收起') + position.node.title + '的分支'" :aria-expanded="!collapsed.has(position.node.id)" @click="toggleCollapsed(position.node)">{{ collapsed.has(position.node.id) ? '+' : '−' }} {{ childCount(position.node.id) }}</button>
            </div>
          </div>
        </div>
      </section>

      <section class="current-question" aria-labelledby="current-question-title">
        <div class="question-context"><div class="question-kicker"><span><BranchIcon name="thought" />当前问题</span><span>{{ selected.origin === 'sample' ? '示例情境' : '自建情境' }} · {{ path.length === 1 ? '起点' : '第 ' + (path.length - 1) + ' 层分叉' }}</span></div><h2 id="current-question-title">{{ selected.question }}</h2>
          <p v-if="selected.change" class="condition-change"><span>{{ selected.change.label }}</span><s>{{ selected.change.before }}</s><span class="change-symbol">/</span><strong>{{ selected.change.after }}</strong></p>
          <div class="condition-tags"><span v-for="condition in selected.conditions" :key="condition.key" :class="{ changed: condition.key === selected.change?.key }">{{ condition.value }}</span></div>
          <button class="thought-button comparison-action" :aria-pressed="comparison.includes(selected.id)" @click="toggleComparison"><BranchIcon name="compare" />{{ comparison.includes(selected.id) ? '移出分支对照' : '加入分支对照' }}</button>
        </div>
        <div class="question-judgment"><div class="judgment-heading"><label for="branch-judgment">此刻，你怎么想？</label><select aria-label="当前判断倾向" :value="selected.stance" @change="editStance"><option v-for="stance in STANCES" :key="stance">{{ stance }}</option></select></div><textarea id="branch-judgment" :value="selected.judgment" maxlength="4000" placeholder="记录你的判断、理由，或者暂时没有答案的地方…" @input="editJudgment"></textarea><div class="judgment-actions"><span class="draft-state">{{ selected.confirmed ? '这一步的判断已确认' : '允许保留疑问，也可以稍后再写' }}</span><button class="thought-button quiet" :disabled="!selected.judgment.trim()" @click="confirmJudgment"><BranchIcon name="check" />确认判断</button><button class="thought-button primary" @click="openEditor('branch')"><BranchIcon name="plus" />改变一个条件</button></div></div>
      </section>
      <footer class="thought-footer"><span role="status">{{ notice || (thought ? '确认判断后可存入资料库。' : storageError ? '当前修改仅保留在页面，请先导出备份。' : '草稿自动保存在本浏览器，刷新后可继续。') }}</span><button @click="exportCurrentPath">导出当前路径</button></footer>
    </main>

    <dialog ref="editor" class="thought-dialog" aria-labelledby="branch-editor-title" @close="formError = ''">
      <form @submit.prevent="submitEditor"><div class="dialog-heading"><h2 id="branch-editor-title">{{ mode === 'root' ? '新建探索' : '创建分支' }}</h2><button type="button" class="icon-button" aria-label="关闭情境编辑" @click="editor?.close()"><BranchIcon name="close" /></button></div>
        <template v-if="mode === 'branch'"><p class="dialog-note">从「{{ selected.title }}」继续，其他条件保持一致。</p><label for="condition-choice">这次改变哪个条件？</label><select id="condition-choice" v-model="conditionKey" @change="afterValue = ''"><option v-for="condition in selected.conditions" :key="condition.key" :value="condition.key">{{ condition.label }}</option></select><p class="previous-condition">当前：{{ changingCondition?.value }}</p><label for="condition-value">新的条件</label><input id="condition-value" v-model="afterValue" required maxlength="120" placeholder="例如：决定无法撤回" /></template>
        <label for="branch-question">{{ mode === 'root' ? '你想探索什么问题？' : '在这个条件下，你想问什么？' }}</label><textarea id="branch-question" v-model="question" required maxlength="180" :placeholder="mode === 'root' ? '例如：AI 可以替我做决定吗？' : '把问题写具体一点，让这次分叉有明确的方向。'"></textarea>
        <details v-if="mode === 'root'" class="root-conditions-editor"><summary>设定三个起始条件</summary><p class="dialog-note">默认是 AI 决策情境。探索其他问题时，请在这里填写适用的条件。</p><div v-for="(condition, i) in rootConditions" :key="condition.key"><label :for="'root-label-' + i">条件 {{ i + 1 }} 名称</label><input :id="'root-label-' + i" v-model="condition.label" required maxlength="24" /><label :for="'root-value-' + i">条件 {{ i + 1 }} 内容</label><input :id="'root-value-' + i" v-model="condition.value" required maxlength="120" /></div></details><p v-if="formError" class="thought-error" role="alert">{{ formError }}</p><div class="dialog-actions"><button type="button" class="thought-button quiet" @click="editor?.close()">取消</button><button type="submit" class="thought-button primary">{{ mode === 'root' ? '开始探索' : '创建分支' }}</button></div>
      </form>
    </dialog>
    <dialog ref="compareDialog" class="thought-dialog comparison-dialog" aria-labelledby="branch-comparison-title"><div class="dialog-heading"><div><p class="thought-eyebrow">TWO PATHS, YOUR PERSPECTIVE</p><h2 id="branch-comparison-title">条件变了，判断呢？</h2></div><button class="icon-button" aria-label="关闭分支对照" @click="compareDialog?.close()"><BranchIcon name="close" /></button></div><div class="comparison-columns"><article v-for="node in comparisonNodes" :key="node.id"><span class="comparison-origin">{{ node.origin === 'sample' ? '示例情境' : '自建情境' }}</span><h3>{{ node.question }}</h3><dl><template v-for="condition in node.conditions" :key="condition.key"><dt>{{ condition.label }}</dt><dd :class="{ difference: comparisonNodes.some(other => other.conditions.find(c => c.key === condition.key)?.value !== condition.value) }">{{ condition.value }}</dd></template></dl><div class="comparison-judgment"><span>我的判断 · {{ node.confirmed ? '已确认' : '待确认' }}</span><strong>{{ node.stance }}</strong><p>{{ node.judgment || '还没有记录理由，可以回到这个情境继续思考。' }}</p></div><button class="thought-button quiet" @click="selectNode(node); compareDialog?.close()">回到这个情境</button></article></div><p class="dialog-note">不同条件可以有不同判断，不必让两条路径得出相同答案。</p></dialog>
  </div>
  <ThoughtResultForm v-if="thought && selected.confirmed" :key="selected.id + ':' + selected.judgment"
    class="shell" :parent-id="thought.id" kind="branch" :initial-body="selected.judgment" />
</template>

<style scoped src="../thought-branches.css"></style>
