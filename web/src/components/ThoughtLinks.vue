<script setup lang="ts">
import { thoughtLink, thoughtModes } from "../thought-library";

defineProps<{ id: string; activePath?: string }>();
</script>

<template>
  <nav class="hub-welcome-actions" aria-label="使用这条思绪">
    <template v-for="mode in thoughtModes" :key="mode.path">
      <span v-if="mode.path === activePath" class="hub-action primary" aria-current="page">{{ mode.label }}</span>
      <a v-else class="hub-action quiet" :href="thoughtLink(mode.path, id)">{{ mode.label }}</a>
    </template>
  </nav>
</template>
