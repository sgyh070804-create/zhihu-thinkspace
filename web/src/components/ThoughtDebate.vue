<script setup lang="ts">
import { ref } from "vue";
import type { ThoughtRecord } from "../types";
import ThoughtResultForm from "./ThoughtResultForm.vue";

const props = defineProps<{ thought: ThoughtRecord }>();
const frame = ref<HTMLIFrameElement>(), error = ref("");

function initialize() {
  const room = frame.value?.contentWindow as (Window & {
    debateRoom?: { setThought(title: string, body: string): void };
  }) | null | undefined;
  if (!room?.debateRoom?.setThought) {
    error.value = "讨论室无法载入这条思绪，请刷新后重试。";
    return;
  }
  room.debateRoom.setThought(props.thought.title, props.thought.body);
  error.value = "";
}
</script>

<template>
  <main class="shell hub-page" aria-label="长桌讨论室">
    <p v-if="error" role="alert">{{ error }}</p>
    <iframe ref="frame" src="/experiences/debate/" title="长桌讨论室" class="experience-frame" @load="initialize"></iframe>
    <ThoughtResultForm :parent-id="thought.id" kind="discussion" />
  </main>
</template>
