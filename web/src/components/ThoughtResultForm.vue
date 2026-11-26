<script setup lang="ts">
import { onBeforeUnmount, ref } from "vue";
import { ApiError } from "../api";
import { RequestScope } from "../request-scope";
import { saveThought, thoughtLink } from "../thought-library";
import type { ThoughtRecord } from "../types";

const props = defineProps<{
  parentId: string; kind: "branch" | "discussion" | "revision"; initialBody?: string; initialTitle?: string;
}>();
const emit = defineEmits<{ saved: [record: ThoughtRecord] }>();
const title = ref(props.initialTitle || "");
const labels = { branch: "分叉结论", discussion: "讨论心得", revision: "整理后的思绪" };
const body = ref(props.initialBody || ""), saving = ref(false), error = ref(""), saved = ref<ThoughtRecord>();
const scope = new RequestScope();
let requestId = "";

async function commit() {
  if (saving.value || !body.value.trim()) return;
  const request = scope.begin();
  requestId ||= crypto.randomUUID();
  saving.value = true;
  error.value = "";
  try {
    const thought = await saveThought(
      { title: title.value, body: body.value, kind: props.kind, parent_ids: [props.parentId] },
      requestId, request.signal,
    );
    if (!request.isCurrent()) return;
    saved.value = thought;
    body.value = "";
    requestId = "";
    emit("saved", thought);
  } catch (reason) {
    if (request.isCurrent()) error.value = reason instanceof ApiError ? reason.message : "保存失败，请重试。";
  } finally {
    if (request.isCurrent()) saving.value = false;
  }
}
onBeforeUnmount(() => scope.invalidate());
</script>

<template>
  <form class="panel thought-record-form thought-result" @submit.prevent="commit" @input="requestId = ''; saved = undefined">
    <label v-if="kind === 'revision'">版本标题<input v-model="title" maxlength="180" :disabled="saving" /></label>
    <label>{{ labels[kind] }}
      <textarea v-model="body" rows="3" maxlength="4000" required :disabled="saving"></textarea>
    </label>
    <button type="submit" class="hub-action primary" :disabled="saving || !body.trim()">{{ saving ? "保存中…" : kind === "revision" ? "保存新版本" : "保存为新思绪" }}</button>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="saved" role="status">已保存。<a :href="thoughtLink('/library', saved.id)">在资料库查看</a></p>
  </form>
</template>
