<script setup lang="ts">
import { ref } from "vue";
const experiences = [
  { id: "bubbles", title: "灵感泡泡", label: "交互演示 · 示例观点", description: "让想法游动、挤压和融合，点击进入泡泡阅读。融合结果使用示例文案。", url: "/experiences/bubbles/", icon: "◌" },
  { id: "debate", title: "长桌讨论室", label: "本地演示 · 预设讨论", description: "与刘看山围桌而坐，查看角色动作、参与发言和导出记录。回复尚未接入 AI。", url: "/experiences/debate/", icon: "◎" },
];
const selected = ref<(typeof experiences)[number] | null>(null);
</script>
<template>
  <section class="experience-gallery" aria-labelledby="experience-title">
    <div class="workspace-heading"><div><div class="eyebrow">ROOM FOR YOUR THOUGHTS</div><h1 id="experience-title">给想法一点空间</h1></div></div>
    <p class="experience-note">体验泡泡与角色互动。这里使用示例内容，暂不与资料区的泡泡记录或真实 AI 服务同步。</p>
    <template v-if="!selected">
      <div class="experience-cards">
        <article v-for="experience in experiences" :key="experience.id" class="panel experience-card">
          <span class="experience-symbol" aria-hidden="true">{{ experience.icon }}</span>
          <small>{{ experience.label }}</small><h2>{{ experience.title }}</h2><p>{{ experience.description }}</p>
          <button class="button primary" @click="selected = experience">进入{{ experience.title }} ↗</button>
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
