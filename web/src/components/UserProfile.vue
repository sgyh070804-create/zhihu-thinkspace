<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, ApiError } from "../api";
import type { ContentItem, Followee, Paging, Profile } from "../types";

const emit = defineEmits<{ back: [] }>();

const profile = ref<Profile | null>(null);
const profileLoading = ref(true);
const error = ref("");

const PAGE_SIZE = 5;

const followees = ref<Followee[]>([]);
const followeesPaging = ref<Paging | null>(null);
const followeesLoading = ref(false);

const creations = ref<ContentItem[]>([]);
const creationsPaging = ref<Paging | null>(null);
const creationsLoading = ref(false);

function formatDate(timestamp?: number) {
  if (!timestamp) return "未标注时间";
  return new Date(timestamp * 1000).toLocaleDateString("zh-CN");
}

async function loadProfile() {
  profileLoading.value = true;
  try {
    profile.value = await api<Profile>("/zhihu/me");
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : "用户信息加载失败。";
  } finally {
    profileLoading.value = false;
  }
}

async function loadFollowees(reset = false) {
  if (followeesLoading.value) return;
  followeesLoading.value = true;
  error.value = "";
  try {
    const offset = reset || !followeesPaging.value?.NextOffset
      ? "0"
      : followeesPaging.value.NextOffset;
    const data = await api<{ Items: Followee[]; Paging: Paging }>(
      `/zhihu/followees?offset=${offset}&limit=${PAGE_SIZE}`,
    );
    followees.value = reset ? data.Items || [] : [...followees.value, ...(data.Items || [])];
    followeesPaging.value = data.Paging || null;
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : "关注列表加载失败。";
  } finally {
    followeesLoading.value = false;
  }
}

async function loadCreations(reset = false) {
  if (creationsLoading.value) return;
  creationsLoading.value = true;
  error.value = "";
  try {
    const offset = reset || !creationsPaging.value?.NextOffset
      ? "0"
      : creationsPaging.value.NextOffset;
    const data = await api<{ Items: ContentItem[]; Paging: Paging }>(
      `/zhihu/contents?content_type=all&offset=${offset}&limit=${PAGE_SIZE}`,
    );
    creations.value = reset ? data.Items || [] : [...creations.value, ...(data.Items || [])];
    creationsPaging.value = data.Paging || null;
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : "创作列表加载失败。";
  } finally {
    creationsLoading.value = false;
  }
}

onMounted(async () => {
  await loadProfile();
  await Promise.all([loadFollowees(true), loadCreations(true)]);
});
</script>

<template>
  <section class="user-profile">
    <button class="button secondary back-button" @click="emit('back')">← 返回资料区</button>

    <div v-if="error" class="error-banner">
      <span>{{ error }}</span><button @click="loadProfile">重试</button>
    </div>

    <div class="profile-card panel">
      <div v-if="profileLoading" class="empty">正在加载用户信息…</div>
      <template v-else-if="profile">
        <div class="profile-identity">
          <img
            v-if="profile.avatar_path"
            class="profile-avatar"
            :src="profile.avatar_path"
            alt="用户头像"
          />
          <span v-else class="profile-avatar placeholder">{{ profile.fullname.slice(0, 1) || "?" }}</span>
          <div class="profile-text">
            <h1>{{ profile.fullname || "未设置昵称" }}</h1>
            <p v-if="profile.headline" class="profile-headline">{{ profile.headline }}</p>
            <p v-if="profile.description" class="profile-description">{{ profile.description }}</p>
            <small class="profile-uid">知乎用户 ID：{{ profile.uid || "未返回" }}</small>
          </div>
          <a
            v-if="profile.url"
            class="button secondary profile-link"
            :href="profile.url"
            target="_blank"
            rel="noreferrer"
          >知乎主页 ↗</a>
        </div>
      </template>
      <div v-else class="empty">未能获取用户信息，可能是授权已过期，请退出后重新登录。</div>
    </div>

    <div class="profile-lists">
      <div class="panel">
        <div class="panel-heading">
          <h2>关注的人</h2>
          <span>共 {{ followeesPaging?.Totals ?? followees.length }} 人</span>
        </div>
        <div v-if="followees.length" class="followee-list">
          <a
            v-for="person in followees"
            :key="person.Url"
            class="person"
            :href="person.Url"
            target="_blank"
            rel="noreferrer"
          >
            <img v-if="person.AvatarUrl" class="person-photo" :src="person.AvatarUrl" alt="" />
            <span v-else class="avatar">{{ person.Fullname.slice(0, 1) }}</span>
            <span>
              <strong>{{ person.Fullname }}</strong>
              <small>{{ person.Headline || "无简介" }}</small>
            </span>
            <span class="person-count">{{ person.FollowerCount }} 关注者</span>
          </a>
        </div>
        <p v-else-if="!followeesLoading" class="empty">没有可展示的关注用户。</p>
        <p v-if="followeesLoading" class="empty">加载中…</p>
        <button
          v-if="followeesPaging && !followeesPaging.IsEnd && followees.length"
          class="load-more"
          :disabled="followeesLoading"
          @click="loadFollowees()"
        >{{ followeesLoading ? "加载中…" : "加载更多关注" }}</button>
        <p v-else-if="followees.length && followeesPaging?.IsEnd" class="end-note">已显示全部关注。</p>
      </div>

      <div class="panel">
        <div class="panel-heading">
          <h2>创作信息</h2>
          <span>公开摘要 · 共 {{ creationsPaging?.Totals ?? creations.length }} 条</span>
        </div>
        <div v-if="creations.length" class="card-list">
          <article v-for="item in creations" :key="item.Url" class="content-card">
            <div class="content-meta">{{ item.ContentType }} · {{ formatDate(item.CreatedAt) }}</div>
            <a :href="item.Url" target="_blank" rel="noreferrer">{{ item.Title }}</a>
            <p>{{ item.Summary }}</p>
            <footer>
              <span>公开摘要</span>
              <span>{{ item.LikeCount || 0 }} 赞同 · {{ item.CommentCount || 0 }} 评论 · {{ item.FavoriteCount || 0 }} 收藏</span>
            </footer>
          </article>
        </div>
        <p v-else-if="!creationsLoading" class="empty">没有可展示的公开创作。</p>
        <p v-if="creationsLoading" class="empty">加载中…</p>
        <button
          v-if="creationsPaging && !creationsPaging.IsEnd && creations.length"
          class="load-more"
          :disabled="creationsLoading"
          @click="loadCreations()"
        >{{ creationsLoading ? "加载中…" : "加载更多创作" }}</button>
        <p v-else-if="creations.length && creationsPaging?.IsEnd" class="end-note">已显示全部创作。</p>
      </div>
    </div>
  </section>
</template>
