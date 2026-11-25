<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { api, ApiError } from "../api";
import { RequestScope } from "../request-scope";
import { thoughtLink } from "../thought-library";
import type { ThoughtRecord } from "../types";
import ThoughtLinks from "./ThoughtLinks.vue";

const props = defineProps<{ id: string; activePath: string }>();
const record = ref<ThoughtRecord>(), error = ref("");
const scope = new RequestScope();

onMounted(async () => {
  const request = scope.begin();
  try {
    const thought = await api<ThoughtRecord>(`/thoughts/${encodeURIComponent(props.id)}`, { signal: request.signal });
    if (request.isCurrent()) record.value = thought;
  } catch (reason) {
    if (request.isCurrent()) error.value = reason instanceof ApiError ? reason.message : "无法读取这条思绪。";
  }
});
onBeforeUnmount(() => scope.invalidate());
</script>

<template>
  <section class="shell panel thought-record-context" aria-label="当前思绪">
    <a class="hub-back" :href="thoughtLink('/library', id)">返回资料库</a>
    <template v-if="record">
      <h2>{{ record.title }}</h2>
      <p v-if="record.body !== record.title" class="thought-record-body">{{ record.body }}</p>
      <blockquote v-if="record.quote">{{ record.quote }}</blockquote>
      <p v-if="record.source_url"><a :href="record.source_url" target="_blank" rel="noreferrer">{{ record.source_title || "打开知乎原文" }}</a></p>
      <ThoughtLinks :id="record.id" :active-path="activePath" />
    </template>
    <p v-else-if="error" role="alert">{{ error }}</p>
    <p v-else role="status">正在读取思绪…</p>
  </section>
  <slot v-if="record" :record="record" />
</template>
