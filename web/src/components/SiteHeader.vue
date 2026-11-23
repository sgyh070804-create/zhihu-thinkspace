<script setup lang="ts">
import type { AuthStatus, Profile } from "../types";

defineProps<{ section: string; status: AuthStatus | null; profile: Profile | null }>();
const links = [
  { id: "home", href: "/", label: "首页" },
  { id: "library", href: "/library", label: "资料库" },
  { id: "space", href: "/space", label: "思考空间" },
];
</script>

<template>
  <header class="hub-header">
    <div class="hub-header-inner">
      <a class="hub-brand" href="/" aria-label="ThinkSpace 首页">
        <span aria-hidden="true">T</span><strong>ThinkSpace</strong>
      </a>
      <nav class="hub-nav" aria-label="主导航">
        <a v-for="link in links" :key="link.id" :href="link.href"
          :aria-current="section === link.id ? 'page' : undefined">{{ link.label }}</a>
      </nav>
      <a class="hub-account" href="/account" :aria-current="section === 'account' ? 'page' : undefined"
        :aria-label="status?.authenticated ? '个人中心' : '登录与账户'">
        <img v-if="status?.authenticated && profile?.avatar_path" :src="profile.avatar_path" alt="" />
        <span v-else class="hub-avatar" aria-hidden="true">{{ status?.authenticated ? (profile?.fullname?.slice(0, 1) || "我") : "我" }}</span>
        <span>{{ status?.authenticated ? "个人中心" : "登录" }}</span>
      </a>
    </div>
  </header>
</template>
