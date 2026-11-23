<script setup lang="ts">
import BranchIcon from "./BranchIcon.vue";
import SpaceIcon from "./SpaceIcon.vue";

const tools = [
  { id: "bubbles", href: "/thought-bubbles", label: "思维泡泡", description: "重读阅读手记，把两个想法连成新的观点。" },
  { id: "branches", href: "/thought-branches", label: "思想分叉", description: "改变一个条件，看看自己的判断会怎么变。" },
  { id: "debate", href: "/space/debate", label: "长桌讨论室", description: "和刘看山围桌而坐，从不同角色的角度看问题。" },
];
</script>

<template>
  <div class="hub-tools">
    <a v-for="tool in tools" :key="tool.id" class="hub-tool" :href="tool.href">
      <span class="hub-tool-icon">
        <SpaceIcon v-if="tool.id === 'bubbles'" name="bubbles" />
        <BranchIcon v-else :name="tool.id === 'branches' ? 'branch' : 'thought'" />
      </span>
      <span><strong>{{ tool.label }}</strong><small>{{ tool.description }}</small></span>
      <SpaceIcon class="hub-tool-next" name="right" />
    </a>
  </div>
</template>
