<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { layoutTree } from "../branches";
import { nodePath } from "../thought-tree";
import type { BranchCandidate, TreeNode } from "../thought-tree";
import BranchIcon from "./BranchIcon.vue";

const props = defineProps<{ nodes: TreeNode[]; selectedId: string; candidates: BranchCandidate[]; disabled: boolean }>();
const emit = defineEmits<{ select: [id: string]; candidate: [index: number] }>();
const viewport = ref<HTMLElement>(), scale = ref(1), pan = ref({ x: 0, y: 0 });
const collapsed = ref(new Set<string>()), dragging = ref(false);
let drag: { id: number; x: number; y: number; startX: number; startY: number } | undefined;
let observer: ResizeObserver | undefined;

const children = computed(() => {
  const counts = new Map<string, number>();
  for (const { parent_id } of props.nodes) if (parent_id) counts.set(parent_id, (counts.get(parent_id) || 0) + 1);
  return counts;
});
const layout = computed(() => layoutTree([
  ...props.nodes.map(node => ({ ...node, parentId: node.parent_id, candidate: -1 })),
  ...props.candidates.map((candidate, index) => ({
    ...candidate, id: 'candidate-' + index, parentId: props.selectedId, candidate: index,
  })),
], collapsed.value));
const highlights = computed(() => new Set(nodePath(props.nodes, props.selectedId).map(node => node.id)));
const edges = computed(() => {
  const byId = new Map(layout.value.positions.map(item => [item.node.id, item]));
  return layout.value.positions.flatMap(({ node, x, y }) => {
    const parent = node.parentId && byId.get(node.parentId);
    if (!parent) return [];
    const sx = parent.x + 252, sy = parent.y + 30, ey = y + 30;
    return [{ id: node.id, preview: node.candidate >= 0, d: 'M' + sx + ',' + sy + ' C' + (sx + 32) + ',' + sy + ' ' + (x - 32) + ',' + ey + ' ' + x + ',' + ey }];
  });
});
function fit() {
  if (!viewport.value) return;
  const { clientWidth: width, clientHeight: height } = viewport.value;
  const size = layout.value;
  const fitScale = Math.min((width - 32) / size.width, (height - 24) / size.height, 1);
  if (fitScale < .55 && width < 620) {
    const current = size.positions.find(item => item.node.id === props.selectedId);
    if (current) {
      scale.value = .8;
      pan.value = { x: width / 2 - (current.x + 126) * .8, y: height / 2 - (current.y + 30) * .8 };
      return;
    }
  }
  scale.value = Math.max(.24, fitScale);
  pan.value = { x: (width - size.width * scale.value) / 2, y: (height - size.height * scale.value) / 2 };
}
function zoom(delta: number) {
  if (!viewport.value) return;
  const x = viewport.value.clientWidth / 2, y = viewport.value.clientHeight / 2;
  const next = Math.min(1.6, Math.max(.24, scale.value + delta));
  const ratio = next / scale.value;
  pan.value = { x: x - (x - pan.value.x) * ratio, y: y - (y - pan.value.y) * ratio };
  scale.value = next;
}
function start(event: PointerEvent) {
  if (event.button !== 0 || (event.target as Element).closest("button")) return;
  drag = { id: event.pointerId, x: event.clientX, y: event.clientY, startX: pan.value.x, startY: pan.value.y };
  viewport.value?.setPointerCapture(event.pointerId);
  dragging.value = true;
}
function move(event: PointerEvent) {
  if (drag?.id !== event.pointerId) return;
  pan.value = { x: drag.startX + event.clientX - drag.x, y: drag.startY + event.clientY - drag.y };
}
function stop() { drag = undefined; dragging.value = false; }
function onKey(event: KeyboardEvent) {
  if (event.target !== viewport.value) return;
  if (event.key === "Home") { event.preventDefault(); fit(); return; }
  const offset = { ArrowLeft: [35, 0], ArrowRight: [-35, 0], ArrowUp: [0, 35], ArrowDown: [0, -35] }[event.key];
  if (offset) { event.preventDefault(); pan.value = { x: pan.value.x + offset[0], y: pan.value.y + offset[1] }; }
}
function toggle(nodeId: string) {
  if (collapsed.value.has(nodeId)) collapsed.value.delete(nodeId);
  else {
    collapsed.value.add(nodeId);
    if (highlights.value.has(nodeId)) emit("select", nodeId);
  }
  void nextTick(fit);
}
watch([() => props.nodes.length, () => props.candidates.length], () => void nextTick(fit));
watch(() => props.selectedId, () => {
  for (const ancestor of nodePath(props.nodes, props.selectedId).slice(0, -1)) collapsed.value.delete(ancestor.id);
  if (viewport.value && viewport.value.clientWidth < 620) void nextTick(fit);
});
onMounted(() => {
  observer = new ResizeObserver(fit);
  if (viewport.value) observer.observe(viewport.value);
  fit();
});
onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <section class="free-tree-canvas" aria-label="思绪画布">
    <header class="free-tree-tools">
      <span>{{ nodes.length }} 个节点</span>
      <div>
        <button type="button" class="icon-button" aria-label="缩小画布" @click="zoom(-.12)"><BranchIcon name="minus" /></button>
        <button type="button" class="icon-button" aria-label="放大画布" @click="zoom(.12)"><BranchIcon name="plus" /></button>
        <button type="button" class="icon-button" aria-label="适应画布" @click="fit"><BranchIcon name="fit" /></button>
      </div>
    </header>
    <div ref="viewport" class="free-tree-viewport" :class="{ 'is-dragging': dragging }" tabindex="0"
      aria-label="拖动或使用方向键移动画布" @keydown="onKey" @pointerdown="start" @pointermove="move"
      @pointerup="stop" @pointercancel="stop" @lostpointercapture="stop">
      <div class="tree-world" :style="{ width: layout.width + 'px', height: layout.height + 'px', transform: 'translate(' + pan.x + 'px,' + pan.y + 'px) scale(' + scale + ')' }">
        <svg class="tree-connections" :width="layout.width" :height="layout.height" aria-hidden="true">
          <path v-for="edge in edges" :key="edge.id" :d="edge.d" :class="{ active: highlights.has(edge.id), 'is-candidate': edge.preview }" />
        </svg>
        <div v-for="{ node, x, y } in layout.positions" :key="node.id" class="free-tree-leaf" :class="{ 'is-candidate': node.candidate >= 0 }"
          :style="{ left: x + 'px', top: y + 'px' }">
          <button v-if="node.candidate >= 0" type="button" class="free-tree-node" @click="emit('candidate', node.candidate)">
            <small>AI 候选</small><strong>{{ node.title }}</strong>
          </button>
          <template v-else>
            <button type="button" class="free-tree-node" :disabled="disabled" :aria-pressed="selectedId === node.id" @click="emit('select', node.id)">
              <small v-if="!node.parentId">原始思绪</small><strong>{{ node.title }}</strong>
            </button>
            <button v-if="children.has(node.id)" type="button" class="free-tree-collapse"
              :aria-label="(collapsed.has(node.id) ? '展开' : '折叠') + node.title"
              :aria-expanded="!collapsed.has(node.id)" :disabled="disabled" @click="toggle(node.id)">
              {{ collapsed.has(node.id) ? '+' : '−' }}
            </button>
          </template>
        </div>
      </div>
    </div>
  </section>
</template>
