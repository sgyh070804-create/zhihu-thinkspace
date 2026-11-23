<script setup lang="ts">
import BranchIcon from "./BranchIcon.vue";
import SpaceIcon from "./SpaceIcon.vue";

const tools = [
  { id: "bubbles", href: "/thought-bubbles", label: "思维泡泡" },
  { id: "branches", href: "/thought-branches", label: "思想分叉" },
  { id: "debate", href: "/space/debate", label: "长桌讨论室" },
];
</script>

<template>
  <div class="hub-tools">
    <a v-for="tool in tools" :key="tool.id" class="hub-tool" :href="tool.href">
      <span class="hub-tool-icon">
        <SpaceIcon v-if="tool.id === 'bubbles'" name="bubbles" />
        <BranchIcon v-else :name="tool.id === 'branches' ? 'branch' : 'thought'" />
      </span>
      <strong>{{ tool.label }}</strong>
      <SpaceIcon class="hub-tool-next" name="right" />
    </a>
  </div>
</template>
