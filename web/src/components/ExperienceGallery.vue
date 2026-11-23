<script setup lang="ts">
import { ref } from "vue";
const experiences = [
  { id: "bubbles", title: "思维泡泡", label: "思绪空间 · 阅读与连接", description: "在透明薄膜间浏览阅读手记，走进一颗想法，写下两个观点之间的新连接。", url: "/thought-bubbles", icon: "◌" },
  { id: "debate", title: "长桌讨论室", label: "本地演示 · 预设讨论", description: "与刘看山围桌而坐，查看角色动作、参与发言和导出记录。回复尚未接入 AI。", url: "/experiences/debate/", icon: "◎" },
];
const selected = ref<(typeof experiences)[number] | null>(null);
</script>
<template>
  <section class="experience-gallery" aria-labelledby="experience-title">
    <div class="workspace-heading"><div><div class="eyebrow">ROOM FOR YOUR THOUGHTS</div><h1 id="experience-title">给想法一点空间</h1></div></div>
    <p class="experience-note">进入思维泡泡浏览阅读手记，或在讨论室体验角色互动。讨论室使用预设回复，尚未接入 AI。</p>
    <template v-if="!selected">
      <div class="experience-cards">
        <article v-for="experience in experiences" :key="experience.id" class="panel experience-card">
          <span class="experience-symbol" aria-hidden="true">{{ experience.icon }}</span>
          <small>{{ experience.label }}</small><h2>{{ experience.title }}</h2><p>{{ experience.description }}</p>
          <a v-if="experience.id === 'bubbles'" class="button primary" :href="experience.url">进入思维泡泡</a>
          <button v-else class="button primary" @click="selected = experience">进入{{ experience.title }}</button>
        </article>
      </div>
    </template>
    <section v-else class="experience-stage" :aria-label="selected.title">
      <div class="experience-toolbar"><button class="button secondary" @click="selected = null">← 返回思考体验</button><span>{{ selected.label }}</span><a :href="selected.url" target="_blank" rel="noreferrer">独立窗口 ↗</a></div>
      <p class="experience-note">演示中的变化仅保留在当前页面，离开后会重置。</p>
      <iframe :key="selected.id" :src="selected.url" :title="selected.title + '交互演示'" class="experience-frame"></iframe>
    </section>
  </section>
</template>
