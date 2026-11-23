<script setup lang="ts">
import ChaosPendulum from "./ChaosPendulum.vue";
import SpaceTools from "./SpaceTools.vue";
import SpaceIcon from "./SpaceIcon.vue";
import { pickWorkspaceQuote } from "../workspace-quotes";
import type { Bubble } from "../types";

defineProps<{
  authenticated: boolean; recent: Bubble[]; loading: boolean; failed: boolean;
  resume?: { href: string; label: string };
}>();
const quote = pickWorkspaceQuote();
</script>

<template>
  <main class="hub-home">
    <section class="hub-welcome" aria-labelledby="hub-welcome-title">
      <div class="hub-welcome-copy">
        <h1 id="hub-welcome-title" class="hub-quotation">「{{ quote.text }}」</h1>
        <p class="hub-quote-source">{{ quote.source }}</p>
        <div class="hub-welcome-actions">
          <a v-if="resume" class="hub-action primary" :href="resume.href">继续{{ resume.label }}</a>
          <a v-else class="hub-action primary" href="/space">进入思考空间</a>
          <a v-if="resume?.href !== '/library'" class="hub-action quiet" href="/library">打开资料库</a>
          <a v-else class="hub-action quiet" href="/space">打开思考空间</a>
        </div>
      </div>
      <ChaosPendulum />
    </section>

    <div class="hub-home-grid">
      <section aria-labelledby="hub-tools-title">
        <div class="hub-section-heading"><h2 id="hub-tools-title">思考工具</h2><a href="/space">全部工具</a></div>
        <SpaceTools />
      </section>
      <section aria-labelledby="hub-recent-title">
        <div class="hub-section-heading"><h2 id="hub-recent-title">最近想法</h2><a href="/thought-bubbles">查看泡泡</a></div>
        <div class="hub-recent">
          <p v-if="loading" class="hub-recent-empty" role="status">正在读取想法…</p>
          <p v-else-if="failed" class="hub-recent-empty">暂时无法读取最近想法。<a href="/thought-bubbles">到泡泡页重试</a></p>
          <p v-else-if="!authenticated" class="hub-recent-empty"><a href="/account">登录</a>后，这里会显示你的阅读手记。</p>
          <p v-else-if="!recent.length" class="hub-recent-empty">阅读时通过扩展记下的想法会出现在这里。<a href="/account#extension">连接阅读扩展</a></p>
          <a v-for="bubble in recent" :key="bubble.id" class="hub-recent-item" :href="`/thought-bubbles?note=${encodeURIComponent(bubble.id)}`">
            <span><strong>{{ bubble.body }}</strong><small>{{ bubble.title || "阅读手记" }}</small></span>
            <SpaceIcon name="right" />
          </a>
        </div>
      </section>
    </div>
  </main>
</template>
