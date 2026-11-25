<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api, ApiError } from "../api";
import { RequestScope } from "../request-scope";
import { saveThought, thoughtLink } from "../thought-library";
import type { ThoughtRecord } from "../types";
import LibraryShelf from "./LibraryShelf.vue";
import ThoughtLinks from "./ThoughtLinks.vue";
import ThoughtResultForm from "./ThoughtResultForm.vue";

const props = defineProps<{ initialId?: string }>();
const emit = defineEmits<{ select: [id: string] }>();
const records = ref<ThoughtRecord[]>([]), selectedId = ref(props.initialId || "");
const loading = ref(true), error = ref(""), formError = ref(""), editing = ref(false), saving = ref(false);
const revising = ref(false);
const draft = ref({ title: "", body: "", source_url: "" });
const listRequest = new RequestScope(), writeRequest = new RequestScope();
let requestId = "";
const labels: Record<ThoughtRecord["kind"], string> = {
  reading: "阅读手记", library: "资料库", fusion: "泡泡融合", branch: "思想分叉", discussion: "长桌讨论", revision: "整理版本",
};
const books = computed(() => records.value.map(record => ({
  id: record.id, title: record.title || "未命名思绪", subtitle: labels[record.kind],
})));
const selected = computed(() => records.value.find(record => record.id === selectedId.value));
const parents = computed(() => selected.value?.parent_ids.map(id => records.value.find(record => record.id === id))
  .filter((record): record is ThoughtRecord => !!record) || []);
const children = computed(() => records.value.filter(record => record.parent_ids.includes(selectedId.value)));

function openSaved(thought: ThoughtRecord) {
  listRequest.invalidate();
  loading.value = false;
  records.value = [thought, ...records.value.filter(record => record.id !== thought.id)];
  selectedId.value = thought.id;
  error.value = "";
  emit("select", thought.id);
}

async function load() {
  const request = listRequest.begin();
  loading.value = true;
  error.value = "";
  try {
    const data = await api<{ items: ThoughtRecord[] }>("/thoughts", { signal: request.signal });
    if (!request.isCurrent()) return;
    records.value = data.items;
    if (selectedId.value && !selected.value) error.value = "这条思绪暂不可用。";
  } catch (reason) {
    if (request.isCurrent()) error.value = reason instanceof ApiError ? reason.message : "无法读取思绪。";
  } finally {
    if (request.isCurrent()) loading.value = false;
  }
}

async function create() {
  if (saving.value || !draft.value.body.trim()) return;
  const request = writeRequest.begin();
  requestId ||= crypto.randomUUID();
  saving.value = true;
  formError.value = "";
  try {
    const thought = await saveThought(draft.value, requestId, request.signal);
    if (!request.isCurrent()) return;
    openSaved(thought);
    draft.value = { title: "", body: "", source_url: "" };
    requestId = "";
    editing.value = false;
  } catch (reason) {
    if (request.isCurrent()) formError.value = reason instanceof ApiError ? reason.message : "保存失败，请重试。";
  } finally {
    if (request.isCurrent()) saving.value = false;
  }
}

function open(id: string) {
  selectedId.value = selectedId.value === id ? "" : id;
  emit("select", selectedId.value);
}

watch(() => props.initialId, id => { selectedId.value = id || ""; });
watch(selectedId, () => { revising.value = false; });
onMounted(load);
onBeforeUnmount(() => { listRequest.invalidate(); writeRequest.invalidate(); });
</script>

<template>
  <section aria-label="资料库思绪">
    <div class="thought-library-toolbar">
      <button type="button" class="hub-action primary" :aria-expanded="editing" @click="editing = !editing">记录思绪</button>
    </div>
    <form v-if="editing" class="panel thought-record-form" @submit.prevent="create" @input="requestId = ''">
      <label>标题<input v-model="draft.title" maxlength="180" :disabled="saving" /></label>
      <label>思绪内容<textarea v-model="draft.body" rows="4" maxlength="4000" required :disabled="saving"></textarea></label>
      <label>知乎原文链接（可选）<input v-model="draft.source_url" type="url" maxlength="2000" :disabled="saving" /></label>
      <p v-if="formError" role="alert">{{ formError }}</p>
      <button type="submit" class="hub-action primary" :disabled="saving || loading || !draft.body.trim()">{{ saving ? "保存中…" : "保存思绪" }}</button>
    </form>
    <div v-if="error" class="error-banner" role="alert"><span>{{ error }}</span><button @click="load">重试</button></div>
    <LibraryShelf :books="books" :open-id="selectedId" :loading="loading" @open="open" />
    <article v-if="selected" class="panel thought-record-detail">
      <h2>{{ selected.title }}</h2>
      <p class="thought-record-body">{{ selected.body }}</p>
      <blockquote v-if="selected.quote">{{ selected.quote }}</blockquote>
      <p v-if="selected.source_url"><a :href="selected.source_url" target="_blank" rel="noreferrer">{{ selected.source_title || "打开知乎原文" }}</a></p>
      <ThoughtLinks :id="selected.id" />
      <div v-if="parents.length || children.length" class="thought-history">
        <h3>版本与来路</h3>
        <a v-for="parent in parents" :key="parent.id" :href="thoughtLink('/library', parent.id)">
          {{ selected.kind === "revision" ? "上一版本" : "来自" }}「{{ parent.title }}」
        </a>
        <a v-for="child in children" :key="child.id" :href="thoughtLink('/library', child.id)">
          {{ child.kind === "revision" ? "后续版本" : "派生思绪" }}「{{ child.title }}」
        </a>
      </div>
      <button type="button" class="hub-action quiet thought-revise" :aria-expanded="revising" @click="revising = !revising">
        {{ revising ? "关闭整理" : "整理为新版本" }}
      </button>
      <ThoughtResultForm v-if="revising" :key="selected.id" :parent-id="selected.id" kind="revision"
        :initial-title="selected.title" :initial-body="selected.body" @saved="openSaved" />
    </article>
  </section>
</template>
